import asyncio
from pathlib import Path

from src.ai_write_x.core.visual_assets import VisualAssetsManager
from src.ai_write_x.utils.path_manager import PathManager
from src.ai_write_x.web.api import articles as articles_api


class _FakeConfig:
    def __init__(self):
        self.wechat_credentials = [
            {
                "appid": "wx-direct",
                "appsecret": "secret",
                "author": "测试账号",
                "enabled": True,
            }
        ]
        self.format_publish = False
        self.config = {"auto_delete_published": False}


def test_article_library_publish_calls_wechat_directly(monkeypatch, tmp_path: Path):
    article = tmp_path / "direct.html"
    article.write_text(
        "<html><body><h1>直接发布测试</h1><p>文章库发布不再经过运营中心。</p></body></html>",
        encoding="utf-8",
    )
    calls = []

    monkeypatch.setattr(articles_api.Config, "get_instance", staticmethod(lambda: _FakeConfig()))
    monkeypatch.setattr(PathManager, "get_article_dir", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(
        VisualAssetsManager,
        "prepare_for_wechat_publish",
        classmethod(lambda cls, path: article.read_text(encoding="utf-8")),
    )

    import src.ai_write_x.tools.wx_publisher as publisher_module

    def fake_pub2wx(**kwargs):
        calls.append(kwargs)
        return "发布成功", "media-id", True

    monkeypatch.setattr(publisher_module, "pub2wx", fake_pub2wx)
    result = asyncio.run(
        articles_api.publish_articles(
            articles_api.PublishRequest(
                article_paths=[str(article)],
                account_indices=[0],
                article_titles=["直接发布测试"],
            )
        )
    )

    assert result["success_count"] == 1
    assert result["fail_count"] == 0
    assert calls[0]["appid"] == "wx-direct"
    assert calls[0]["title"] == "直接发布测试"


def test_operations_center_assets_and_routes_are_removed():
    root = Path(__file__).resolve().parents[1]
    index = (root / "src/ai_write_x/web/templates/index.html").read_text(encoding="utf-8")
    sidebar = (root / "src/ai_write_x/web/templates/components/sidebar.html").read_text(encoding="utf-8")
    app_source = (root / "src/ai_write_x/web/app.py").read_text(encoding="utf-8")
    assert "operations-hub" not in index
    assert "运营中心" not in sidebar
    assert "operations_router" not in app_source
    assert not (root / "src/ai_write_x/web/api/operations.py").exists()
    assert not (root / "src/ai_write_x/core/operations_hub.py").exists()
