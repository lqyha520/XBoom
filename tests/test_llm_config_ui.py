from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src/ai_write_x/web/templates/components/views/config-manager/panels/api-config.html"
SCRIPT = ROOT / "src/ai_write_x/web/static/js/config-manager.js"
STYLES = ROOT / "src/ai_write_x/web/static/css/views/config-manager.css"


def test_llm_api_page_uses_compact_gateway_layout():
    template = TEMPLATE.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")

    assert "llm-api-page-header" in template
    assert "MODEL GATEWAY" in template
    assert "密钥仅保存在本机" in template
    assert "#config-api .llm-api-form" in styles
    assert "grid-template-columns: minmax(0, 1.08fr)" in styles
    assert "api-section-config" in styles
    assert "api-config-step-url" in styles
    assert "grid-template-columns: minmax(0, 1.55fr)" in styles


def test_llm_api_key_display_is_masked_by_default():
    script = SCRIPT.read_text(encoding="utf-8")

    assert "formatItemLabel" in script
    assert "密钥 ${index + 1}  ····${suffix}" in script
    assert "display.classList.add('is-secret')" in script
    assert "option.textContent = formatItemLabel(item, index)" in script


def test_llm_model_config_uses_url_key_model_order_without_key_name():
    script = SCRIPT.read_text(encoding="utf-8")

    compact_branch = script.split("if (compactToolbar) {", 1)[1].split("} else {", 1)[0]
    assert compact_branch.index("baseOnlyRow") < compact_branch.index("keyOnlyRow")
    assert compact_branch.index("keyOnlyRow") < compact_branch.index("modelRow")
    assert "configSec.body.appendChild(baseOnlyRow)" in compact_branch
    assert "configSec.body.appendChild(keyOnlyRow)" in compact_branch
    assert "configSec.body.appendChild(modelRow)" in compact_branch
    assert "configSec.body.appendChild(row1)" not in compact_branch
    assert "api-url-hint" in script
