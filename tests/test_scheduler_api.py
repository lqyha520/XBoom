import ast
import asyncio
from pathlib import Path


SCHEDULER_API = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "ai_write_x"
    / "web"
    / "api"
    / "scheduler.py"
)


def _route_paths() -> set[tuple[str, str]]:
    tree = ast.parse(SCHEDULER_API.read_text(encoding="utf-8"))
    routes: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if decorator.func.attr not in {"get", "post", "put", "delete"}:
                continue
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                routes.add((decorator.func.attr, decorator.args[0].value))
    return routes


def test_scheduler_exposes_task_lifecycle_routes():
    routes = _route_paths()
    assert ("get", "/tasks") in routes
    assert ("post", "/tasks") in routes
    assert ("put", "/tasks/{task_id}") in routes
    assert ("delete", "/tasks/{task_id}") in routes
    assert ("post", "/tasks/{task_id}/preflight") in routes


def test_generate_api_exposes_explicit_recovery_routes():
    generate_api = SCHEDULER_API.with_name("generate.py")
    tree = ast.parse(generate_api.read_text(encoding="utf-8"))
    routes = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                routes.add((decorator.func.attr, decorator.args[0].value))

    assert ("get", "/generate/recovery") in routes
    assert ("post", "/generate/recovery/restart") in routes


def test_account_list_api_is_read_only_after_settings_consolidation():
    accounts_api = SCHEDULER_API.with_name("accounts.py")
    tree = ast.parse(accounts_api.read_text(encoding="utf-8"))
    routes = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                if decorator.args and isinstance(decorator.args[0], ast.Constant):
                    routes.add((decorator.func.attr, decorator.args[0].value))
    assert ("get", "") in routes
    assert ("post", "") not in routes
    assert ("put", "/{account_id}") not in routes
    assert ("delete", "/{account_id}") not in routes
    assert ("post", "/{account_id}/check") not in routes


def test_scheduler_exposes_post_action_selector_and_api_field():
    root = SCHEDULER_API.parents[4]
    template = (
        root / "src/ai_write_x/web/templates/components/views/scheduler.html"
    ).read_text(encoding="utf-8")
    script = (
        root / "src/ai_write_x/web/static/js/scheduler-manager.js"
    ).read_text(encoding="utf-8")
    api_source = SCHEDULER_API.read_text(encoding="utf-8")
    assert 'id="task-post-action"' in template
    assert 'value="none"' in template
    assert 'value="save" selected' in template
    assert 'value="publish"' in template
    assert "post_action: postAction" in script
    assert 'post_action: str = "save"' in api_source


def test_scheduler_supports_repeat_modes_in_ui_and_api():
    root = SCHEDULER_API.parents[4]
    template = (root / "src/ai_write_x/web/templates/components/views/scheduler.html").read_text(encoding="utf-8")
    script = (root / "src/ai_write_x/web/static/js/scheduler-manager.js").read_text(encoding="utf-8")
    api_source = SCHEDULER_API.read_text(encoding="utf-8")
    assert 'id="task-repeat-mode"' in template
    assert 'value="once"' in template
    assert 'value="daily"' in template
    assert 'value="interval"' in template
    assert "repeat_mode: repeatMode" in script
    assert "toggleRepeatMode" in script
    assert "repeat_mode: Optional[str] = None" in api_source


def test_scheduler_exposes_and_submits_image_style():
    root = SCHEDULER_API.parents[4]
    template = (root / "src/ai_write_x/web/templates/components/views/scheduler.html").read_text(encoding="utf-8")
    script = (root / "src/ai_write_x/web/static/js/scheduler-manager.js").read_text(encoding="utf-8")
    api_source = SCHEDULER_API.read_text(encoding="utf-8")
    assert 'id="task-image-style"' in template
    assert 'value="premium_editorial"' in template
    assert 'value="oriental"' in template
    assert "image_style: imageStyle" in script
    assert 'image_style: str = "auto"' in api_source
    assert 'task.image_style = data.image_style' in api_source
    scheduler_source = (root / "src/ai_write_x/core/scheduler.py").read_text(encoding="utf-8")
    assert '"image_style": getattr(task, "image_style", "auto") or "auto"' in scheduler_source


def test_scheduler_refreshes_and_resolves_wechat_account_bindings():
    root = SCHEDULER_API.parents[4]
    template = (root / "src/ai_write_x/web/templates/components/views/scheduler.html").read_text(encoding="utf-8")
    script = (root / "src/ai_write_x/web/static/js/scheduler-manager.js").read_text(encoding="utf-8")
    config_script = (root / "src/ai_write_x/web/static/js/config-manager.js").read_text(encoding="utf-8")
    profile_source = (root / "src/ai_write_x/core/account_profiles.py").read_text(encoding="utf-8")
    scheduler_source = (root / "src/ai_write_x/core/scheduler.py").read_text(encoding="utf-8")
    preflight_source = (root / "src/ai_write_x/core/scheduler_preflight.py").read_text(encoding="utf-8")
    assert "fetchWechatCredentials()" in script
    assert "wechat-credentials-updated" in script
    assert "run_task_preflight" in scheduler_source
    assert "account_binding_mode" in preflight_source
    assert "wechat-credentials-updated" in config_script
    assert '"configured": bool(item.get("appid") and item.get("has_secret"))' in SCHEDULER_API.read_text(encoding="utf-8")
    assert "未配置 AppID" in script
    assert 'id="task-refresh-wechat"' in template
    assert "refreshWechatCredentials(true)" in template
    assert "cache: 'no-store'" in script
    assert "已删除公众号（请重新选择）" in script
    assert "resolve_task_account" in profile_source
    assert "default_account_id" in SCHEDULER_API.with_name("config.py").read_text(encoding="utf-8")
    assert "__default__" in template
    assert "__none__" in template
    assert "account_binding_mode" in script
    assert "preflightTask" in script
    assert "_credentialsFromConfig" in script
    assert "_mergeWechatCredentials" in script
    assert "/api/config?_=" in script
    assert "可分别固定绑定到不同任务" in script


def test_scheduler_wechat_credential_api_returns_every_configured_account(monkeypatch):
    from src.ai_write_x.core.account_profiles import AccountProfileService
    from src.ai_write_x.web.api.scheduler import get_wechat_credentials

    profiles = [
        {"account_id": "a", "name": "育儿号", "appid": "wxa", "has_secret": True, "enabled": True, "is_default": True},
        {"account_id": "b", "name": "职场号", "appid": "wxb", "has_secret": True, "enabled": True, "is_default": False},
        {"account_id": "c", "name": "生活号", "appid": "wxc", "has_secret": True, "enabled": True, "is_default": False},
    ]
    monkeypatch.setattr(AccountProfileService, "list_public", lambda self: profiles)

    result = asyncio.run(get_wechat_credentials())

    assert [item["account_id"] for item in result] == ["a", "b", "c"]
    assert [item["name"] for item in result] == ["育儿号", "职场号", "生活号"]
    assert result[0]["is_default"] is True
