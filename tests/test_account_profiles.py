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


def test_single_configured_account_rebinds_stale_scheduled_tasks(monkeypatch):
    service = AccountProfileService(FakeConfig([
        {"account_id": "new-account", "name": "new", "appid": "wxnew", "appsecret": "secret"}
    ]))
    task = SimpleNamespace(
        target_account_id="old-account",
        target_appid="wxold",
        updated_at=None,
        saved=0,
    )
    task.save = lambda: setattr(task, "saved", task.saved + 1)
    unbound_task = SimpleNamespace(
        target_account_id=None,
        target_appid=None,
        updated_at=None,
        saved=0,
    )
    unbound_task.save = lambda: setattr(unbound_task, "saved", unbound_task.saved + 1)
    monkeypatch.setattr(db_manager, "get_all_tasks", lambda: [task, unbound_task])

    assert service.rebind_all_tasks_to_single_account() == 2
    assert task.target_account_id == "new-account"
    assert task.target_appid == "wxnew"
    assert task.saved == 1
    assert unbound_task.target_account_id == "new-account"
    assert unbound_task.target_appid == "wxnew"
    assert unbound_task.saved == 1
