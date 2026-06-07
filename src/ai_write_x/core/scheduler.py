import threading
import time
import asyncio
import traceback
from datetime import datetime, timedelta
from typing import Optional, List

from src.ai_write_x.database.db_manager import db_manager
from src.ai_write_x.utils import log
from src.ai_write_x.config.config import Config

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
        self._initialized = True

    def start(self):
        """启动后台调度线程"""
        if self.is_running:
            return
        
        self.is_running = True
        self.thread = threading.Thread(target=self._run_loop, name="SchedulerThread", daemon=True)
        self.thread.start()
        log.print_log("⏰ Scheduler Service (定时任务系统) 已启动", "success")

    def stop(self):
        """停止后台调度线程"""
        self.is_running = False
        log.print_log("⏰ Scheduler Service 已停止", "info")

    def _run_loop(self):
        """心跳轮询逻辑 (每 60 秒检查一次)"""
        while self.is_running:
            try:
                self._check_and_execute_tasks()
            except Exception as e:
                log.print_log(f"[Scheduler] 轮询异常: {e}\n{traceback.format_exc()}", "error")
            
            # 每 60 秒检查一次，直到停止
            for _ in range(60):
                if not self.is_running:
                    break
                time.sleep(1)

    def _check_and_execute_tasks(self):
        """检查并执行到期的任务"""
        active_tasks = db_manager.get_active_tasks()
        if not active_tasks:
            return

        for task in active_tasks:
            if not db_manager.claim_task_for_execution(str(task.id)):
                continue
            log.print_log(f"🕒 发现到期任务: {task.topic or '(自动热点)'} ({task.platform})", "info")

            t = threading.Thread(
                target=self._execute_single_task,
                args=(str(task.id),),
                name=f"TaskExecutor-{str(task.id)[:8]}",
                daemon=True,
            )
            t.start()

    def _execute_single_task(self, task_id: str):
        """执行单个具体任务"""
        from src.ai_write_x.database.models import ScheduledTask
        
        task = None
        try:
            # 重新获取任务对象确保状态最新
            task = ScheduledTask.get_by_id(task_id)

            db_manager.log_task_execution(task_id, 'running', "任务开始执行...")

            # 初始化工作流
            workflow = UnifiedContentWorkflow()
            
            # 定时任务配置
            kwargs = {
                "publish_platform": task.platform,
                "auto_publish": True,
                "use_ai_beautify": task.use_ai_beautify
            }
            
            is_collection = getattr(task, "collection_mode", False)
            
            # 如果话题为空，尝试自动拾取热点话题（复用立马生成的逻辑）
            original_topic = task.topic.strip() if task.topic else ""
            
            count = task.article_count if task.article_count > 0 else 1
            success_count = 0
            
            used_topics_in_batch = []
            from src.ai_write_x.utils.topic_deduplicator import TopicDeduplicator
            deduplicator = TopicDeduplicator(dedup_days=3)
            
            for i in range(count):
                # 动态确定本次生成的话题
                current_topic = ""
                if not original_topic:
                    from src.ai_write_x.tools import hotnews
                    # 随机从微博、头条、百度之一取热点
                    platforms = ["微博", "今日头条", "百度热点"]
                    try:
                        # 尝试获取不重复的热点
                        retry_count = 0
                        while retry_count < 5:
                            platform_to_use = platforms[(i + retry_count) % len(platforms)]
                            # 开启权威源优先模式
                            candidate = hotnews.select_platform_topic(platform_to_use, cnt=200, exclude_topics=used_topics_in_batch, authority_priority=True)
                            if not deduplicator.is_duplicate(candidate) and candidate not in used_topics_in_batch:
                                current_topic = candidate
                                break
                            retry_count += 1
                        
                        if not current_topic:
                            current_topic = f"深度解析：{platforms[i % len(platforms)]}最新科技与社会动态"
                            
                        log.print_log(f"🔥 [Scheduler] 空话题填充: 自动拾取或生成热点: {current_topic}", "info")
                    except Exception as e:
                        current_topic = f"深入探讨：热点解析系列 {i+1}"
                        log.print_log(f"⚠️ [Scheduler] 自动拾取话题失败: {e}，将使用备用安全话题", "warning")
                else:
                    from src.ai_write_x.core.llm_client import LLMClient
                    llm = LLMClient()
                    recent_topics = deduplicator.get_recent_topics(days=7) if hasattr(deduplicator, 'get_recent_topics') else []
                    all_excluded = list(set(recent_topics + used_topics_in_batch))
                    excluded_str = '、'.join(all_excluded[:20]) if all_excluded else '无'
                    
                    if is_collection:
                        sub_prompt = (
                            f"你是一个资深内容策划编辑。核心系列是「{original_topic}」，请为今天的文章生成一个子话题标题。\n"
                            f"要求：\n"
                            f"1. 子话题必须属于「{original_topic}」领域，但切入点要新颖独特\n"
                            f"2. 子话题要有悬念或痛点，能引发读者好奇心\n"
                            f"3. 不要与以下已用选题重复或过于相似：{excluded_str}\n"
                            f"4. 只输出子话题本身，不要包含「{original_topic}」前缀，不要冒号，不要任何解释或标点包裹\n"
                            f"5. 最终标题格式为「{original_topic}：{{你生成的子话题}}」"
                        )
                    else:
                        sub_prompt = (
                            f"你是一个资深内容策划编辑。核心领域是「{original_topic}」，请基于该领域生成一个具体的、有吸引力的文章标题作为今日选题。\n"
                            f"要求：\n"
                            f"1. 必须属于「{original_topic}」领域，但切入点要新颖独特\n"
                            f"2. 标题要有悬念或痛点，能引发读者好奇心\n"
                            f"3. 不要与以下已用选题重复或过于相似：{excluded_str}\n"
                            f"4. 只输出一个标题，不要任何解释、序号或标点包裹"
                        )
                    try:
                        diverged = llm.chat([{"role": "user", "content": sub_prompt}], temperature=0.9).strip().strip('"').strip("'").strip('《》')
                        if is_collection and diverged:
                            if not diverged.startswith(original_topic):
                                diverged = f"{original_topic}：{diverged}"
                        if diverged and not deduplicator.is_duplicate(diverged) and diverged not in used_topics_in_batch:
                            current_topic = diverged
                            log.print_log(f"🧠 [Scheduler] {'合集' if is_collection else ''}发散新角度: {current_topic}", "info")
                        else:
                            if is_collection:
                                retry_prompt = (
                                    f"核心系列「{original_topic}」，请生成一个与已有选题完全不同的子话题。"
                                    f"已用选题：{excluded_str}。只输出子话题本身，不要包含前缀。"
                                )
                            else:
                                retry_prompt = (
                                    f"核心领域「{original_topic}」，请生成一个与已有选题完全不同的文章标题。"
                                    f"已用选题：{excluded_str}。只输出标题。"
                                )
                            diverged2 = llm.chat([{"role": "user", "content": retry_prompt}], temperature=1.0).strip().strip('"').strip("'").strip('《》')
                            if is_collection and diverged2:
                                if not diverged2.startswith(original_topic):
                                    diverged2 = f"{original_topic}：{diverged2}"
                            if diverged2:
                                current_topic = diverged2
                                log.print_log(f"🧠 [Scheduler] 二次发散成功: {current_topic}", "info")
                            else:
                                current_topic = original_topic
                                log.print_log(f"⚠️ [Scheduler] 二次发散仍重复，使用原话题: {current_topic}", "warning")
                    except Exception as e:
                        current_topic = original_topic
                        log.print_log(f"⚠️ [Scheduler] 话题发散失败: {e}，使用原话题", "warning")

                # 记录已使用的话题，防止本批次内重复
                used_topics_in_batch.append(current_topic)
                # 同时也记入全局数据库去重器
                deduplicator.add_topic(current_topic)

                log.print_log(f"🚀 [Scheduler] 正在执行任务: {current_topic} ({i+1}/{count})", "info")
                
                # V13.0 Fix: 防止 "multiple values for keyword argument 'topic'" 异常
                # 确保 kwargs 不含有 'topic'，因为它是作为位置参数传递的
                if "topic" in kwargs:
                    kwargs.pop("topic")
                
                if is_collection:
                    kwargs["collection_mode"] = True
                
                results = workflow.execute(topic=current_topic, **kwargs)
                
                if results.get("success"):
                    success_count += 1
                    msg = f"文章 {i+1} 生成成功"
                    if results.get("publish_result"):
                        msg += f"并已发布: {results['publish_result'].get('message', '')}"

                    if kwargs.get("use_ai_beautify"):
                        art_path = results.get("save_result", {}).get("path")
                        if art_path:
                            try:
                                from src.ai_write_x.core.visual_assets import VisualAssetsManager
                                VisualAssetsManager.auto_fix_article_images(art_path)
                                log.print_log(
                                    "[Scheduler] 已同步补齐配图（定时任务不自动换模板，请在文章库手动操作）",
                                    "info",
                                )
                            except Exception as img_e:
                                log.print_log(f"[Scheduler] 配图补齐失败: {img_e}", "warning")
                    
                    db_manager.log_task_execution(
                        task_id=task_id, 
                        status='success', 
                        message=msg,
                        article_id=results.get("save_result", {}).get("path")
                    )
                else:
                    db_manager.log_task_execution(task_id, 'failed', f"文章 {i+1} 执行失败")
            
            if success_count == count:
                log.print_log(f"✅ [Scheduler] 任务全部完成 ({success_count}/{count})", "success")
            else:
                log.print_log(f"⚠️ [Scheduler] 任务部分完成 ({success_count}/{count})", "warning")

        except Exception as e:
            err_msg = f"任务执行异常: {str(e)}"
            log.print_log(f"[Scheduler] {err_msg}", "error")
            if task_id:
                db_manager.log_task_execution(task_id, 'failed', f"{err_msg}\n{traceback.format_exc()}")
        finally:
            # 更新下一次执行时间或禁用任务
            self._finalize_task(task_id)

    def _finalize_task(self, task_id: str):
        """处理任务后续逻辑：更新时间或禁用"""
        from src.ai_write_x.database.models import ScheduledTask
        try:
            task = ScheduledTask.get_by_id(task_id)
            task.last_run_at = datetime.now()
            
            if task.is_recurring and task.interval_hours > 0:
                # 计算下一次运行时间
                task.execution_time = task.last_run_at + timedelta(hours=task.interval_hours)
                task.status = 'enabled' # 恢复为可用
            else:
                # 一次性任务，标记为已完成（实际上通过状态禁用即可）
                task.status = 'completed'
            
            task.save()
        except Exception as e:
            log.print_log(f"[Scheduler] 任务结算失败: {e}", "error")

scheduler_service = SchedulerService()
