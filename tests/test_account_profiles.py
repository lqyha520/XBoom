from src.ai_write_x.core.account_profiles import AccountProfileService
from src.ai_write_x.database.db_manager import db_manager
from pathlib import Path
from types import SimpleNamespace


class FakeConfig:
    def __init__(self, credentials):
        self.config = {"wechat": {"credentials": credentials}}
        self.error_message = ""
        self.saved = 0

    def save_config(self, config):
        self.config = config
        self.saved += 1
        return True


def test_existing_wechat_credentials_migrate_without_losing_publish_settings():
    config = FakeConfig([
        {
            "appid": "wx123",
            "appsecret": "secret",
            "author": "科技号",
            "draft_only": True,
            "sendall": False,
        }
    ])
    service = AccountProfileService(config)
    service.migrate()
    profile = service.list_raw()[0]

    assert profile["account_id"]
    assert profile["name"] == "科技号"
    assert profile["draft_only"] is True
    assert profile["sendall"] is False
    assert profile["brand_voice"] == ""


def test_public_profile_hides_secret_and_reports_configuration_status():
    service = AccountProfileService(FakeConfig([]))
    profile = service.save({"name": "职场号", "appid": "wxabc", "appsecret": "top-secret"})
    public = service.public_profile(profile)

    assert "appsecret" not in public
    assert public["has_secret"] is True
    assert public["status"] == "unchecked"


def test_brand_prompt_contains_account_positioning_and_forbidden_words():
    prompt = AccountProfileService.brand_prompt({
        "name": "财经观察",
        "niche": "宏观财经解读",
        "audience": "普通投资者",
        "brand_voice": "谨慎、数据驱动，不承诺收益",
        "forbidden_words": ["稳赚", "保本"],
        "signature": "投资有风险",
    })

    assert "财经观察" in prompt
    assert "宏观财经解读" in prompt
    assert "普通投资者" in prompt
    assert "稳赚、保本" in prompt
    assert "投资有风险" in prompt


def test_duplicate_appid_is_rejected():
    service = AccountProfileService(FakeConfig([]))
    service.save({"name": "账号一", "appid": "wxduplicate", "appsecret": "a"})

    try:
        service.save({"name": "账号二", "appid": "wxduplicate", "appsecret": "b"})
    except ValueError as exc:
        assert "已绑定" in str(exc)
    else:
        raise AssertionError("duplicate appid should be rejected")


def test_updating_profile_with_blank_secret_preserves_existing_secret():
    service = AccountProfileService(FakeConfig([]))
    created = service.save({"name": "账号", "appid": "wxkeep", "appsecret": "keep-me"})
    updated = service.save(
        {"name": "新名称", "appid": "wxkeep", "appsecret": "", "brand_voice": "亲切"},
        created["account_id"],
    )

    assert updated["appsecret"] == "keep-me"
    assert updated["brand_voice"] == "亲切"


def test_account_matrix_ui_is_removed_and_profile_fields_live_in_wechat_settings():
    root = Path(__file__).resolve().parents[1]
    index = (root / "src/ai_write_x/web/templates/index.html").read_text(encoding="utf-8")
    sidebar = (root / "src/ai_write_x/web/templates/components/sidebar.html").read_text(encoding="utf-8")
    config_script = (root / "src/ai_write_x/web/static/js/config-manager.js").read_text(encoding="utf-8")
    config_css = (
        root / "src/ai_write_x/web/static/css/views/config-manager.css"
    ).read_text(encoding="utf-8")
    wechat_template = (
        root / "src/ai_write_x/web/templates/components/views/config-manager/panels/wechat-config.html"
    ).read_text(encoding="utf-8")

    assert "account-manager" not in index
    assert "账号矩阵" not in sidebar
    assert not (root / "src/ai_write_x/web/static/js/account-manager.js").exists()
    for field in (
        "wechat-name-", "wechat-niche-", "wechat-audience-",
        "wechat-brand-voice-", "wechat-forbidden-words-", "wechat-signature-",
    ):
        assert field in config_script
    assert "wechat-enabled-" not in config_script
    assert "wechat-default-action-" not in config_script
    assert "统一管理公众号凭证、账号定位、品牌语气和发布方式" in wechat_template
    assert "credential-main-grid" in config_script
    assert "credential-section-header" in config_script
    assert "credential-avatar" in config_script
    assert ".credential-main-grid" in config_css
    assert ".publish-section .publishing-controls-row" in config_css


