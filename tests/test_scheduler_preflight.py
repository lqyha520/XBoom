import asyncio
from types import SimpleNamespace

from src.ai_write_x.config.config import Config
from src.ai_write_x.core.scheduler_preflight import run_task_preflight, save_preflight_result


class FakeRuntimeConfig:
    def __init__(self, credentials):
        self.config = {
            "wechat": {"credentials": credentials},
            "img_api": {"api_type": "picsum", "picsum": {}},
        }
        self.error_message = ""
        self.api_apibase = "https://api.example.com/v1"
        self.api_type = "Custom"
        self.api_key = "key"
        self.api_model = "model"
        self.img_api_type = "picsum"

    def save_config(self, config, *args):
        self.config = config
        return True


def _task(**overrides):
    values = {
        "account_binding_mode": "default",
        "target_account_id": None,
        "target_appid": None,
        "post_action": "none",
        "use_ai_beautify": False,
        "status": "enabled",
        "saved": 0,
    }
    values.update(overrides)
    task = SimpleNamespace(**values)
    task.save = lambda: setattr(task, "saved", task.saved + 1)
    return task


def test_lightweight_preflight_resolves_default_account(monkeypatch):
    config = FakeRuntimeConfig([
        {"account_id": "default", "name": "默认号", "appid": "wxdefault", "appsecret": "secret"}
    ])
    monkeypatch.setattr(Config, "get_instance", classmethod(lambda cls: config))

    result = asyncio.run(run_task_preflight(_task(), live_wechat=False))

    assert result["ok"] is True
    assert result["binding_status"] == "following_default"
    assert result["profile"]["account_id"] == "default"


def test_preflight_failure_pauses_task(monkeypatch):
    config = FakeRuntimeConfig([])
    monkeypatch.setattr(Config, "get_instance", classmethod(lambda cls: config))
    task = _task()

    result = asyncio.run(run_task_preflight(task, live_wechat=False))
    save_preflight_result(task, result, pause_on_error=True)

    assert result["ok"] is False
    assert task.status == "disabled"
    assert task.preflight_status == "error"
    assert task.preflight_message
    assert task.saved == 1


def test_unverified_account_cannot_preflight_direct_publish(monkeypatch):
    config = FakeRuntimeConfig([
        {"account_id": "default", "name": "默认号", "appid": "wxdefault", "appsecret": "secret"}
    ])
    monkeypatch.setattr(Config, "get_instance", classmethod(lambda cls: config))
    from src.ai_write_x.web.api import config as config_api

    async def fake_test(_credential):
        return {"status": "warning", "message": "未认证，仅支持草稿"}

    monkeypatch.setattr(config_api, "test_wechat_credential", fake_test)
    result = asyncio.run(run_task_preflight(_task(post_action="publish"), live_wechat=True))

    assert result["ok"] is False
    assert "不能执行正式发布" in result["message"]


def test_publish_requires_explicit_verified_capability(monkeypatch):
    config = FakeRuntimeConfig([
        {"account_id": "default", "name": "默认号", "appid": "wxdefault", "appsecret": "secret"}
    ])
    monkeypatch.setattr(Config, "get_instance", classmethod(lambda cls: config))
    from src.ai_write_x.web.api import config as config_api

    async def fake_unconfirmed(_credential):
        return {"status": "success", "message": "凭证有效", "details": {"is_verified": False}}

    monkeypatch.setattr(config_api, "test_wechat_credential", fake_unconfirmed)
    result = asyncio.run(run_task_preflight(_task(post_action="publish"), live_wechat=True))
    assert result["ok"] is False

    async def fake_verified(_credential):
        return {"status": "success", "message": "已认证", "details": {"is_verified": True}}

    monkeypatch.setattr(config_api, "test_wechat_credential", fake_verified)
    result = asyncio.run(run_task_preflight(_task(post_action="publish"), live_wechat=True))
    assert result["ok"] is True


def test_draft_only_profile_cannot_preflight_direct_publish(monkeypatch):
    config = FakeRuntimeConfig([
        {
            "account_id": "default",
            "name": "默认号",
            "appid": "wxdefault",
            "appsecret": "secret",
            "draft_only": True,
        }
    ])
    monkeypatch.setattr(Config, "get_instance", classmethod(lambda cls: config))
    from src.ai_write_x.web.api import config as config_api

    async def fake_verified(_credential):
        return {"status": "success", "message": "已认证", "details": {"is_verified": True}}

    monkeypatch.setattr(config_api, "test_wechat_credential", fake_verified)
    result = asyncio.run(run_task_preflight(_task(post_action="publish"), live_wechat=True))

    assert result["ok"] is False
    assert "仅支持保存草稿" in result["message"]
