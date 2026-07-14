import json
import tomllib
from pathlib import Path

from scripts.run_quick_tests import CORE_TESTS
from src.ai_write_x.version import get_version


ROOT = Path(__file__).resolve().parents[1]


def test_quick_gate_only_references_existing_tests():
    missing = [path for path in CORE_TESTS if not (ROOT / path).is_file()]
    assert missing == []


def test_release_version_is_consistent_across_primary_metadata():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    policy = json.loads((ROOT / "version-policy.json").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == get_version()
    assert policy["latest_version"] == get_version()


def test_dashboard_does_not_ship_fake_business_metrics():
    dashboard_js = (
        ROOT / "src" / "ai_write_x" / "web" / "static" / "js" / "dashboard-manager.js"
    ).read_text(encoding="utf-8")
    dashboard_html = (
        ROOT / "src" / "ai_write_x" / "web" / "templates" / "components" / "views" / "dashboard.html"
    ).read_text(encoding="utf-8")

    assert "value: [98, 95, 99, 97, 88, 92]" not in dashboard_js
    assert "Math.floor(Math.random() * 15 + 5)" not in dashboard_js
    assert "+12.5%" not in dashboard_html
    assert "+8.3%" not in dashboard_html


def test_wechat_settings_are_the_single_account_management_entry():
    index = (ROOT / "src" / "ai_write_x" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    sidebar = (ROOT / "src" / "ai_write_x" / "web" / "templates" / "components" / "sidebar.html").read_text(encoding="utf-8")
    config_js = (ROOT / "src" / "ai_write_x" / "web" / "static" / "js" / "config-manager.js").read_text(encoding="utf-8")

    assert "components/views/account-manager.html" not in index
    assert "/static/js/account-manager.js" not in index
    assert "/static/css/views/account-manager.css" not in index
    assert 'data-view="account-manager"' not in sidebar
    assert "...(credentials[index] || {})" in config_js
    assert "wechat-brand-voice-" in config_js
