"""Atomic persistence for recoverable background task state."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from src.ai_write_x.utils.path_manager import PathManager


class TaskStateStore:
    def __init__(self, state_dir: Path | None = None) -> None:
        self.state_dir = state_dir or (PathManager.get_app_data_dir() / "cache" / "task_state")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _safe_task_id(task_id: str) -> str:
        safe = "".join(ch for ch in task_id if ch.isalnum() or ch in ("-", "_"))
        if not safe:
            raise ValueError("task_id must contain at least one safe character")
        return safe

    def path_for(self, task_id: str) -> Path:
        return self.state_dir / f"{self._safe_task_id(task_id)}.json"

    def save(self, task_id: str, state: dict[str, Any]) -> None:
        path = self.path_for(task_id)
        payload = dict(state)
        payload["id"] = task_id
        payload["updated_at"] = time.time()
        temp_path = path.with_name(
            f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        encoded = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        with self._lock:
            temp_path.write_text(encoded, encoding="utf-8")
            os.replace(temp_path, path)

    def load(self, task_id: str) -> dict[str, Any] | None:
        path = self.path_for(task_id)
        with self._lock:
            if not path.is_file():
                return None
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
        return data if isinstance(data, dict) else None

    def clear(self, task_id: str) -> None:
        with self._lock:
            self.path_for(task_id).unlink(missing_ok=True)

    def mark_running_interrupted(self) -> list[str]:
        interrupted: list[str] = []
        with self._lock:
            paths = list(self.state_dir.glob("*.json"))
        for path in paths:
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(state, dict) or state.get("status") != "running":
                continue
            task_id = str(state.get("id") or path.stem)
            state["status"] = "interrupted"
            state["finished_at"] = time.time()
            state["error"] = "应用异常退出，任务已中断"
            self.save(task_id, state)
            interrupted.append(task_id)
        return interrupted
