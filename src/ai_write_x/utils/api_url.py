import re


_VERSION_SEGMENT = re.compile(r"/v\d+(?:[a-z]+)?(?:\.\d+)?(?:/|$)", re.IGNORECASE)
_IMAGE_ENDPOINTS = ("/images/generations", "/image-synthesis")
_OPENAI_ENDPOINTS = (*_IMAGE_ENDPOINTS, "/chat/completions", "/responses")


def split_force_raw_marker(raw_url: str) -> tuple[str, bool]:
    value = str(raw_url or "").strip()
    force_raw = value.endswith("#")
    if force_raw:
        value = value[:-1].rstrip()
    return value.rstrip("/"), force_raw


def normalize_openai_base_url(raw_url: str) -> str:
    """Normalize an OpenAI-compatible base URL, honoring a trailing # raw marker."""
    value, force_raw = split_force_raw_marker(raw_url)
    if not value or force_raw:
        return value
    lower = value.lower()
    for endpoint in _OPENAI_ENDPOINTS:
        if lower.endswith(endpoint):
            value = value[: -len(endpoint)].rstrip("/")
            lower = value.lower()
            break
    if lower.endswith("/models"):
        value = value[:-7].rstrip("/")
        lower = value.lower()
    if _VERSION_SEGMENT.search(f"{lower}/"):
        return value
    return f"{value}/v1"


def normalize_openai_base_url_for_storage(raw_url: str) -> str:
    """Normalize a saved URL while preserving the trailing-# raw override."""
    value, force_raw = split_force_raw_marker(raw_url)
    if not value:
        return value
    if force_raw:
        return f"{value}#"
    return normalize_openai_base_url(value)


def normalize_openai_provider_urls(api_config: dict) -> dict:
    """Normalize every provider ``api_base`` in the main LLM configuration."""
    if not isinstance(api_config, dict):
        return api_config
    for provider in api_config.values():
        entries = provider if isinstance(provider, list) else [provider]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            api_base = entry.get("api_base")
            if isinstance(api_base, str) and api_base.strip():
                entry["api_base"] = normalize_openai_base_url_for_storage(api_base)
    return api_config


def build_openai_endpoint(raw_url: str, endpoint: str) -> str:
    value, force_raw = split_force_raw_marker(raw_url)
    endpoint = endpoint.strip("/")
    if not value:
        return ""
    if value.lower().endswith(f"/{endpoint.lower()}"):
        return value
    base = value if force_raw else normalize_openai_base_url(value)
    return f"{base.rstrip('/')}/{endpoint}"


def build_image_generation_url(raw_url: str) -> str:
    value, _ = split_force_raw_marker(raw_url)
    lower = value.lower()
    if any(lower.endswith(endpoint) for endpoint in _IMAGE_ENDPOINTS):
        return value
    return build_openai_endpoint(raw_url, "images/generations")
