# -*- coding: utf-8 -*-
"""Release packaging checks for XBoom."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WEBVIEW2_RUNTIME_GUID = "F3017226-FE2A-4295-8BDF-00C3A9A7E4C5"
OLD_WEBVIEW2_GUID = "F3017226-FE2A-4295-8BDF-00C3B927B189"
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"wx[a-z0-9]{16,}"),
    re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}"),
]


def _ok(message: str) -> None:
    print(f"[OK] {message}")


def _warn(message: str) -> None:
    print(f"[WARN] {message}")


def _fail(message: str) -> None:
    print(f"[FAIL] {message}")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def get_runtime_version() -> str:
    from src.ai_write_x.version import get_version

    return get_version()


def check_version_alignment() -> bool:
    version = get_runtime_version()
    ok = True

    pyproject = tomllib.loads(_read_text(ROOT / "pyproject.toml"))
    pyproject_version = pyproject.get("project", {}).get("version")
    if pyproject_version != version:
        _fail(f"pyproject.toml version {pyproject_version!r} != runtime version {version!r}")
        ok = False

    installer = _read_text(ROOT / "aiwritex_installer.iss")
    app_version = re.search(r"(?m)^AppVersion=(.+)$", installer)
    output_name = re.search(r"(?m)^OutputBaseFilename=(.+)$", installer)
    if not app_version or app_version.group(1).strip() != version:
        _fail("aiwritex_installer.iss AppVersion does not match runtime version")
        ok = False
    if not output_name or f"v{version}" not in output_name.group(1):
        _fail("aiwritex_installer.iss OutputBaseFilename does not include runtime version")
        ok = False

    policy = json.loads(_read_text(ROOT / "version-policy.json"))
    if policy.get("latest_version") != version:
        _fail("version-policy.json latest_version does not match runtime version")
        ok = False
    if f"v{version}" not in str(policy.get("download_url", "")):
        _fail("version-policy.json download_url does not include runtime version")
        ok = False

    if ok:
        _ok(f"Release version metadata is aligned at v{version}")
    return ok


def check_webview2_guid() -> bool:
    files = [
        ROOT / "启动.bat",
        ROOT / "启动小爆来咯.bat",
        ROOT / "aiwritex_installer.iss",
        ROOT / "scripts" / "doctor.py",
    ]
    ok = True
    for path in files:
        text = _read_text(path)
        if WEBVIEW2_RUNTIME_GUID not in text:
            _fail(f"WebView2 runtime GUID missing from {path.relative_to(ROOT)}")
            ok = False
        if OLD_WEBVIEW2_GUID in text:
            _fail(f"Old WebView2 GUID still present in {path.relative_to(ROOT)}")
            ok = False
    if ok:
        _ok("WebView2 runtime detection uses one consistent GUID")
    return ok


def check_packaging_inputs() -> bool:
    required = [
        ROOT / "aiwritex_windows.spec",
        ROOT / "aiwritex_installer.iss",
        ROOT / "build_windows_installer.ps1",
        ROOT / "src" / "ai_write_x" / "assets" / "branding" / "app_icon.ico",
        ROOT / "secrets" / "api_keys.example.yaml",
        ROOT / "z-image专用nf4快速备份.json",
    ]
    missing = [path.relative_to(ROOT) for path in required if not path.exists()]
    if missing:
        for path in missing:
            _fail(f"Required packaging input is missing: {path}")
        return False
    _ok("Required packaging inputs exist")
    return True


def check_spec_does_not_package_local_state() -> bool:
    spec = _read_text(ROOT / "aiwritex_windows.spec")
    blocked_fragments = [
        ".local_secrets",
        "root / 'secrets' / 'api_keys.yaml'",
        'root / "secrets" / "api_keys.yaml"',
        "src' / 'ai_write_x' / 'config' / 'config.yaml",
        'src" / "ai_write_x" / "config" / "config.yaml',
        "install_id.txt",
        "data/",
        "output/",
        "logs/",
    ]
    hits = [fragment for fragment in blocked_fragments if fragment in spec]
    if hits:
        for hit in hits:
            _fail(f"Packaging spec contains release-sensitive fragment: {hit}")
        return False
    _ok("PyInstaller spec avoids direct local config, secrets, data, output, and logs")
    return True


def check_readme_version_alignment() -> bool:
    version = get_runtime_version()
    readme = _read_text(ROOT / "README.md")
    expected = f"当前包版本为 `{version}`"
    if expected not in readme:
        _fail("README.md current version does not match runtime version")
        _fail(f"Expected README fragment: {expected}")
        return False
    _ok("README.md current version matches runtime version")
    return True


def check_factory_config_export() -> bool:
    result = subprocess.run(
        [sys.executable, "scripts/export_factory_config_for_build.py"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode != 0:
        _fail("Factory config export failed")
        print(result.stdout)
        return False

    factory_dir = ROOT / "build" / "factory_config"
    files = [path for path in factory_dir.rglob("*") if path.is_file()]
    ok = True
    for path in files:
        if path.suffix.lower() not in {".yaml", ".yml", ".toml", ".json"}:
            continue
        text = _read_text(path)
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                _fail(f"Potential secret found in factory config: {path.relative_to(ROOT)}")
                ok = False
                break
    if ok:
        _ok("Factory config export is present and contains no detected secrets")
    return ok


def check_local_secret_warning() -> bool:
    local_secret = ROOT / "secrets" / "api_keys.yaml"
    if local_secret.exists():
        _warn("Local secrets/api_keys.yaml exists; release build uses sanitized factory config")
    else:
        _ok("No local secrets/api_keys.yaml file present")
    return True


def check_required_packaging_dependencies() -> bool:
    required = {
        "asyncpg": "scraper PostgreSQL storage",
        "feedparser": "NewsHub RSS parsing",
    }
    missing = [
        f"{module} ({feature})"
        for module, feature in required.items()
        if importlib.util.find_spec(module) is None
    ]
    if missing:
        for item in missing:
            _fail(f"Required packaging dependency is not installed: {item}")
        return False
    _ok("Required packaging dependencies are importable")
    return True


def check_uninstall_user_data_prompt() -> bool:
    installer = _read_text(ROOT / "aiwritex_installer.iss")
    required_fragments = [
        "InitializeUninstall",
        "Delete this user data now?",
        "{userappdata}\\XBoom",
        "DeleteUserDataOnUninstall",
        "MB_DEFBUTTON2",
        "CurUninstallStepChanged",
        "Type: filesandordirs; Name: \"{app}\\_internal\"",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in installer]
    if missing:
        for fragment in missing:
            _fail(f"Installer uninstall user-data prompt is missing: {fragment}")
        return False
    _ok("Installer asks before deleting AppData user data and cleans internal program files")
    return True


def check_update_flow_static_contract() -> bool:
    updater = _read_text(ROOT / "src" / "ai_write_x" / "web" / "api" / "updater.py")
    policy = json.loads(_read_text(ROOT / "version-policy.json"))
    required_policy = [
        "latest_version",
        "download_url",
        "sha256",
        "force_update",
        "update_level",
        "install_mode",
        "auto_download",
        "auto_install",
        "rollout_percent",
    ]
    missing_policy = [key for key in required_policy if key not in policy]
    required_updater_fragments = [
        "Stop-Process -Force",
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "Start-Process",
        "resolve_installed_executable",
        "sha256",
        "prepared_update.json",
        "start_prepared_update",
    ]
    missing_updater = [fragment for fragment in required_updater_fragments if fragment not in updater]
    if missing_policy or missing_updater:
        for key in missing_policy:
            _fail(f"version-policy.json missing update field: {key}")
        for fragment in missing_updater:
            _fail(f"Updater flow missing expected fragment: {fragment}")
        return False

    force_update = bool(policy.get("force_update"))
    update_level = str(policy.get("update_level") or "normal").lower()
    if not force_update and update_level != "critical":
        if policy.get("min_supported_version") == policy.get("latest_version"):
            _fail("Non-critical updates must not set min_supported_version to latest_version")
            return False

    _ok("Updater flow static contract is present")
    return True


def check_version_policy_sha256() -> bool:
    version = get_runtime_version()
    policy = json.loads(_read_text(ROOT / "version-policy.json"))
    installer_path = ROOT / "dist" / "installer" / f"小爆来咯-Setup-v{version}.exe"
    if not installer_path.exists():
        _warn(f"Installer not found for SHA256 check: {installer_path.relative_to(ROOT)}")
        return True

    digest = hashlib.sha256(installer_path.read_bytes()).hexdigest()
    if policy.get("sha256") != digest:
        _fail("version-policy.json sha256 does not match the built installer")
        _fail(f"Expected: {digest}")
        _fail(f"Actual:   {policy.get('sha256')}")
        return False
    _ok("version-policy.json sha256 matches the built installer")
    return True


def main() -> int:
    checks = [
        check_version_alignment,
        check_webview2_guid,
        check_packaging_inputs,
        check_spec_does_not_package_local_state,
        check_readme_version_alignment,
        check_factory_config_export,
        check_local_secret_warning,
        check_required_packaging_dependencies,
        check_uninstall_user_data_prompt,
        check_update_flow_static_contract,
        check_version_policy_sha256,
    ]
    results = [check() for check in checks]
    if all(results):
        print("\nRelease check passed.")
        return 0
    print("\nRelease check failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
