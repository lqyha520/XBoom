from __future__ import annotations

from datetime import datetime
from typing import Any

from src.ai_write_x.config.config import Config
from src.ai_write_x.core.account_profiles import AccountProfileService


def _has_value(value: Any) -> bool:
    if isinstance(value, (list, tuple)):
        return any(str(item or "").strip() for item in value)
    return bool(str(value or "").strip())


def _llm_config_error(config: Config) -> str:
    try:
        if not _has_value(config.api_apibase):
            return "大模型 API URL 未配置"
        if str(config.api_type or "").lower() != "ollama" and not _has_value(config.api_key):
            return "大模型 API Key 未配置"
        if not _has_value(config.api_model):
            return "大模型未选择"
    except Exception as exc:
        return f"大模型配置读取失败: {exc}"
    return ""


def _image_config_error(config: Config) -> str:
    try:
        img_type = str(config.img_api_type or "").strip()
        if not img_type:
            return "图片生成 API 类型未选择"
        if img_type == "picsum":
            return ""
        root = config.config.get("img_api", {})
        provider = root.get(img_type, {})
        if img_type == "custom" and isinstance(provider, list):
            index = int(root.get("custom_index", 0) or 0)
            provider = provider[index] if 0 <= index < len(provider) else {}
        if not isinstance(provider, dict):
            return "图片生成 API 配置格式错误"
        if img_type == "comfyui":
            if not _has_value(provider.get("api_base")):
                return "ComfyUI 地址未配置"
            return ""
        if not _has_value(provider.get("api_base")):
            return "图片生成 API URL 未配置"
        if not _has_value(config.img_api_key):
            return "图片生成 API Key 未配置"
        if not _has_value(provider.get("model")):
            return "图片生成模型未选择"
    except Exception as exc:
        return f"图片生成配置读取失败: {exc}"
    return ""


async def run_task_preflight(task, *, live_wechat: bool = True) -> dict:
    config = Config.get_instance()
    profiles = AccountProfileService(config)
    profile, binding_status, binding_message = profiles.resolve_task_account(task)
    mode = str(getattr(task, "account_binding_mode", None) or "fixed")
    post_action = str(getattr(task, "post_action", None) or "publish")

    if mode != "none" and binding_status in {"missing_default", "missing_account", "unconfigured", "disabled"}:
        return {
            "ok": False,
            "status": "error",
            "message": binding_message,
            "binding_status": binding_status,
            "profile": profile,
        }
    if post_action in {"save", "publish"} and not profile:
        return {
            "ok": False,
            "status": "error",
            "message": "存草稿或正式发布必须绑定公众号",
            "binding_status": binding_status,
            "profile": None,
        }

    llm_error = _llm_config_error(config)
    if llm_error:
        return {"ok": False, "status": "error", "message": llm_error, "binding_status": binding_status, "profile": profile}

    if getattr(task, "use_ai_beautify", True):
        image_error = _image_config_error(config)
        if image_error:
            return {"ok": False, "status": "error", "message": image_error, "binding_status": binding_status, "profile": profile}

    if live_wechat and post_action in {"save", "publish"} and profile:
        from src.ai_write_x.web.api.config import WechatCredentialTest, test_wechat_credential

        result = await test_wechat_credential(
            WechatCredentialTest(appid=str(profile.get("appid") or ""), appsecret=str(profile.get("appsecret") or ""))
        )
        result_status = result.get("status", "error")
        if result_status == "error":
            return {
                "ok": False,
                "status": "error",
                "message": result.get("message") or "公众号连接验证失败",
                "binding_status": binding_status,
                "profile": profile,
            }
        is_verified = bool((result.get("details") or {}).get("is_verified"))
        if post_action == "publish" and (
            profile.get("draft_only", False)
            or result_status == "warning"
            or not is_verified
        ):
            return {
                "ok": False,
                "status": "error",
                "message": "未确认该公众号具备认证发布能力，仅支持保存草稿，不能执行正式发布",
                "binding_status": binding_status,
                "profile": profile,
            }

    return {
        "ok": True,
        "status": "ok",
        "message": "执行前检查通过",
        "binding_status": binding_status,
        "profile": profile,
        "checked_at": datetime.now(),
    }


def save_preflight_result(task, result: dict, *, pause_on_error: bool = True) -> None:
    from src.ai_write_x.core import task_status

    task.preflight_status = result.get("status", "error")
    task.preflight_message = result.get("message") or ""
    task.preflight_checked_at = datetime.now()
    if pause_on_error and not result.get("ok"):
        task.status = task_status.DISABLED
    task.updated_at = datetime.now()
    task.save()
