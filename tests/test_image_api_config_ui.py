from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src/ai_write_x/web/templates/components/views/config-manager/panels/img-api-config.html"
SCRIPT = ROOT / "src/ai_write_x/web/static/js/config-manager.js"
STYLES = ROOT / "src/ai_write_x/web/static/css/views/config-manager.css"


def test_image_api_page_uses_compact_pipeline_layout():
    template = TEMPLATE.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")

    assert "img-api-page-header" in template
    assert "IMAGE PIPELINE" in template
    assert "密钥仅保存在本机" in template
    assert '<details class="img-api-settings-panel">' in template
    assert "#config-img-api .img-api-section-config" in styles


def test_image_api_config_uses_url_key_model_order():
    script = SCRIPT.read_text(encoding="utf-8")
    builtin = script.split("// 创建图片API提供商卡片", 1)[1].split("// 获取内置图片 API", 1)[0]

    assert "img-config-step-url" in builtin
    assert "img-config-step-key" in builtin
    assert "img-config-step-model" in builtin
    assert builtin.index("configBody.appendChild(baseUrlGroup)") < builtin.index("configBody.appendChild(keyField)")
    assert builtin.index("configBody.appendChild(keyField)") < builtin.index("configBody.appendChild(modelGroup)")


def test_removed_fast_mode_fields_are_not_rendered():
    script = SCRIPT.read_text(encoding="utf-8")
    build_form = script.split("buildImgAPISettingsForm()", 1)[1].split("return wrap;", 1)[0]

    assert "极速超时" not in build_form
    assert "img-api-settings-fast-timeout" not in build_form


def test_manual_model_input_is_collapsed_and_select_stays_in_sync():
    script = SCRIPT.read_text(encoding="utf-8")

    assert "toggleImgManualModelInput" in script
    assert "手动填写模型名" in script
    assert "hidden id=\"img-api-${providerKey}-model-input\"" in script
    assert "document.getElementById('img-api-${providerKey}-model-input').value = this.value" in script


def test_image_api_url_preview_matches_v1_normalization():
    script = SCRIPT.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")

    assert "normalizeImgAPIBaseURL" in script
    assert "buildImgAPIEndpoint" in script
    assert "attachImgAPIURLPreview" in script
    assert "已自动补 /v1" in script
    assert "grid-template-columns: minmax(0, 1.5fr)" in styles
