# -*- coding: utf-8 -*-
"""Runtime path regression tests."""

from pathlib import Path
from unittest.mock import patch
import sys
import types


def test_spider_data_manager_default_dir_uses_path_manager():
    from src.ai_write_x.tools.spider_manager import SpiderDataManager

    expected = Path("F:/tmp/xboom-user-data/output")
    with patch("src.ai_write_x.tools.spider_manager.PathManager.get_output_dir", return_value=expected):
        manager = SpiderDataManager()

    assert manager.data_dir == expected / "spider"
    assert manager.articles_root == expected / "spider" / "articles"


def test_webview_crash_log_uses_path_manager_log_dir(tmp_path):
    from src.ai_write_x.web.webview_gui import WebViewGUI

    log_dir = tmp_path / "user-logs"
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    with (
        patch("src.ai_write_x.web.webview_gui.PathManager.get_log_dir", return_value=log_dir),
        patch("src.ai_write_x.web.webview_gui.sys.frozen", True, create=True),
        patch("src.ai_write_x.web.webview_gui.sys.executable", str(install_dir / "小爆来咯.exe")),
    ):
        gui = WebViewGUI.__new__(WebViewGUI)
        gui.write_crash_log("test", RuntimeError("boom"))

    assert (log_dir / "desktop_crash.log").exists()
    assert not (install_dir / "logs").exists()


def test_knowledge_graph_persists_to_app_data(tmp_path):
    from src.ai_write_x.core.knowledge_graph import KnowledgeGraph

    app_data = tmp_path / "app-data"
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    with (
        patch("src.ai_write_x.utils.path_manager.PathManager.get_app_data_dir", return_value=app_data),
        patch("src.ai_write_x.utils.path_manager.PathManager.get_base_dir", return_value=install_dir),
    ):
        graph = KnowledgeGraph()

    assert graph.persist_path == app_data / "knowledge_graph.json"


def test_wechat_preview_uses_output_dir(tmp_path):
    from src.ai_write_x.core.wechat_preview import WeChatPreviewEngine

    output_dir = tmp_path / "user-output"
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    with (
        patch("src.ai_write_x.core.wechat_preview.PathManager.get_output_dir", return_value=output_dir),
        patch("src.ai_write_x.core.wechat_preview.PathManager.get_root_dir", return_value=install_dir),
    ):
        engine = WeChatPreviewEngine()

    assert engine.preview_dir == output_dir / "previews"
    assert not (install_dir / "previews").exists()


def test_aesthetic_profile_uses_config_dir(tmp_path):
    fake_config_module = types.ModuleType("src.ai_write_x.config.config")
    fake_config_module.Config = type(
        "Config",
        (),
        {"get_instance": staticmethod(lambda: types.SimpleNamespace(config={}))},
    )
    fake_factory_module = types.ModuleType("src.ai_write_x.core.agent_factory")
    fake_factory_module.AgentFactory = lambda: object()
    fake_framework_module = types.ModuleType("src.ai_write_x.core.base_framework")
    fake_framework_module.AgentConfig = object

    with patch.dict(
        sys.modules,
        {
            "src.ai_write_x.config.config": fake_config_module,
            "src.ai_write_x.core.agent_factory": fake_factory_module,
            "src.ai_write_x.core.base_framework": fake_framework_module,
        },
    ):
        from src.ai_write_x.core.aesthetic_summarizer import AestheticSummarizer

        config_dir = tmp_path / "user-config"
        install_dir = tmp_path / "install"
        install_dir.mkdir()
        with (
            patch("src.ai_write_x.core.aesthetic_summarizer.PathManager.get_config_dir", return_value=config_dir),
            patch("src.ai_write_x.core.aesthetic_summarizer.PathManager.get_root_dir", return_value=install_dir),
        ):
            summarizer = AestheticSummarizer()

    assert summarizer.profile_path == config_dir / "aesthetic_profile.json"


def test_publishers_cookie_dir_uses_app_data(tmp_path):
    from src.ai_write_x.tools.publishers.base_publisher import PlaywrightPublisher

    class PublisherForTest(PlaywrightPublisher):
        def publish(self, title: str, content: str, images: list = None, **kwargs):
            return True, "ok"

    app_data = tmp_path / "app-data"
    with patch("src.ai_write_x.tools.publishers.base_publisher.PathManager.get_app_data_dir", return_value=app_data):
        publisher = PublisherForTest("demo")

    assert Path(publisher.cookies_dir) == app_data / "data" / "cookies"
    assert Path(publisher.cookie_file) == app_data / "data" / "cookies" / "demo_cookies.json"


def test_generate_temp_cleanup_uses_path_manager():
    source = Path("src/ai_write_x/web/api/generate.py").read_text(encoding="utf-8")
    assert "PathManager.get_temp_dir()" in source
    assert "os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))" not in source
