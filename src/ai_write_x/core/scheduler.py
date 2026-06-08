import threading
import time
import traceback
from datetime import datetime, timedelta
from typing import Set

from src.ai_write_x.database.db_manager import db_manager
from src.ai_write_x.core import task_status
from src.ai_write_x.utils import log


class SchedulerService:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SchedulerService, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.is_running = False
        self.thread = None
        self._running_task_ids: Set[str] = set()
        self._cancel_requested: Set[str] = set()
        self._state_lock = threading.Lock()
        self._initialized = True

    def start(self):
        """Start the background scheduler polling thread."""
        if self.is_running:
            return

        self.is_running = True
        self.thread = threading.Thread(target=self._run_loop, name="SchedulerThread", daemon=True)
        self.thread.start()
        log.print_log("Scheduler service started", "success")

    def stop(self):
        """Stop scheduler polling. Running task threads are allowed to finish."""
        self.is_running = False
        log.print_log("Scheduler service stopped", "info")

    def request_cancel(self, task_id: str):
        """Request cancellation for one scheduled-task execution only."""
        from src.ai_write_x.database.models import ScheduledTask

        task = ScheduledTask.get_by_id(task_id)
        if not task:
            return False, "Task not found"

        with self._state_lock:
            self._cancel_requested.add(task_id)

        if task.status in task_status.ACTIVE_STATUSES:
            if task.status != task_status.CANCEL_REQUESTED:
                db_manager.update_task_status(task_id, task_status.CANCEL_REQUESTED)
                db_manager.log_task_execution(task_id, task_status.CANCEL_REQUESTED, "User requested cancellation")
            return True, "Cancel requested"

        return False, "Task is not running"

    def is_cancel_requested(self, task_id: str) -> bool:
        with self._state_lock:
            if task_id in self._cancel_requested:
                return True

        try:
            from src.ai_write_x.database.models import ScheduledTask

            task = ScheduledTask.get_by_id(task_id)
            return bool(task and task.status == task_status.CANCEL_REQUESTED)
        except Exception:
            return False

    def _clear_cancel_request(self, task_id: str):
        with self._state_lock:
            self._cancel_requested.discard(task_id)

    def _mark_task_thread_started(self, task_id: str) -> bool:
        with self._state_lock:
            if task_id in self._running_task_ids:
                return False
            self._running_task_ids.add(task_id)
            return True

    def _mark_task_thread_finished(self, task_id: str):
        with self._state_lock:
            self._running_task_ids.discard(task_id)

    def _run_loop(self):
        """Poll due scheduled tasks once per minute."""
        while self.is_running:
            try:
                self._check_and_execute_tasks()
            except Exception as exc:
                log.print_log(f"[Scheduler] Polling failed: {exc}\n{traceback.format_exc()}", "error")

            for _ in range(60):
                if not self.is_running:
                    break
                time.sleep(1)

    def _check_and_execute_tasks(self):
        """Claim and start due tasks without launching duplicates."""
        active_tasks = db_manager.get_active_tasks()
        if not active_tasks:
            return

        for task in active_tasks:
            task_id = str(task.id)
            if not self._mark_task_thread_started(task_id):
                log.print_log(f"[Scheduler] Task {task_id[:8]} is already running; skipped duplicate launch", "warning")
                continue

            if not db_manager.claim_task_for_execution(task_id):
                self._mark_task_thread_finished(task_id)
                continue

            topic = task.topic or "auto hot topic"
            log.print_log(f"[Scheduler] Claimed task {task_id[:8]}: {topic} ({task.platform})", "info")

            thread = threading.Thread(
                target=self._execute_single_task,
                args=(task_id,),
                name=f"TaskExecutor-{task_id[:8]}",
                daemon=True,
            )
            thread.start()

    def _execute_single_task(self, task_id: str):
        """Execute one scheduled task and write detailed progress logs."""
        from src.ai_write_x.core.unified_workflow import UnifiedContentWorkflow
        from src.ai_write_x.database.models import ScheduledTask
        from src.ai_write_x.utils.topic_deduplicator import TopicDeduplicator

        outcome = task_status.FAILED
        success_count = 0
        count = 1

        try:
            task = ScheduledTask.get_by_id(task_id)
            if not task:
                log.print_log(f"[Scheduler] Task {task_id[:8]} no longer exists", "warning")
                return

            if self.is_cancel_requested(task_id):
                db_manager.log_task_execution(task_id, task_status.CANCELLED, "Task cancelled before execution")
                outcome = task_status.CANCELLED
                return

            count = task.article_count if task.article_count > 0 else 1
            original_topic = task.topic.strip() if task.topic else ""
            is_collection = getattr(task, "collection_mode", False)
            workflow = UnifiedContentWorkflow()
            deduplicator = TopicDeduplicator(dedup_days=3)
            used_topics_in_batch = []
            kwargs = {
                "publish_platform": task.platform,
                "auto_publish": True,
                "use_ai_beautify": task.use_ai_beautify,
            }
            kwargs["cancel_check"] = lambda task_id=task_id: self.is_cancel_requested(task_id)
            if is_collection:
                kwargs["collection_mode"] = True

            db_manager.log_task_execution(task_id, task_status.RUNNING, f"Task started, planned articles: {count}")

            for index in range(count):
                article_no = index + 1
                if self.is_cancel_requested(task_id):
                    db_manager.log_task_execution(
                        task_id,
                        task_status.CANCELLED,
                        f"Cancellation noticed before article {article_no}/{count}",
                    )
                    outcome = task_status.CANCELLED
                    break

                current_topic = self._resolve_topic(
                    original_topic=original_topic,
                    is_collection=is_collection,
                    index=index,
                    used_topics_in_batch=used_topics_in_batch,
                    deduplicator=deduplicator,
                )
                used_topics_in_batch.append(current_topic)
                deduplicator.add_topic(current_topic)

                db_manager.log_task_execution(
                    task_id,
                    task_status.RUNNING,
                    f"Generating article {article_no}/{count}: {current_topic}",
                )
                log.print_log(f"[Scheduler] Generating article {article_no}/{count}: {current_topic}", "info")

                results = workflow.execute(topic=current_topic, **kwargs)

                if self.is_cancel_requested(task_id):
                    db_manager.log_task_execution(
                        task_id,
                        task_status.CANCELLED,
                        f"Cancellation noticed after article {article_no}/{count}",
                    )
                    outcome = task_status.CANCELLED
                    break

                if results.get("success"):
                    success_count += 1
                    message = f"Article {article_no}/{count} generated successfully"
                    publish_result = results.get("publish_result")
                    if publish_result:
                        message += f": {publish_result.get('message', '')}"

                    self._sync_visual_assets_if_needed(results, kwargs)
                    db_manager.log_task_execution(
                        task_id=task_id,
                        status="success",
                        message=message,
                        article_id=results.get("save_result", {}).get("path"),
                    )
                else:
                    db_manager.log_task_execution(task_id, task_status.FAILED, f"Article {article_no}/{count} failed")

            if outcome != task_status.CANCELLED:
                outcome = task_status.COMPLETED if success_count == count else task_status.FAILED

            if outcome == task_status.COMPLETED:
                log.print_log(f"[Scheduler] Task completed ({success_count}/{count})", "success")
            elif outcome == task_status.CANCELLED:
                log.print_log(f"[Scheduler] Task cancelled ({success_count}/{count} completed)", "warning")
            else:
                log.print_log(f"[Scheduler] Task partially failed ({success_count}/{count})", "warning")

        except Exception as exc:
            outcome = task_status.FAILED
            message = f"Task execution failed: {exc}"
            log.print_log(f"[Scheduler] {message}", "error")
            db_manager.log_task_execution(task_id, task_status.FAILED, f"{message}\n{traceback.format_exc()}")
        finally:
            self._finalize_task(task_id, outcome)
            self._clear_cancel_request(task_id)
            self._mark_task_thread_finished(task_id)

    def _resolve_topic(self, original_topic, is_collection, index, used_topics_in_batch, deduplicator):
        if not original_topic:
            return self._select_hot_topic(index, used_topics_in_batch, deduplicator)
        return self._diverge_topic(original_topic, is_collection, used_topics_in_batch, deduplicator)

    def _select_hot_topic(self, index, used_topics_in_batch, deduplicator):
        from src.ai_write_x.tools import hotnews

        platforms = ["微博", "今日头条", "百度热点"]
        try:
            for retry in range(5):
                platform = platforms[(index + retry) % len(platforms)]
                candidate = hotnews.select_platform_topic(
                    platform,
                    cnt=200,
                    exclude_topics=used_topics_in_batch,
                    authority_priority=True,
                )
                if candidate and not deduplicator.is_duplicate(candidate) and candidate not in used_topics_in_batch:
                    log.print_log(f"[Scheduler] Selected hot topic: {candidate}", "info")
                    return candidate
        except Exception as exc:
            log.print_log(f"[Scheduler] Hot-topic selection failed: {exc}", "warning")

        fallback = f"深度解析：{platforms[index % len(platforms)]}最新科技与社会动态"
        log.print_log(f"[Scheduler] Using fallback topic: {fallback}", "warning")
        return fallback

    def _diverge_topic(self, original_topic, is_collection, used_topics_in_batch, deduplicator):
        from src.ai_write_x.core.llm_client import LLMClient

        recent_topics = deduplicator.get_recent_topics(days=7) if hasattr(deduplicator, "get_recent_topics") else []
        excluded = "、".join(list(dict.fromkeys(recent_topics + used_topics_in_batch))[:20]) or "无"
        llm = LLMClient()

        if is_collection:
            prompt = (
                f"你是资深内容策划编辑。核心系列是《{original_topic}》，请为今天的文章生成一个子话题标题。\n"
                f"要求：属于该系列，但切入点要新；不要与这些已用选题重复：{excluded}\n"
                f"只输出标题本身。最终格式可以是：{original_topic}：你的子话题"
            )
        else:
            prompt = (
                f"你是资深内容策划编辑。核心领域是《{original_topic}》，请生成一个具体、有吸引力的文章标题。\n"
                f"不要与这些已用选题重复：{excluded}\n只输出一个标题，不要解释。"
            )

        try:
            diverged = llm.chat([{"role": "user", "content": prompt}], temperature=0.9).strip().strip('"').strip("'").strip()
            if is_collection and diverged and not diverged.startswith(original_topic):
                diverged = f"{original_topic}：{diverged}"
            if diverged and not deduplicator.is_duplicate(diverged) and diverged not in used_topics_in_batch:
                log.print_log(f"[Scheduler] Diverged topic: {diverged}", "info")
                return diverged
        except Exception as exc:
            log.print_log(f"[Scheduler] Topic divergence failed: {exc}", "warning")

        return original_topic

    def _sync_visual_assets_if_needed(self, results, kwargs):
        if not kwargs.get("use_ai_beautify"):
            return
        article_path = results.get("save_result", {}).get("path")
        if not article_path:
            return
        try:
            from src.ai_write_x.core.visual_assets import VisualAssetsManager

            VisualAssetsManager.auto_fix_article_images(article_path)
            log.print_log("[Scheduler] Visual assets synchronized", "info")
        except Exception as exc:
            log.print_log(f"[Scheduler] Visual asset sync failed: {exc}", "warning")

    def _finalize_task(self, task_id: str, outcome: str):
        """Finalize task status and schedule the next recurring run."""
        from src.ai_write_x.database.models import ScheduledTask

        try:
            task = ScheduledTask.get_by_id(task_id)
            if not task:
                return

            now = datetime.now()
            task.last_run_at = now
            was_cancelled = outcome == task_status.CANCELLED or task.status == task_status.CANCEL_REQUESTED

            if task.is_recurring and task.interval_hours > 0:
                task.execution_time = now + timedelta(hours=task.interval_hours)
                task.status = task_status.ENABLED
                if was_cancelled:
                    db_manager.log_task_execution(task_id, task_status.CANCELLED, "Recurring task cancelled for this run; next run was scheduled")
            else:
                task.status = task_status.CANCELLED if was_cancelled else outcome

            task.updated_at = now
            task.save()
        except Exception as exc:
            log.print_log(f"[Scheduler] Task finalization failed: {exc}", "error")


scheduler_service = SchedulerService()