def test_default_and_fixed_task_bindings_are_resolved_explicitly():
    service = AccountProfileService(FakeConfig([
        {"account_id": "new-account", "name": "new", "appid": "wxnew", "appsecret": "secret"}
    ]))
    default_task = SimpleNamespace(
        account_binding_mode="default",
        target_account_id=None,
        target_appid=None,
    )
    fixed_task = SimpleNamespace(
        account_binding_mode="fixed",
        target_account_id="old-account",
        target_appid="wxold",
    )

    profile, status, _ = service.resolve_task_account(default_task)
    assert profile["account_id"] == "new-account"
    assert status == "following_default"
    profile, status, _ = service.resolve_task_account(fixed_task)
    assert profile is None
    assert status == "missing_account"


def test_safe_delete_pauses_affected_tasks_and_moves_default(monkeypatch):
    config = FakeConfig([
        {"account_id": "account-a", "name": "A", "appid": "wxa", "appsecret": "secret-a"},
        {"account_id": "account-b", "name": "B", "appid": "wxb", "appsecret": "secret-b"},
    ])
    service = AccountProfileService(config)
    service.migrate()
    assert service.get_default_account_id() == "account-a"

    tasks = [
        SimpleNamespace(id="fixed-a", account_binding_mode="fixed", target_account_id="account-a", target_appid="wxa", status="enabled", saved=0),
        SimpleNamespace(id="follow-default", account_binding_mode="default", target_account_id=None, target_appid=None, status="enabled", saved=0),
        SimpleNamespace(id="fixed-b", account_binding_mode="fixed", target_account_id="account-b", target_appid="wxb", status="enabled", saved=0),
    ]
    for task in tasks:
        task.save = lambda task=task: setattr(task, "saved", task.saved + 1)

    monkeypatch.setattr(db_manager, "get_all_tasks", lambda: tasks)
    from src.ai_write_x.database.models import ScheduledTask
    monkeypatch.setattr(ScheduledTask, "get_by_id", staticmethod(lambda task_id: next((t for t in tasks if t.id == task_id), None)))

    result = service.safe_delete("account-a")

    assert result["paused_tasks"] == 2
    assert service.get_default_account_id() == "account-b"
    assert tasks[0].status == "disabled"
    assert tasks[1].status == "disabled"
    assert tasks[2].status == "enabled"
    assert "绑定公众号已删除" in tasks[0].preflight_message


def test_safe_delete_does_not_pause_tasks_when_config_save_fails(monkeypatch):
    config = FakeConfig([
        {"account_id": "account-a", "name": "A", "appid": "wxa", "appsecret": "secret-a"},
        {"account_id": "account-b", "name": "B", "appid": "wxb", "appsecret": "secret-b"},
    ])
    service = AccountProfileService(config)
    service.migrate()

    task = SimpleNamespace(
        id="fixed-a",
        account_binding_mode="fixed",
        target_account_id="account-a",
        target_appid="wxa",
        status="enabled",
        preflight_status="unchecked",
        preflight_message=None,
        preflight_checked_at=None,
        updated_at=None,
        saved=0,
    )
    task.save = lambda: setattr(task, "saved", task.saved + 1)
    monkeypatch.setattr(db_manager, "get_all_tasks", lambda: [task])
    from src.ai_write_x.database.models import ScheduledTask
    monkeypatch.setattr(ScheduledTask, "get_by_id", staticmethod(lambda _task_id: task))
    config.save_config = lambda _config: False

    try:
        service.safe_delete("account-a")
        assert False, "expected save failure"
    except RuntimeError:
        pass

    assert task.status == "enabled"
    assert task.saved == 0
    assert service._wechat_root()["default_account_id"] == "account-a"
    assert [item["account_id"] for item in service._wechat_root()["credentials"]] == ["account-a", "account-b"]
