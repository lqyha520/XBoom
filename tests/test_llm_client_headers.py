import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

from src.ai_write_x.core import llm_client
from src.ai_write_x.core.direct_llm import _apply_compatibility_headers


def _client_with_api_type(api_type: str):
    client = object.__new__(llm_client.LLMClient)
    client._config = SimpleNamespace(api_type=api_type)
    return client


def test_custom_async_client_overrides_sdk_user_agent(monkeypatch):
    captured = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(llm_client, "AsyncOpenAI", FakeAsyncOpenAI)
    client = _client_with_api_type("我的中转")

    client._get_async_client("test-key", "https://gateway.example/v1")

    headers = captured["default_headers"]
    assert headers["User-Agent"].startswith("Mozilla/5.0")
    assert headers["Accept"] == "application/json"
    assert "AsyncOpenAI/Python" not in headers["User-Agent"]


def test_standard_async_client_keeps_sdk_defaults(monkeypatch):
    captured = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(llm_client, "AsyncOpenAI", FakeAsyncOpenAI)
    client = _client_with_api_type("OpenRouter")

    client._get_async_client("test-key", "https://openrouter.ai/api/v1")

    assert "default_headers" not in captured


def test_direct_llm_key_rebuild_uses_sdk_level_headers():
    kwargs = {"api_key": "test-key", "base_url": "https://gateway.example/v1"}

    result = _apply_compatibility_headers(kwargs, True)

    assert result["default_headers"]["User-Agent"].startswith("Mozilla/5.0")
    assert result["default_headers"]["Accept"] == "application/json"


def test_custom_async_client_sends_browser_user_agent_on_stream_request():
    received = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received["user_agent"] = self.headers.get("User-Agent")
            length = int(self.headers.get("Content-Length", "0"))
            received["payload"] = json.loads(self.rfile.read(length))
            body = (
                'data: {"id":"test","object":"chat.completion.chunk",'
                '"created":1,"model":"test-model","choices":[{"index":0,'
                '"delta":{"content":"OK"},"finish_reason":null}]}\n\n'
                'data: [DONE]\n\n'
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    async def run_request():
        client = _client_with_api_type("我的中转")._get_async_client(
            "test-key",
            f"http://127.0.0.1:{server.server_port}/v1",
        )
        try:
            stream = await client.chat.completions.create(
                model="test-model",
                messages=[{"role": "user", "content": "hello"}],
                stream=True,
            )
            parts = []
            async for chunk in stream:
                if chunk.choices:
                    parts.append(chunk.choices[0].delta.content or "")
            return "".join(parts)
        finally:
            await client.close()

    try:
        assert asyncio.run(run_request()) == "OK"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert received["user_agent"].startswith("Mozilla/5.0")
    assert received["payload"]["stream"] is True


def test_custom_sync_client_sends_browser_user_agent_on_request():
    received = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received["user_agent"] = self.headers.get("User-Agent")
            length = int(self.headers.get("Content-Length", "0"))
            received["payload"] = json.loads(self.rfile.read(length))
            body = json.dumps({
                "id": "test",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "OK"},
                    "finish_reason": "stop",
                }],
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = _client_with_api_type("我的中转")
    client._client_cache = {}

    try:
        sdk_client = client._get_client(
            "test-key",
            f"http://127.0.0.1:{server.server_port}/v1",
        )
        response = sdk_client.chat.completions.create(
            model="test-model",
            messages=[{"role": "user", "content": "hello"}],
        )
        assert response.choices[0].message.content == "OK"
        sdk_client.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert received["user_agent"].startswith("Mozilla/5.0")
