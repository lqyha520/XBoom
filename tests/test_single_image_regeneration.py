import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException
from bs4 import BeautifulSoup

from src.ai_write_x.core.visual_assets import VisualAssetsManager
from src.ai_write_x.utils.path_manager import PathManager
from src.ai_write_x.web.api.articles import (
    RegenerateSingleImageRequest,
    regenerate_single_article_image,
)


def test_regenerate_single_image_replaces_only_target(monkeypatch, tmp_path: Path):
    article = tmp_path / "article.html"
    article.write_text(
        """<!doctype html><html><body><h1>测试文章</h1>
        <p>这是目标图片附近的一段正文，用于描述真实的文章场景。</p>
        <img src="/images/old-a.png" data-aspect-ratio="16:9" alt="旧图一">
        <img src="/images/old-b.png" data-aspect-ratio="4:3" alt="旧图二">
        </body></html>""",
        encoding="utf-8",
    )
    monkeypatch.setattr(PathManager, "get_article_dir", staticmethod(lambda: tmp_path))
    captured = {}

    def fake_generate(cls, marker, timeout=None, force_regenerate=False):
        captured["marker"] = marker
        captured["force_regenerate"] = force_regenerate
        return (
            '<img src="/images/new-a.png" alt="新图" '
            'data-img-prompt="custom scene --no text" data-aspect-ratio="16:9">'
        )

    monkeypatch.setattr(
        VisualAssetsManager,
        "sync_trigger_image_generation",
        classmethod(fake_generate),
    )

    result = asyncio.run(
        regenerate_single_article_image(
            RegenerateSingleImageRequest(
                path=str(article),
                image_src="/images/old-a.png",
                image_index=0,
                prompt="custom scene",
                image_style="cinematic",
            )
        )
    )

    saved = BeautifulSoup(article.read_text(encoding="utf-8"), "html.parser")
    images = saved.find_all("img")
    assert result["status"] == "success"
    assert captured["force_regenerate"] is True
    assert "custom scene" in captured["marker"]
    assert images[0]["src"] == "/images/new-a.png"
    assert images[0]["data-img-prompt"] == "custom scene --no text"
    assert images[1]["src"] == "/images/old-b.png"


def test_regenerate_single_image_uses_index_fallback(monkeypatch, tmp_path: Path):
    article = tmp_path / "fallback.html"
    article.write_text(
        '<html><body><h1>标题</h1><p>正文上下文内容足够生成新的画面。</p>'
        '<img src="/images/only.png" data-aspect-ratio="16:9"></body></html>',
        encoding="utf-8",
    )
    monkeypatch.setattr(PathManager, "get_article_dir", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(
        VisualAssetsManager,
        "_image_prompt_text",
        classmethod(lambda cls, topic, context, is_cover=False, style_key="auto": ("auto prompt", "16:9")),
    )
    monkeypatch.setattr(
        VisualAssetsManager,
        "sync_trigger_image_generation",
        classmethod(
            lambda cls, marker, timeout=None, force_regenerate=False:
            '<img src="/images/fresh.png" data-img-prompt="auto prompt" data-aspect-ratio="16:9">'
        ),
    )

    asyncio.run(
        regenerate_single_article_image(
            RegenerateSingleImageRequest(
                path=str(article),
                image_src="/images/stale-browser-value.png",
                image_index=0,
                prompt="",
                image_style="oriental",
            )
        )
    )
    saved = BeautifulSoup(article.read_text(encoding="utf-8"), "html.parser")
    assert saved.find("img")["src"] == "/images/fresh.png"


def test_regenerate_single_image_rejects_path_outside_articles(monkeypatch, tmp_path: Path):
    article_dir = tmp_path / "articles"
    article_dir.mkdir()
    outside = tmp_path / "outside.html"
    outside.write_text('<img src="/images/a.png">', encoding="utf-8")
    monkeypatch.setattr(PathManager, "get_article_dir", staticmethod(lambda: article_dir))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            regenerate_single_article_image(
                RegenerateSingleImageRequest(
                    path=str(outside),
                    image_src="/images/a.png",
                )
            )
        )
    assert exc.value.status_code == 400


def test_preview_panel_exposes_single_image_regeneration_controls():
    root = Path(__file__).resolve().parents[1]
    template = (root / "src/ai_write_x/web/templates/components/preview-panel.html").read_text(encoding="utf-8")
    script = (root / "src/ai_write_x/web/static/js/preview-panel.js").read_text(encoding="utf-8")
    assert "preview-regenerate-image-btn" in template
    assert "openSingleImageRegenerator" in script
    assert "/api/articles/regenerate-image" in script
    assert "重新生成并替换" in script
