import yaml

from src.ai_write_x.config.config import Config
from src.ai_write_x.utils.api_url import (
    build_image_generation_url,
    build_openai_endpoint,
    normalize_openai_base_url,
    normalize_openai_base_url_for_storage,
    normalize_openai_provider_urls,
)


def test_openai_base_adds_v1_once():
    assert normalize_openai_base_url("https://api.example.com") == "https://api.example.com/v1"
    assert normalize_openai_base_url("https://api.example.com/v1/") == "https://api.example.com/v1"
    assert normalize_openai_base_url("https://api.example.com/v1/chat/completions") == "https://api.example.com/v1"
    assert normalize_openai_base_url(
        "https://generativelanguage.googleapis.com/v1beta/openai/"
    ) == "https://generativelanguage.googleapis.com/v1beta/openai"


def test_force_raw_marker_skips_v1_completion():
    assert normalize_openai_base_url("https://api.example.com/custom#") == "https://api.example.com/custom"
    assert normalize_openai_base_url_for_storage("https://api.example.com/custom#") == "https://api.example.com/custom#"
    assert build_image_generation_url("https://api.example.com/custom#") == "https://api.example.com/custom/images/generations"


def test_image_endpoint_accepts_root_versioned_and_complete_urls():
    expected = "https://api.example.com/v1/images/generations"
    assert build_image_generation_url("https://api.example.com") == expected
    assert build_image_generation_url("https://api.example.com/v1") == expected
    assert build_image_generation_url(expected) == expected


def test_chat_endpoint_uses_same_normalization():
    assert build_openai_endpoint("https://api.example.com", "chat/completions") == "https://api.example.com/v1/chat/completions"


def test_provider_urls_are_normalized_before_storage():
    api_config = {
        "api_type": "custom",
        "custom": [
            {"api_base": "https://api.example.com", "model": ["model-a"]},
            {"api_base": "https://raw.example.com/gateway#", "model": ["model-b"]},
        ],
        "builtin": {"api_base": "https://builtin.example.com/v1/chat/completions"},
    }

    normalize_openai_provider_urls(api_config)

    assert api_config["custom"][0]["api_base"] == "https://api.example.com/v1"
    assert api_config["custom"][1]["api_base"] == "https://raw.example.com/gateway#"
    assert api_config["builtin"]["api_base"] == "https://builtin.example.com/v1"


def test_config_save_persists_normalized_url_and_runtime_has_a_fallback(tmp_path):
    config = object.__new__(Config)
    config.config_path = str(tmp_path / "config.yaml")
    config.config_aiforge_path = str(tmp_path / "aiforge.toml")
    config.error_message = None
    config._save_secrets_to_file = lambda _payload: True
    config._strip_secrets = lambda payload: payload
    payload = {
        "api": {
            "api_type": "my-gateway",
            "my-gateway": {
                "api_base": "https://api.example.com",
                "api_key": ["secret"],
                "model": ["model-a"],
            },
        }
    }

    assert config.save_config(payload)
    saved = yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
    assert saved["api"]["my-gateway"]["api_base"] == "https://api.example.com/v1"

    config.config["api"]["my-gateway"]["api_base"] = "https://legacy.example.com"
    assert config.api_apibase == "https://legacy.example.com/v1"
