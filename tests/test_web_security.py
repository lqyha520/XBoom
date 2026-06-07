# -*- coding: utf-8 -*-
"""Security regression tests for the local web API."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient


def _client_with_registered_token(client: TestClient, token: str = "issued-token") -> dict[str, str]:
    client.get("/", params={"token": token})
    return {"X-App-Client-Token": token}


def test_unregistered_client_token_cannot_access_config_api():
    from src.ai_write_x.web.app import allowed_tokens, app

    allowed_tokens.clear()
    with TestClient(app) as client:
        response = client.get(
            "/api/config/",
            headers={"X-App-Client-Token": "not-issued-by-app"},
        )

    assert response.status_code == 403


def test_config_api_masks_runtime_secrets(monkeypatch):
    from src.ai_write_x.web.app import allowed_tokens, app
    from src.ai_write_x.web.api import config as config_api

    fake_config = SimpleNamespace(
        config={
            "api": {"OpenRouter": {"api_key": ["sk-live-secret"], "key_index": 0}},
            "img_api": {"ali": {"api_key": "img-secret"}},
            "wechat": {"credentials": [{"appid": "wx-app", "appsecret": "wx-secret"}]},
        },
        aiforge_config={"llm": {"api_key": "forge-secret"}},
    )
    monkeypatch.setattr(config_api.Config, "get_instance", lambda: fake_config)

    allowed_tokens.clear()
    with TestClient(app) as client:
        headers = _client_with_registered_token(client)
        response = client.get("/api/config/", headers=headers)

    assert response.status_code == 200
    body = response.text
    assert "sk-live-secret" not in body
    assert "img-secret" not in body
    assert "wx-secret" not in body
    assert "forge-secret" not in body


def test_article_content_rejects_paths_outside_article_dir(tmp_path, monkeypatch):
    from src.ai_write_x.web.app import allowed_tokens, app
    from src.ai_write_x.web.api import articles as articles_api

    article_dir = tmp_path / "articles"
    article_dir.mkdir()
    article_file = article_dir / "ok.md"
    article_file.write_text("inside article", encoding="utf-8")
    outside_file = tmp_path / "outside.md"
    outside_file.write_text("outside article", encoding="utf-8")
    monkeypatch.setattr(articles_api.PathManager, "get_article_dir", lambda: article_dir)

    allowed_tokens.clear()
    with TestClient(app) as client:
        headers = _client_with_registered_token(client)
        allowed = client.get(
            "/api/articles/content",
            params={"path": str(article_file)},
            headers=headers,
        )
        blocked = client.get(
            "/api/articles/content",
            params={"path": str(outside_file)},
            headers=headers,
        )

    assert allowed.status_code == 200
    assert allowed.text == "inside article"
    assert blocked.status_code == 400
