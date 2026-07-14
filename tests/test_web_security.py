from src.ai_write_x.web.auth import (
    ClientTokenRegistry,
    is_development_local_request,
    is_public_http_path,
)


def test_only_static_images_and_basic_health_are_public():
    assert is_public_http_path("/health")
    assert is_public_http_path("/static/js/main.js")
    assert is_public_http_path("/images/cover.png")

    assert not is_public_http_path("/health/v15")
    assert not is_public_http_path("/api/system/update")
    assert not is_public_http_path("/api/system/update-policy")
    assert not is_public_http_path("/api/system/update-progress")


def test_configured_registry_rejects_unknown_bootstrap_tokens():
    registry = ClientTokenRegistry(["configured-token"])

    assert registry.register_bootstrap_token("configured-token")
    assert registry.contains("configured-token")
    assert not registry.register_bootstrap_token("attacker-token")
    assert not registry.contains("attacker-token")


def test_empty_registry_accepts_only_tokens_registered_during_bootstrap():
    registry = ClientTokenRegistry()

    assert registry.register_bootstrap_token("desktop-session-token")
    assert registry.contains("desktop-session-token")
    assert not registry.register_bootstrap_token("second-untrusted-token")


def test_development_bypass_must_be_explicit_and_local():
    assert is_development_local_request("development", "127.0.0.1")
    assert not is_development_local_request("production", "127.0.0.1")
    assert not is_development_local_request("development", "192.168.1.20")
    assert not is_development_local_request("staging", "127.0.0.1")
