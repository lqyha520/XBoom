"""Account matrix profiles backed by the existing WeChat credential config."""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Any

from src.ai_write_x.config.config import Config


PROFILE_DEFAULTS = {
    "platform": "wechat",
    "name": "",
    "author": "",
    "enabled": True,
    "niche": "",
    "audience": "",
    "brand_voice": "",
    "forbidden_words": [],
    "signature": "",
    "default_template_category": "",
    "default_template": "",
    "health_status": "unchecked",
    "health_message": "尚未检测",
    "last_checked_at": "",
    "draft_only": False,
    "call_sendall": False,
    "sendall": True,
    "tag_id": 0,
}


class AccountProfileService:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config.get_instance()

    def _credentials(self) -> list[dict]:
        root = self.config.config.setdefault("wechat", {})
        credentials = root.setdefault("credentials", [])
        if not isinstance(credentials, list):
            credentials = []
            root["credentials"] = credentials
        return credentials

    def _wechat_root(self) -> dict:
        return self.config.config.setdefault("wechat", {})

    @staticmethod
    def _account_id(credential: dict, index: int) -> str:
        existing = str(credential.get("account_id") or "").strip()
        if existing:
            return existing
        appid = str(credential.get("appid") or "").strip()
        if appid:
            return str(uuid.uuid5(uuid.NAMESPACE_URL, f"xboom:wechat:{appid}"))
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"xboom:wechat:slot:{index}"))

    def _normalize(self, credential: dict, index: int) -> tuple[dict, bool]:
        original = copy.deepcopy(credential)
        normalized = {**PROFILE_DEFAULTS, **(credential or {})}
        normalized["account_id"] = self._account_id(normalized, index)
        normalized["platform"] = "wechat"
        normalized["name"] = str(
            normalized.get("name") or normalized.get("author") or f"公众号 {index + 1}"
        ).strip()
        normalized["author"] = str(normalized.get("author") or normalized["name"]).strip()
        normalized["enabled"] = True
        normalized.pop("default_post_action", None)
        words = normalized.get("forbidden_words") or []
        if isinstance(words, str):
            words = [item.strip() for item in words.replace("，", ",").split(",") if item.strip()]
        normalized["forbidden_words"] = list(dict.fromkeys(str(item).strip() for item in words if str(item).strip()))
        return normalized, normalized != original

    def migrate(self) -> bool:
        credentials = self._credentials()
        changed = False
        normalized_credentials = []
        for index, credential in enumerate(credentials):
            normalized, item_changed = self._normalize(credential or {}, index)
            normalized_credentials.append(normalized)
            changed = changed or item_changed
        usable_ids = [
            item.get("account_id") for item in normalized_credentials
            if item.get("enabled", True) and item.get("appid") and item.get("appsecret")
        ]
        root = self._wechat_root()
        current_default = str(root.get("default_account_id") or "").strip()
        next_default = current_default if current_default in usable_ids else (usable_ids[0] if usable_ids else "")
        if current_default != next_default or "default_account_id" not in root:
            root["default_account_id"] = next_default
            changed = True
        if changed:
            self.config.config["wechat"]["credentials"] = normalized_credentials
            self.config.save_config(self.config.config)
        return changed

    def list_raw(self) -> list[dict]:
        self.migrate()
        return self._credentials()

    def get_raw(self, account_id: str) -> dict | None:
        return next(
            (item for item in self.list_raw() if item.get("account_id") == account_id),
            None,
        )

    def get_by_appid(self, appid: str) -> dict | None:
        return next(
            (item for item in self.list_raw() if str(item.get("appid") or "") == str(appid or "")),
            None,
        )

    def get_default_account_id(self) -> str:
        self.migrate()
        return str(self._wechat_root().get("default_account_id") or "").strip()

    def get_default(self) -> dict | None:
        account_id = self.get_default_account_id()
        return self.get_raw(account_id) if account_id else None

    def set_default(self, account_id: str) -> dict:
        profile = self.get_raw(account_id)
        if not profile:
            raise KeyError(account_id)
        if not profile.get("appid") or not profile.get("appsecret"):
            raise ValueError("公众号 AppID 或 AppSecret 未配置完整")
        root = self._wechat_root()
        previous_default = root.get("default_account_id", "")
        root["default_account_id"] = account_id
        if not self.config.save_config(self.config.config):
            root["default_account_id"] = previous_default
            raise RuntimeError(self.config.error_message or "默认公众号保存失败")
        return profile

    def resolve_task_account(self, task) -> tuple[dict | None, str, str]:
        mode = str(getattr(task, "account_binding_mode", None) or "fixed")
        if mode == "none":
            return None, "none", "不绑定公众号"
        if mode == "default":
            profile = self.get_default()
            if not profile:
                return None, "missing_default", "尚未设置可用的默认公众号"
            status, message = self.status_for(profile)
            if status == "disabled":
                return profile, "disabled", message
            if status == "unconfigured":
                return profile, "unconfigured", message
            return profile, "following_default", "跟随默认公众号"

        account_id = str(getattr(task, "target_account_id", None) or "").strip()
        appid = str(getattr(task, "target_appid", None) or "").strip()
        profile = self.get_raw(account_id) if account_id else None
        if not profile and appid:
            profile = self.get_by_appid(appid)
        if not profile:
            return None, "missing_account", "原公众号已删除"
        status, message = self.status_for(profile)
        if status == "disabled":
            return profile, "disabled", message
        if status == "unconfigured":
            return profile, "unconfigured", message
        return profile, "fixed", "固定绑定"

    @staticmethod
    def status_for(profile: dict) -> tuple[str, str]:
        if not profile.get("enabled", True):
            return "disabled", "账号已暂停"
        if not profile.get("appid") or not profile.get("appsecret"):
            return "unconfigured", "AppID 或 AppSecret 未配置"
        status = str(profile.get("health_status") or "unchecked")
        message = str(profile.get("health_message") or "尚未检测")
        return status, message

    def public_profile(self, profile: dict) -> dict:
        status, message = self.status_for(profile)
        result = copy.deepcopy(profile)
        result.pop("appsecret", None)
        result["has_secret"] = bool(profile.get("appsecret"))
        result["status"] = status
        result["status_message"] = message
        result["bound_tasks"] = self.bound_task_count(profile)
        result["is_default"] = profile.get("account_id") == self.get_default_account_id()
        return result

    def list_public(self) -> list[dict]:
        return [self.public_profile(item) for item in self.list_raw()]

    def bound_task_count(self, profile: dict) -> int:
        try:
            from src.ai_write_x.database.db_manager import db_manager

            account_id = profile.get("account_id")
            appid = profile.get("appid")
            is_default = account_id == self.get_default_account_id()
            count = 0
            for task in db_manager.get_all_tasks():
                mode = str(getattr(task, "account_binding_mode", None) or "fixed")
                if mode == "default" and is_default:
                    count += 1
                elif mode == "fixed" and (
                    getattr(task, "target_account_id", None) == account_id
                    or (not getattr(task, "target_account_id", None) and getattr(task, "target_appid", None) == appid)
                ):
                    count += 1
            return count
        except Exception:
            return 0

    def delete_impact(self, account_id: str) -> dict:
        profile = self.get_raw(account_id)
        if not profile:
            raise KeyError(account_id)
        fixed_task_ids = []
        default_task_ids = []
        from src.ai_write_x.database.db_manager import db_manager

        for task in db_manager.get_all_tasks():
            mode = str(getattr(task, "account_binding_mode", None) or "fixed")
            if mode == "fixed" and (
                getattr(task, "target_account_id", None) == account_id
                or (not getattr(task, "target_account_id", None)
                    and getattr(task, "target_appid", None) == profile.get("appid"))
            ):
                fixed_task_ids.append(str(task.id))
            elif mode == "default" and account_id == self.get_default_account_id():
                default_task_ids.append(str(task.id))
        task_ids = list(dict.fromkeys(fixed_task_ids + default_task_ids))
        active_statuses = {"running", "cancel_requested"}
        running_tasks = sum(
            1 for task in db_manager.get_all_tasks()
            if str(task.id) in task_ids and getattr(task, "status", "") in active_statuses
        )
        return {
            "account_id": account_id,
            "name": profile.get("name") or profile.get("author") or "未命名公众号",
            "is_default": account_id == self.get_default_account_id(),
            "fixed_tasks": len(fixed_task_ids),
            "default_tasks": len(default_task_ids),
            "affected_tasks": len(task_ids),
            "running_tasks": running_tasks,
            "task_ids": task_ids,
        }

    def safe_delete(self, account_id: str) -> dict:
        impact = self.delete_impact(account_id)
        if impact.get("running_tasks"):
            raise ValueError("仍有相关定时任务正在运行，请先取消任务后再删除公众号")
        from src.ai_write_x.core import task_status
        from src.ai_write_x.database.models import ScheduledTask

        pause_message = "绑定公众号已删除，请重新选择或确认新默认公众号"
        root = self._wechat_root()
        previous_credentials = copy.deepcopy(root.get("credentials", []))
        previous_default = root.get("default_account_id", "")
        credentials = [item for item in self.list_raw() if item.get("account_id") != account_id]
        root["credentials"] = credentials
        if impact["is_default"]:
            usable = [
                item for item in credentials
                if item.get("enabled", True) and item.get("appid") and item.get("appsecret")
            ]
            root["default_account_id"] = usable[0].get("account_id") if usable else ""
        if not self.config.save_config(self.config.config):
            root["credentials"] = previous_credentials
            root["default_account_id"] = previous_default
            raise RuntimeError(self.config.error_message or "公众号删除失败")

        task_snapshots = []
        paused = 0
        try:
            for task_id in impact["task_ids"]:
                task = ScheduledTask.get_by_id(task_id)
                if not task:
                    continue
                task_snapshots.append((
                    task,
                    task.status,
                    getattr(task, "preflight_status", None),
                    getattr(task, "preflight_message", None),
                    getattr(task, "preflight_checked_at", None),
                    getattr(task, "updated_at", None),
                ))
                task.status = task_status.DISABLED
                task.preflight_status = "error"
                task.preflight_message = pause_message
                task.preflight_checked_at = datetime.now()
                task.updated_at = datetime.now()
                task.save()
                paused += 1
        except Exception:
            for task, status, preflight_status, preflight_message, checked_at, updated_at in reversed(task_snapshots):
                task.status = status
                task.preflight_status = preflight_status
                task.preflight_message = preflight_message
                task.preflight_checked_at = checked_at
                task.updated_at = updated_at
                try:
                    task.save()
                except Exception:
                    pass
            root["credentials"] = previous_credentials
            root["default_account_id"] = previous_default
            self.config.save_config(self.config.config)
            raise
        return {
            **impact,
            "paused_tasks": paused,
            "default_account_id": root.get("default_account_id") or "",
        }

    def save(self, data: dict, account_id: str | None = None) -> dict:
        credentials = self.list_raw()
        existing = self.get_raw(account_id) if account_id else None
        profile = copy.deepcopy(existing or {})
        incoming = copy.deepcopy(data)
        secret = incoming.pop("appsecret", None)
        profile.update(incoming)
        if secret and "***" not in str(secret):
            profile["appsecret"] = str(secret).strip()
        elif existing:
            profile["appsecret"] = existing.get("appsecret", "")
        profile["account_id"] = account_id or str(uuid.uuid4())
        normalized, _ = self._normalize(profile, len(credentials))

        appid = str(normalized.get("appid") or "").strip()
        if appid and any(
            item.get("account_id") != normalized["account_id"]
            and str(item.get("appid") or "").strip() == appid
            for item in credentials
        ):
            raise ValueError("该 AppID 已绑定到其他账号档案")

        if existing:
            index = credentials.index(existing)
            credentials[index] = normalized
        else:
            credentials.append(normalized)
        self.config.config["wechat"]["credentials"] = credentials
        if not self.config.save_config(self.config.config):
            raise RuntimeError(self.config.error_message or "账号档案保存失败")
        return normalized

    def delete(self, account_id: str, *, force: bool = False) -> None:
        profile = self.get_raw(account_id)
        if not profile:
            raise KeyError(account_id)
        if self.bound_task_count(profile) and not force:
            raise RuntimeError("账号仍被定时任务绑定，请先调整任务或使用强制删除")
        credentials = [item for item in self.list_raw() if item.get("account_id") != account_id]
        self.config.config["wechat"]["credentials"] = credentials
        if not self.config.save_config(self.config.config):
            raise RuntimeError(self.config.error_message or "账号档案删除失败")

    def update_health(self, account_id: str, status: str, message: str) -> dict:
        profile = self.get_raw(account_id)
        if not profile:
            raise KeyError(account_id)
        profile["health_status"] = status
        profile["health_message"] = message
        profile["last_checked_at"] = datetime.now(timezone.utc).isoformat()
        self.config.save_config(self.config.config)
        return profile

    @staticmethod
    def brand_prompt(profile: dict | None) -> str:
        if not profile:
            return ""
        parts = [f"【目标账号】{profile.get('name') or profile.get('author') or '未命名账号'}"]
        mapping = (
            ("niche", "账号定位"),
            ("audience", "目标读者"),
            ("brand_voice", "品牌语气"),
            ("signature", "固定署名/口头禅"),
        )
        for key, label in mapping:
            value = str(profile.get(key) or "").strip()
            if value:
                parts.append(f"【{label}】{value}")
        forbidden = profile.get("forbidden_words") or []
        if forbidden:
            parts.append(f"【禁用表达】不得使用：{'、'.join(forbidden)}")
        parts.append("写作时必须服从以上账号定位，但不要在正文中解释这些规则。")
        return "\n".join(parts)
