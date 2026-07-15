from src.ai_write_x.utils.api_url import (
    build_image_generation_url,
    build_openai_endpoint,
    normalize_openai_base_url,
)


def test_openai_base_adds_v1_once():
    assert normalize_openai_base_url("https://api.example.com") == "https://api.example.com/v1"
    assert normalize_openai_base_url("https://api.example.com/v1/") == "https://api.example.com/v1"


def test_force_raw_marker_skips_v1_completion():
    assert normalize_openai_base_url("https://api.example.com/custom#") == "https://api.example.com/custom"
    assert build_image_generation_url("https://api.example.com/custom#") == "https://api.example.com/custom/images/generations"


def test_image_endpoint_accepts_root_versioned_and_complete_urls():
    expected = "https://api.example.com/v1/images/generations"
    assert build_image_generation_url("https://api.example.com") == expected
    assert build_image_generation_url("https://api.example.com/v1") == expected
    assert build_image_generation_url(expected) == expected


def test_chat_endpoint_uses_same_normalization():
    assert build_openai_endpoint("https://api.example.com", "chat/completions") == "https://api.example.com/v1/chat/completions"
