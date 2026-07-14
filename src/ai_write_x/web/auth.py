"""Shared client-token authentication helpers for HTTP and WebSocket access."""

from __future__ import annotations

import os
import secrets
import threading
from collections.abc import Iterable


CLIENT_TOKEN_COOKIE = "app_client_token"
CLIENT_TOKEN_HEADER = "X-App-Client-Token"


class ClientTokenRegistry:
    """Thread-safe registry for the tokens accepted by the local web service."""

    def __init__(self, tokens: Iterable[str] = ()) -> None:
        self._lock = threading.RLock()
        self._tokens = {token.strip() for token in tokens if token and token.strip()}

    @classmethod
    def from_environment(cls) -> "ClientTokenRegistry":
        return cls(os.environ.get("AIWRITEX_CLIENT_TOKEN", "").split(","))

    def register_bootstrap_token(self, token: str | None) -> bool:
        """Accept the configured token, or register the first token in local mode."""
        candidate = (token or "").strip()
        if not candidate:
            return False

        with self._lock:
            if self._tokens and not self._contains_unlocked(candidate):
                return False
            self._tokens.add(candidate)
            return True

    def contains(self, token: str | None) -> bool:
        candidate = (token or "").strip()
        if not candidate:
            return False
        with self._lock:
            return self._contains_unlocked(candidate)

    def _contains_unlocked(self, candidate: str) -> bool:
        return any(secrets.compare_digest(candidate, token) for token in self._tokens)


client_tokens = ClientTokenRegistry.from_environment()


def is_public_http_path(path: str) -> bool:
    """Return whether an HTTP path is intentionally accessible without a token."""
    if path == "/health":
        return True
    return any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in ("/static", "/images")
    )


def is_development_local_request(app_env: str, client_host: str | None) -> bool:
    """Allow local bypass only when development mode is explicitly selected."""
    return app_env.lower() == "development" and client_host in {
        "127.0.0.1",
        "::1",
        "localhost",
    }
