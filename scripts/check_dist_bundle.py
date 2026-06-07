# -*- coding: utf-8 -*-
"""Validate a built XBoom onedir bundle."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MAX_INSTALLER_SIZE_MIB = 140
LARGE_DIR_WARN_MIB = 60

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"wx[a-z0-9]{16,}"),
    re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}"),
]
SECRET_SCAN_EXCLUDES = {
    Path("_internal/litellm/proxy/_super_secret_config.yaml"),
    Path("_internal/litellm/llms/huggingface/huggingface_llms_metadata/hf_text_generation_models.txt"),
}


def _ok(message: str) -> None:
    _print(f"[OK] {message}")


def _fail(message: str) -> None:
    _print(f"[FAIL] {message}")


def _print(message: str) -> None:
    safe = message.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8")
    print(safe)


def _default_dist_root() -> Path:
    from src.ai_write_x.branding.install import APP_BRAND

    return ROOT / "dist" / APP_BRAND


def _bundle_data_root(dist_root: Path) -> Path:
    internal = dist_root / "_internal"
    return internal if internal.exists() else dist_root


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def check_dist_root(dist_root: Path) -> bool:
    if not dist_root.exists():
        _fail(f"Dist root does not exist: {dist_root}")
        return False
    if not dist_root.is_dir():
        _fail(f"Dist root is not a directory: {dist_root}")
        return False
    _ok(f"Dist root exists: {dist_root}")
    return True


def check_entry_exe(dist_root: Path) -> bool:
    from src.ai_write_x.branding.install import EXE_NAME

    exe = dist_root / EXE_NAME
    if exe.exists():
        _ok(f"Entry executable exists: {exe.name}")
        return True

    exes = sorted(path.name for path in dist_root.glob("*.exe"))
    if exes:
        _fail(f"Expected {EXE_NAME}, found: {', '.join(exes)}")
    else:
        _fail("No executable found in dist root")
    return False


def check_required_assets(dist_root: Path) -> bool:
    data_root = _bundle_data_root(dist_root)
    required = [
        "src/ai_write_x/assets/branding/app_icon.ico",
        "src/ai_write_x/web/templates/index.html",
        "src/ai_write_x/web/static/css/main.css",
        "src/ai_write_x/web/static/js/main.js",
        "templates",
        "config/config.yaml",
        "config/aiforge.toml",
        "config/mcp_services.json",
        "secrets/api_keys.yaml",
        "secrets/api_keys.example.yaml",
        "docs/uninstall-user-data.md",
    ]
    ok = True
    for relative in required:
        path = data_root / Path(relative)
        if not path.exists():
            _fail(f"Required bundled asset missing: {relative}")
            ok = False

    workflow_hits = sorted(data_root.rglob("*nf4*.json"))
    if not workflow_hits:
        _fail("ComfyUI nf4 workflow JSON is missing")
        ok = False

    if ok:
        _ok("Required bundled assets are present")
    return ok


def check_no_local_runtime_state(dist_root: Path) -> bool:
    data_root = _bundle_data_root(dist_root)
    blocked_dirs = ["data", "output", "logs", "pywebview"]
    blocked_paths = ["src/output", "src/ai_write_x/scrapers/output"]
    blocked_files = ["install_id.txt", "config/config.yaml.bak"]
    ok = True
    for name in blocked_dirs:
        if (data_root / name).exists():
            _fail(f"Runtime directory should not be bundled: {name}")
            ok = False
    for name in blocked_paths:
        if (data_root / name).exists():
            _fail(f"Runtime path should not be bundled: {name}")
            ok = False
    for name in blocked_files:
        if (data_root / name).exists():
            _fail(f"Runtime file should not be bundled: {name}")
            ok = False
    if ok:
        _ok("No local runtime state directories/files are bundled")
    return ok


def check_no_detected_secrets(dist_root: Path) -> bool:
    ok = True
    scanned = 0
    for path in dist_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".yaml", ".yml", ".toml", ".json", ".env", ".txt"}:
            continue
        relative = path.relative_to(dist_root)
        if Path(relative.as_posix()) in SECRET_SCAN_EXCLUDES:
            continue
        scanned += 1
        text = _read_text(path)
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                _fail(f"Potential secret detected in bundle: {relative}")
                ok = False
                break
    if ok:
        _ok(f"No detected secrets in {scanned} scanned config/text files")
    return ok


def check_factory_secret_template(dist_root: Path) -> bool:
    secret = _bundle_data_root(dist_root) / "secrets" / "api_keys.yaml"
    if not secret.exists():
        _fail("Factory API key template is missing")
        return False
    text = _read_text(secret)
    if "api: {}" not in text or "img_api: {}" not in text:
        _fail("Factory API key template does not look sanitized")
        return False
    _ok("Factory API key template is sanitized")
    return True


def summarize_largest_bundle_dirs(dist_root: Path) -> bool:
    data_root = _bundle_data_root(dist_root)
    dirs = []
    for path in data_root.iterdir():
        if not path.is_dir():
            continue
        total = sum(file.stat().st_size for file in path.rglob("*") if file.is_file())
        dirs.append((total, path.name))
    if not dirs:
        return True
    top = sorted(dirs, reverse=True)[:8]
    summary = ", ".join(f"{name}={size / 1024 / 1024:.1f}MiB" for size, name in top)
    _ok(f"Largest bundled directories: {summary}")
    large = [(size, name) for size, name in top if size / 1024 / 1024 >= LARGE_DIR_WARN_MIB]
    if large:
        large_summary = ", ".join(f"{name}={size / 1024 / 1024:.1f}MiB" for size, name in large)
        _print(f"[WARN] Large bundled directories worth reviewing: {large_summary}")
    return True


def check_installer_size_budget() -> bool:
    installer_dir = ROOT / "dist" / "installer"
    installers = sorted(installer_dir.glob("*-Setup-v*.exe"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not installers:
        _fail("Versioned installer was not found in dist/installer")
        return False
    installer = installers[0]
    size_mib = installer.stat().st_size / 1024 / 1024
    if size_mib > MAX_INSTALLER_SIZE_MIB:
        _fail(f"Installer size {size_mib:.1f}MiB exceeds budget {MAX_INSTALLER_SIZE_MIB}MiB: {installer.name}")
        return False
    _ok(f"Installer size is within budget: {size_mib:.1f}MiB <= {MAX_INSTALLER_SIZE_MIB}MiB")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate XBoom dist onedir bundle.")
    parser.add_argument("dist_root", nargs="?", type=Path, default=_default_dist_root())
    parser.add_argument(
        "--skip-installer-size",
        action="store_true",
        help="Skip installer size check when the Inno Setup package has not been built yet.",
    )
    args = parser.parse_args(argv)

    dist_root = args.dist_root.resolve()
    checks = [
        lambda: check_dist_root(dist_root),
        lambda: check_entry_exe(dist_root),
        lambda: check_required_assets(dist_root),
        lambda: check_no_local_runtime_state(dist_root),
        lambda: check_no_detected_secrets(dist_root),
        lambda: check_factory_secret_template(dist_root),
        lambda: summarize_largest_bundle_dirs(dist_root),
    ]
    if not args.skip_installer_size:
        checks.append(check_installer_size_budget)
    results = [check() for check in checks]
    if all(results):
        _print("\nDist bundle check passed.")
        return 0
    _print("\nDist bundle check failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
