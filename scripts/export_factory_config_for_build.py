#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打包前生成出厂默认配置，避免把开发者本机 config / secrets 打进安装包。"""

from __future__ import annotations

import copy
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "build" / "factory_config"
SECRETS_TEMPLATE = """# AIWriteX 密钥配置（用户自行填写，安装包不会包含真实密钥）
# 路径: %APPDATA%/小爆来咯/secrets/api_keys.yaml

wechat:
  credentials: []

api: {}

img_api: {}
"""


def _strip_aiforge_keys(toml_text: str) -> str:
    """将 aiforge.toml 中 api_key 置空，避免开发机残留。"""
    return re.sub(
        r'(?m)^(api_key\s*=\s*)".*?"\s*$',
        r'\1""',
        re.sub(r"(?m)^(api_key\s*=\s*)'[^']*'\s*$", r'\1""', toml_text),
    )


def _sanitize_factory_config(cfg, raw: dict) -> dict:
    """仅保留 default_config 中的 API 厂商结构，去掉本机自定义厂商快照。"""
    data = cfg._strip_secrets(copy.deepcopy(raw))
    default_api = cfg.default_config.get("api") or {}
    if isinstance(default_api, dict) and isinstance(data.get("api"), dict):
        allowed = set(default_api.keys())
        api_block = data["api"]
        for key in list(api_block.keys()):
            if key not in allowed:
                del api_block[key]
        api_block["custom"] = []
        api_block.pop("deleted_providers", None)
        if "api_type" in default_api:
            api_block["api_type"] = default_api.get("api_type", "OpenRouter")

    default_img = cfg.default_config.get("img_api") or {}
    if isinstance(default_img, dict):
        img_block = data.setdefault("img_api", {})
        for provider, default_vals in default_img.items():
            if provider == "settings":
                img_block["settings"] = copy.deepcopy(default_vals)
                continue
            if provider == "custom":
                img_block["custom"] = []
                continue
            entry = copy.deepcopy(default_vals) if isinstance(default_vals, dict) else {}
            if isinstance(entry, dict):
                entry["api_key"] = ""
            img_block[provider] = entry
        img_block["api_type"] = default_img.get("api_type", "picsum")
        img_block["custom_index"] = 0

    return data


def main() -> int:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))

    from src.ai_write_x.config.config import Config

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    secrets_dir = OUT_DIR / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)

    cfg = Config.get_instance()
    sanitized = _sanitize_factory_config(cfg, cfg.default_config)

    config_path = OUT_DIR / "config.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(
            sanitized,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )

    aiforge_src = ROOT / "src" / "ai_write_x" / "config" / "aiforge.toml"
    aiforge_dst = OUT_DIR / "aiforge.toml"
    if aiforge_src.is_file():
        aiforge_dst.write_text(_strip_aiforge_keys(aiforge_src.read_text(encoding="utf-8")), encoding="utf-8")

    mcp_src = ROOT / "src" / "ai_write_x" / "config" / "mcp_services.json"
    mcp_dst = OUT_DIR / "mcp_services.json"
    if mcp_src.is_file():
        mcp_dst.write_bytes(mcp_src.read_bytes())

    secrets_path = secrets_dir / "api_keys.yaml"
    secrets_path.write_text(SECRETS_TEMPLATE, encoding="utf-8")

    print(f"[factory-config] wrote {config_path}")
    print(f"[factory-config] wrote {aiforge_dst} (exists={aiforge_dst.is_file()})")
    print(f"[factory-config] wrote {mcp_dst} (exists={mcp_dst.is_file()})")
    print(f"[factory-config] wrote empty {secrets_path}")
    print("[factory-config] NOT using src/ai_write_x/config/config.yaml or secrets/api_keys.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
