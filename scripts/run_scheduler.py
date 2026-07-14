#!/usr/bin/env python3
"""Run the XBoom scheduler as a single, graceful server-side service."""

from __future__ import annotations

import argparse
import fcntl
import os
import signal
import sys
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            os.environ.setdefault(key, value.strip())


def _acquire_singleton_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RuntimeError(f"another scheduler process owns {path}") from exc
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def main() -> int:
    parser = argparse.ArgumentParser(description="XBoom scheduler service")
    parser.add_argument("--check", action="store_true", help="validate imports and configuration, then exit")
    parser.add_argument(
        "--shutdown-timeout",
        type=float,
        default=float(os.environ.get("AIWRITEX_SCHEDULER_SHUTDOWN_TIMEOUT", "3600")),
    )
    args = parser.parse_args()

    _load_env_file(ROOT / ".env.server")
    os.environ.setdefault("AIWRITEX_SERVER_MODE", "1")
    os.environ.setdefault("APP_ENV", "production")

    from src.ai_write_x.config.config import Config
    from src.ai_write_x.core.scheduler import scheduler_service
    from src.ai_write_x.utils import log
    from src.ai_write_x.utils.path_manager import PathManager

    config = Config.get_instance()
    if not config.load_config():
        raise RuntimeError("scheduler configuration could not be loaded")

    if args.check:
        print("scheduler-check=ok")
        return 0

    lock_path = PathManager.get_app_data_dir() / "data" / "scheduler-service.lock"
    lock_handle = _acquire_singleton_lock(lock_path)
    stop_event = threading.Event()

    def _request_stop(signum, _frame):
        log.print_log(f"[SchedulerService] signal={signum}; stopping new polls", "info")
        scheduler_service.stop()
        stop_event.set()

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    try:
        scheduler_service.start()
        log.print_log(f"[SchedulerService] singleton lock acquired: {lock_path}", "success")
        stop_event.wait()
        if not scheduler_service.wait_until_idle(timeout=args.shutdown_timeout):
            log.print_log(
                f"[SchedulerService] shutdown timeout with {scheduler_service.running_task_count()} task(s) active",
                "warning",
            )
            return 2
        log.print_log("[SchedulerService] graceful shutdown complete", "success")
        return 0
    finally:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
