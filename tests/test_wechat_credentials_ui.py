from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "src/ai_write_x/web/static/js/config-manager.js"
STYLES = ROOT / "src/ai_write_x/web/static/css/views/config-manager.css"


def test_all_wechat_credentials_can_be_deleted_and_empty_state_is_rendered():
    script = SCRIPT.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")

    assert "deleteBtn.disabled = index === 0" not in script
    assert "wechat-credentials-empty" in script
    assert "暂未配置公众号" in script
    assert ".wechat-credentials-empty" in styles
