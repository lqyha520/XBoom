"""客户端启动使用统计上报（公网 IP 由服务端从 HTTP 请求记录）。"""

from __future__ import annotations

import asyncio
import json
import platform
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from src.ai_write_x.config.config import Config
from src.ai_write_x.utils import log, utils
from src.ai_write_x.utils.path_manager import PathManager
from src.ai_write_x.version import get_version

DEFAULT_REPORT_URL = "https://updates.bcxtech.cn/stats/report.php"
INSTALL_ID_FILE = "install_id.txt"


def _usage_settings() -> Dict[str, Any]:
    config = Config.get_instance().config or {}
    merged: Dict[str, Any] = {
        "enabled": True,
        "report_url": DEFAULT_REPORT_URL,
        "report_token": "",
        "timeout_seconds": 8,
        # False：开发运行也会上报，便于验证；仅正式安装包统计可改为 True
        "release_only": False,
    }
    merged.update(config.get("usage_stats") or {})
    return merged


def _install_id_path() -> Path:
    config_dir = PathManager.get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / INSTALL_ID_FILE


def get_or_create_install_id() -> str:
    path = _install_id_path()
    if path.is_file():
        raw = path.read_text(encoding="utf-8").strip()
        try:
            return str(uuid.UUID(raw))
        except ValueError:
            pass
    install_id = str(uuid.uuid4())
    path.write_text(install_id, encoding="utf-8")
    return install_id


def _os_platform_label() -> str:
    try:
        win_ver = platform.win32_ver()
        if win_ver and win_ver[0]:
            return f"Windows-{win_ver[0]}"
    except Exception:
        pass
    return f"{platform.system()}-{platform.release()}"


def build_report_payload() -> Dict[str, str]:
    return {
        "install_id": get_or_create_install_id(),
        "app_version": get_version(),
        "os_platform": _os_platform_label(),
    }


def report_usage_sync() -> bool:
    """同步上报；失败不影响主流程，结果写入日志。"""
    settings = _usage_settings()
    if not settings.get("enabled", True):
        log.print_log("[使用统计] 已在配置中关闭 (usage_stats.enabled=false)", "info")
        return False
    if settings.get("release_only", False) and not utils.get_is_release_ver():
        log.print_log(
            "[使用统计] 当前为源码/开发运行且 release_only=true，已跳过上报",
            "info",
        )
        return False

    url = str(settings.get("report_url") or DEFAULT_REPORT_URL).strip()
    if not url:
        return False

    timeout = max(3, min(int(settings.get("timeout_seconds") or 8), 30))
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    token = str(settings.get("report_token") or "").strip()
    if token:
        headers["X-Stats-Token"] = token

    payload = build_report_payload()
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            try:
                body = response.json()
                if body.get("ok"):
                    log.print_log("[使用统计] 已记录本次启动", "info")
                    return True
            except json.JSONDecodeError:
                pass
        body_preview = ""
        try:
            body_preview = (response.text or "")[:120]
        except Exception:
            pass
        log.print_log(
            f"[使用统计] 上报失败 HTTP {response.status_code} {body_preview}",
            "warning",
        )
    except Exception as exc:
        log.print_log(f"[使用统计] 上报失败: {exc}", "warning")
    return False


async def report_usage_async() -> None:
    await asyncio.to_thread(report_usage_sync)


def schedule_usage_report() -> None:
    """在应用 lifespan 中调用，后台上报不阻塞启动。"""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(report_usage_async())
    except RuntimeError:
        report_usage_sync()
