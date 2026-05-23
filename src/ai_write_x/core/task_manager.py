import asyncio
import multiprocessing
import threading
import queue
import time
import uuid
from typing import Dict, Optional, Any, List
from src.ai_write_x.utils import log

class TaskStatus:
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"

class BackgroundTaskManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(BackgroundTaskManager, cls).__new__(cls)
                cls._instance._init()
            return cls._instance

    def _init(self):
        self.active_tasks: Dict[str, Any] = {} # taskId -> {process, thread, status, start_time, etc}
        self.log_queues: Dict[str, queue.Queue] = {} # taskId -> Queue
        self.task_registry_lock = threading.Lock()

    def _is_task_alive_unlocked(self, task: Dict) -> bool:
        thread = task.get("thread")
        if thread and thread.is_alive():
            return True
        for p in task.get("sub_processes", []):
            if p.is_alive():
                return True
        return False

    def _terminate_sub_processes_unlocked(self, task: Dict):
        for p in task.get("sub_processes", []):
            if p.is_alive():
                try:
                    p.terminate()
                except Exception:
                    pass

    def prepare_for_new_task(self, task_id: str):
        """放弃未完成的旧任务，为新创作腾出干净槽位（不续跑中断任务）。"""
        with self.task_registry_lock:
            if task_id not in self.active_tasks:
                return True, "ready"

            task = self.active_tasks[task_id]
            status = task.get("status")

            if status != TaskStatus.RUNNING:
                self.log_queues.pop(task_id, None)
                del self.active_tasks[task_id]
                return True, "cleared previous task"

            self._terminate_sub_processes_unlocked(task)
            alive = self._is_task_alive_unlocked(task)
            task["status"] = TaskStatus.STOPPED
            task["finished_at"] = time.time()
            task["error"] = "上次任务未完成已中断"

            self.log_queues.pop(task_id, None)
            del self.active_tasks[task_id]

            if alive:
                log.print_log(
                    "已放弃未完成的生成任务（后台线程仍在收尾，新任务将独立执行）",
                    "warning",
                )
                return True, "abandoned active task"

            log.print_log("已清理中断的生成任务，即将启动新任务", "info")
            return True, "cleared stale task"

    def start_task(self, task_id: str, target_func, args=()):
        """启动一个新的后台任务线程"""
        with self.task_registry_lock:
            log_q = queue.Queue()
            self.log_queues[task_id] = log_q
            
            task_info = {
                "id": task_id,
                "status": TaskStatus.RUNNING,
                "start_time": time.time(),
                "log_queue": log_q,
                "sub_processes": [] # 用于追踪产生的子进程
            }
            
            # 开启监控线程/Worker线程
            worker_thread = threading.Thread(
                target=self._worker_wrapper,
                args=(task_id, target_func, args, log_q),
                daemon=True
            )
            task_info["thread"] = worker_thread
            self.active_tasks[task_id] = task_info
            worker_thread.start()
            return True, task_id

    def _worker_wrapper(self, task_id, func, args, log_q):
        try:
            # 注入日志队列，让子流程的 log.print_log 能够定向到这里
            log.set_process_queue(log_q)
            
            # V11.1: 智能参数适配 (Signature Alignment)
            import inspect
            sig = inspect.signature(func)
            params = sig.parameters
            
            if len(args) != len(params):
                log.print_log(f"❌ 参数量严重不匹配 (sig: {len(params)}, args: {len(args)})，任务拒绝执行", "error")
                raise ValueError(f"Task argument mismatch: expected {len(params)}, got {len(args)}")
            
            func(*args)
                
            self.update_task_status(task_id, TaskStatus.COMPLETED)
        except Exception as e:
            log.print_log(f"Task {task_id} failed: {str(e)}", "error")
            self.update_task_status(task_id, TaskStatus.FAILED, error=str(e))
        finally:
            log.set_process_queue(None)

    def update_task_status(self, task_id: str, status: str, error: str = None):
        with self.task_registry_lock:
            if task_id in self.active_tasks:
                self.active_tasks[task_id]["status"] = status
                self.active_tasks[task_id]["finished_at"] = time.time()
                if error:
                    self.active_tasks[task_id]["error"] = error

    def get_task_status(self, task_id: str) -> Dict:
        with self.task_registry_lock:
            if task_id not in self.active_tasks:
                return {"status": TaskStatus.IDLE}

            task = self.active_tasks[task_id]
            if (
                task.get("status") == TaskStatus.RUNNING
                and not self._is_task_alive_unlocked(task)
            ):
                task["status"] = TaskStatus.STOPPED
                task["finished_at"] = time.time()
                task["error"] = task.get("error") or "任务已中断"

            return {
                "status": task["status"],
                "error": task.get("error"),
                "started_at": task.get("start_time"),
                "finished_at": task.get("finished_at")
            }

    def stop_task(self, task_id: str):
        with self.task_registry_lock:
            if task_id not in self.active_tasks:
                return False, "Task not found"
            
            task = self.active_tasks[task_id]
            self._terminate_sub_processes_unlocked(task)

            if task.get("status") == TaskStatus.RUNNING and not self._is_task_alive_unlocked(task):
                self.log_queues.pop(task_id, None)
                del self.active_tasks[task_id]
                return True, "Stale task cleared"

            task["status"] = TaskStatus.STOPPED
            task["finished_at"] = time.time()
            return True, "Task stopped"

    def register_sub_process(self, task_id: str, process):
        with self.task_registry_lock:
            if task_id in self.active_tasks:
                self.active_tasks[task_id].setdefault("sub_processes", []).append(process)

    def get_log_queue(self, task_id: str) -> Optional[queue.Queue]:
        return self.log_queues.get(task_id)

task_manager = BackgroundTaskManager()
