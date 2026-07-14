from pathlib import Path

from src.ai_write_x.core import visual_assets
from src.ai_write_x.core.visual_assets import VisualAssetsManager


def test_auto_image_style_uses_topic_semantics():
    assert VisualAssetsManager.resolve_image_style("auto", "AI 芯片产业", "") == "minimal_3d"
    assert VisualAssetsManager.resolve_image_style("auto", "传统文化与古典诗词", "") == "oriental"
    assert VisualAssetsManager.resolve_image_style("auto", "社会新闻现场调查", "") == "documentary"
    assert VisualAssetsManager.resolve_image_style("auto", "职场沟通方法", "") == "premium_editorial"


def test_visual_translation_prompt_rejects_cheap_stock_imagery(monkeypatch):
    captured = {}

    class FakeLLM:
        def chat(self, messages, **kwargs):
            captured["messages"] = messages
            return (
                "A product designer adjusts a translucent processor prototype inside a quiet "
                "laboratory, framed at eye level with soft side lighting, matte surfaces, cool "
                "neutral colors, and layered depth behind the focused subject."
            )

    monkeypatch.setattr(visual_assets, "LLMClient", FakeLLM)
    VisualAssetsManager._visual_translation_cache.clear()

    result = VisualAssetsManager._translate_to_visual_english(
        "AI 芯片设计团队正在检查新产品",
        style_key="minimal_3d",
        is_cover=True,
    )

    prompt = captured["messages"][0]["content"]
    assert "premium minimal 3D editorial render" in prompt
    assert "企业握手照" in prompt
    assert "一个连贯瞬间" in prompt
    assert "product designer" in result


def test_scene_prompt_applies_selected_style_and_quality_negative(monkeypatch):
    monkeypatch.setattr(
        VisualAssetsManager,
        "_translate_to_visual_english",
        classmethod(
            lambda cls, text, max_retries=1, style_key="auto", is_cover=False: (
                "a focused editor reviewing printed photographs beside a studio window, "
                "natural side light, calm neutral palette, layered foreground and background"
            )
        ),
    )

    marker = VisualAssetsManager._build_scene_prompt(
        "职场成长",
        "负责人复盘项目交付",
        is_cover=True,
        style_key="premium_editorial",
    )

    assert "premium editorial photography" in marker
    assert "cheap stock photo" in marker
    assert "generic corporate handshake" in marker
    assert "2.35:1" in marker
    assert marker.index("a focused editor") < marker.index("premium editorial photography")


def test_storyboard_assigns_distinct_roles_and_contexts(monkeypatch):
    captured = []

    def fake_translate(cls, text, max_retries=1, style_key="auto", is_cover=False):
        captured.append(text)
        if "hero image" in text:
            return "one worried manager alone beside a stalled project timeline in a quiet corridor"
        if "problem scene" in text:
            return "an unopened package blocking a narrow workshop passage under hard side light"
        return "hands calibrating a small metal tool on a wooden bench in warm window light"

    monkeypatch.setattr(
        VisualAssetsManager,
        "_translate_to_visual_english",
        classmethod(fake_translate),
    )
    html = """
    <html><body><h1>项目为什么延期</h1>
    <p>跨部门项目在责任交接过程中经常出现严重的信息断层，相关人员无法及时确认交付标准，最终导致多个关键节点连续延误。</p>
    <h2>问题发生在哪里</h2><p>需求文件无人确认，交接物被搁置在流程中间。</p>
    <h2>如何推进解决</h2><p>负责人逐项检查工具和交付物，并完成现场校准。</p>
    </body></html>
    """
    result = VisualAssetsManager.inject_html_image_placeholders(
        html, "项目管理", "项目为什么延期", min_count=2, style_key="premium_editorial"
    )
    from bs4 import BeautifulSoup

    placeholders = BeautifulSoup(result, "html.parser").select(".img-placeholder")
    roles = [item.get("data-scene-role") for item in placeholders]
    prompts = [item.get("data-img-prompt") for item in placeholders]
    assert roles == ["cover", "problem", "process"]
    assert len(set(prompts)) == 3
    assert "对应段落：问题发生在哪里" in captured[1]
    assert "对应段落：如何推进解决" in captured[2]


def test_scene_similarity_discount_style_but_detects_repeated_subject():
    same_a = "premium editorial photography, a manager points at a board in a meeting room"
    same_b = "documentary photography, a manager points at a board in a meeting room"
    different = "premium editorial photography, close-up hands repair a bicycle chain outdoors"
    assert VisualAssetsManager._scene_prompt_similarity(same_a, same_b) > 0.7
    assert VisualAssetsManager._scene_prompt_similarity(same_a, different) < 0.6


def test_storyboard_rewrites_prompt_when_similarity_is_too_high(monkeypatch):
    calls = []

    def fake_translate(cls, text, max_retries=1, style_key="auto", is_cover=False):
        calls.append(text)
        return "one person working beside a desk in a quiet room with soft window light"

    monkeypatch.setattr(
        VisualAssetsManager,
        "_translate_to_visual_english",
        classmethod(fake_translate),
    )
    monkeypatch.setattr(
        VisualAssetsManager,
        "_scene_prompt_similarity",
        staticmethod(lambda left, right: 0.9),
    )
    html = """
    <html><body><h1>测试</h1>
    <p>这是一段长度足够的文章开头，用来建立封面场景并说明一个需要解决的具体问题和现实背景。</p>
    <h2>第一部分</h2><p>这里描述第一个步骤的具体行为和周围环境。</p>
    </body></html>
    """
    VisualAssetsManager.inject_html_image_placeholders(
        html, "测试主题", "测试标题", min_count=1, style_key="premium_editorial"
    )
    assert any("第一次分镜与前图过于相似" in text for text in calls)


def test_workshop_removes_fast_mode_and_exposes_image_style_selector():
    root = Path(__file__).resolve().parents[1]
    template = (
        root / "src/ai_write_x/web/templates/components/views/creative-workshop.html"
    ).read_text(encoding="utf-8")
    script = (
        root / "src/ai_write_x/web/static/js/creative-workshop.js"
    ).read_text(encoding="utf-8")

    assert "workshop-fast-mode" not in template
    assert "极速模式" not in template
    assert 'id="workshop-image-style"' in template
    assert "高级杂志摄影" in template
    assert "真实纪实摄影" in template
    assert "image_style:" in script
    assert "fast_mode: isFastModeOn" not in script
