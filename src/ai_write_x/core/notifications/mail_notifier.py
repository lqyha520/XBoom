# -*- coding: utf-8 -*-
"""Scheduler task completion email notification via agently-cli."""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


MAIL_NOTIFIER_ENABLED = True  # set False to disable email notifications


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


def _send_email_via_cli(to_addr: str, subject: str, body: str) -> bool:
    """Send an email using agently-cli (two-phase confirmation flow)."""
    if not MAIL_NOTIFIER_ENABLED:
        return False

    # Use a body file to avoid shell escaping issues
    # agently-cli requires --body-file to be a relative path
    body_file = Path(__file__).parent / ".task_email_body.tmp"
    body_file_rel = "./.task_email_body.tmp"
    cwd_dir = str(Path(__file__).parent)
    try:
        body_file.write_text(body, encoding="utf-8")

        # Phase 1: send without confirmation
        cmd_phase1 = [
            "agently-cli", "message", "+send",
            "--to", to_addr,
            "--subject", subject,
            "--body-file", body_file_rel,
        ]

        result = subprocess.run(
            cmd_phase1, capture_output=True, text=True, timeout=30, cwd=cwd_dir
        )

        if result.returncode != 0:
            print(f"[MailNotifier] Phase 1 failed: {result.stderr.strip()}", file=sys.stderr)
            return False

        # Parse response for confirmation_token
        output = result.stdout.strip()
        start = output.find("{")
        end = output.rfind("}") + 1
        if start < 0 or end <= start:
            print("[MailNotifier] Could not parse CLI response (no JSON)", file=sys.stderr)
            return False

        json_str = output[start:end]
        resp = json.loads(json_str)

        if resp.get("data", {}).get("confirmation_required"):
            token = resp["data"]["confirmation_token"]
            # Phase 2: confirm with token
            cmd_phase2 = [
                "agently-cli", "message", "+send",
                "--to", to_addr,
                "--subject", subject,
                "--body-file", body_file_rel,
                "--confirmation-token", token,
            ]
            result2 = subprocess.run(
                cmd_phase2, capture_output=True, text=True, timeout=30, cwd=cwd_dir
            )
            if result2.returncode == 0:
                print("[MailNotifier] Email sent successfully (confirmed)", file=sys.stderr)
                return True
            else:
                print(f"[MailNotifier] Phase 2 failed: {result2.stderr.strip()}", file=sys.stderr)
                return False
        else:
            # Already sent without needing confirmation
            print("[MailNotifier] Email sent successfully", file=sys.stderr)
            return True

    except FileNotFoundError:
        print("[MailNotifier] agently-cli not found in PATH", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print("[MailNotifier] agently-cli timed out", file=sys.stderr)
        return False
    except Exception as exc:
        print(f"[MailNotifier] Unexpected error: {exc}", file=sys.stderr)
        return False
    finally:
        # Cleanup temp file
        try:
            body_file.unlink(missing_ok=True)
        except Exception:
            pass


def send_task_completion_email(task_topic: str, platform: str,
                                total_count: int, success_count: int,
                                outcome: str, article_titles: list,
                                notify_email: str = None) -> bool:
    """Build and send a task-completion email.

    Args:
        task_topic: The scheduled task topic.
        platform: Target publishing platform.
        total_count: Planned article count.
        success_count: Successfully generated count.
        outcome: COMPLETED / FAILED / CANCELLED.
        article_titles: List of generated article titles.
        notify_email: Recipient address. If None, uses the account default.

    Returns:
        True if email was sent successfully (or disabled), False on failure.
    """
    if notify_email is None:
        notify_email = "bcxtech@agent.qq.com"

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_icon = {"COMPLETED": "✅", "FAILED": "❌", "CANCELLED": "⛔"}.get(outcome, "📋")
    public_ip = _get_public_ip()

    # Build HTML body
    articles_html = ""
    if article_titles:
        for i, title in enumerate(article_titles, 1):
            articles_html += f"<li>{title}</li>\n"
    else:
        articles_html = "<li>（无）</li>"

    body = f"""<h2>XBoom 定时任务完成通知</h2>
<ul>
<li><strong>状态：</strong>{status_icon} {outcome}</li>
<li><strong>主题：</strong>{task_topic}</li>
<li><strong>平台：</strong>{platform}</li>
<li><strong>时间：</strong>{now_str}</li>
<li><strong>服务器出口IP：</strong>{public_ip}</li>
<li><strong>进度：</strong>{success_count}/{total_count} 篇文章生成成功</li>
</ul>
<h3>生成文章列表</h3>
<ul>
{articles_html}
</ul>
<hr>
<p><em>由 XBoom 自动发送</em></p>"""

    subject = f"[XBoom] 定时任务完成 - {outcome} - {task_topic}"

    return _send_email_via_cli(notify_email, subject, body)
