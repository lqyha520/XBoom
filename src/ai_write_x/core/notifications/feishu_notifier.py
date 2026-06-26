# -*- coding: utf-8 -*-
"""Scheduler task completion Feishu (Lark) group notification via webhook."""

import sys
from datetime import datetime

import httpx

FEISHU_WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/e6df0dee-828f-43ed-8ca0-c3b920ff022c"

FEISHU_NOTIFIER_ENABLED = True  # set False to disable Feishu notifications


def _get_public_ip() -> str:
    """Get the server's public outbound IP address."""
    try:
        from src.ai_write_x.core.menu_ip_access import detect_public_ip
        ip = detect_public_ip(timeout=5.0)
        if ip:
            return ip
    except Exception:
        pass
    return "未知"


def _send_to_feishu(webhook_url: str, title: str, content_lines: list) -> bool:
    """Send a rich-text message to Feishu group via webhook."""
    if not FEISHU_NOTIFIER_ENABLED:
        return False

    message = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": title,
                    "content": [
                        [{"tag": "text", "text": line}]
                        for line in content_lines
                    ]
                }
            }
        }
    }

    try:
        response = httpx.post(webhook_url, json=message, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"[FeishuNotifier] 发送飞书消息失败: {e}", file=sys.stderr)
        return False


def send_task_completion_feishu(task_topic: str, platform: str,
                                total_count: int, success_count: int,
                                outcome: str, article_titles: list) -> bool:
    """Send a task-completion notification to Feishu group.

    Args:
        task_topic: The scheduled task topic.
        platform: Target publishing platform.
        total_count: Planned article count.
        success_count: Successfully generated count.
        outcome: COMPLETED / FAILED / CANCELLED.
        article_titles: List of generated article titles.

    Returns:
        True if message was sent successfully (or disabled), False on failure.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_icon = {"COMPLETED": "✅", "FAILED": "❌", "CANCELLED": "⛔"}.get(outcome, "📋")
    public_ip = _get_public_ip()

    articles_text = ""
    if article_titles:
        for i, title in enumerate(article_titles, 1):
            articles_text += f"{i}. {title}\n"
    else:
        articles_text = "（无）"

    content_lines = [
        f"{status_icon} 状态：{outcome}",
        f"📝 主题：{task_topic or '（自动选题）'}",
        f"📱 平台：{platform}",
        f"🕐 时间：{now_str}",
        f"🖥️ 服务器IP：{public_ip}",
        f"📊 进度：{success_count}/{total_count} 篇文章生成成功",
        "",
        "—— 生成文章列表 ——",
        articles_text.strip(),
    ]

    title = f"【XBoom】定时任务完成 - {outcome}"

    return _send_to_feishu(FEISHU_WEBHOOK_URL, title, content_lines)
