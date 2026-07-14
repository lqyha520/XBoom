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
        if not normalized_credentials:
            normalized, _ = self._normalize({}, 0)
            normalized_credentials.append(normalized)
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
        return result

    def list_public(self) -> list[dict]:
        return [self.public_profile(item) for item in self.list_raw()]

    def bound_task_count(self, profile: dict) -> int:
        try:
            from src.ai_write_x.database.db_manager import db_manager

            account_id = profile.get("account_id")
            appid = profile.get("appid")
            return sum(
                1
                for task in db_manager.get_all_tasks()
                if getattr(task, "target_account_id", None) == account_id
                or (not getattr(task, "target_account_id", None) and getattr(task, "target_appid", None) == appid)
            )
        except Exception:
            return 0

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
