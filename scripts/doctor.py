# -*- coding: utf-8 -*-
"""Local environment diagnostics for XBoom."""

from __future__ import annotations

import importlib.util
import os
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CHECKS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> bool:
    CHECKS.append((name, ok, detail))
    status = "OK" if ok else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")
    return ok


def warn(name: str, detail: str) -> None:
    CHECKS.append((name, True, f"WARN: {detail}"))
    print(f"[WARN] {name} - {detail}")


def check_python() -> bool:
    version = sys.version_info
    detail = f"{version.major}.{version.minor}.{version.micro} ({sys.executable})"
    return record("Python version", (3, 10) <= (version.major, version.minor) < (3, 13), detail)


def check_virtualenv() -> bool:
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return record("Virtual environment", True, str(venv_python.relative_to(ROOT)))
    warn("Virtual environment", ".venv not found; startup will use system Python")
    return True


def check_imports() -> bool:
    packages = [
        "fastapi",
        "uvicorn",
        "sqlmodel",
        "pydantic",
        "requests",
        "webview",
        "yaml",
    ]
    missing = [pkg for pkg in packages if importlib.util.find_spec(pkg) is None]
    return record("Core dependency imports", not missing, ", ".join(missing) if missing else "all present")


def check_webview2() -> bool:
    if os.name != "nt":
        return record("WebView2 runtime", True, "not required on this platform")

    keys = [
        r"HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        r"HKLM\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        r"HKCU\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
    ]
    for key in keys:
        result = subprocess.run(
            ["reg", "query", key, "/v", "pv"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return record("WebView2 runtime", True, "installed")
    warn("WebView2 runtime", "not detected; desktop mode may fail, browser mode can still work")
    return True


def check_config_and_secrets() -> bool:
    config_file = ROOT / "src" / "ai_write_x" / "config" / "config.yaml"
    example_secret = ROOT / "secrets" / "api_keys.example.yaml"
    local_secret = ROOT / "secrets" / "api_keys.yaml"

    ok = True
    ok = record("Default config file", config_file.exists(), str(config_file.relative_to(ROOT))) and ok
    ok = record("Secret example file", example_secret.exists(), str(example_secret.relative_to(ROOT))) and ok
    if local_secret.exists():
        warn("Local API key file", "present and ignored by git")
    else:
        warn("Local API key file", "not found; AI provider calls may need configuration before use")
    return ok


def check_writable_paths() -> bool:
    try:
        from src.ai_write_x.utils.path_manager import PathManager

        paths = [
            PathManager.get_output_dir(),
            PathManager.get_article_dir(),
            PathManager.get_image_dir(),
            PathManager.get_log_dir(),
            PathManager.get_temp_dir(),
        ]
    except Exception as exc:
        return record("Writable runtime paths", False, str(exc))

    ok = True
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
        test_file = path / ".doctor_write_test"
        try:
            test_file.touch()
            test_file.unlink()
        except OSError as exc:
            ok = False
            record(f"Writable path {path}", False, str(exc))
    if ok:
        record("Writable runtime paths", True, "output/image/log/temp paths writable")
    return ok


def check_ports() -> bool:
    ok = True
    for port in (7000, 4433):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            busy = sock.connect_ex(("127.0.0.1", port)) == 0
        if busy:
            warn(f"Port {port}", "already in use")
        else:
            record(f"Port {port}", True, "available")
    return ok


def check_startup_smoke() -> bool:
    result = subprocess.run(
        [sys.executable, "scripts/startup_smoke_check.py"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    detail = "passed" if result.returncode == 0 else "failed; run scripts/startup_smoke_check.py for details"
    return record("Startup smoke check", result.returncode == 0, detail)


def main() -> int:
    print("XBoom environment diagnostics")
    print("=" * 32)
    print(f"Project: {ROOT}")
    print()

    checks = [
        check_python,
        check_virtualenv,
        check_imports,
        check_webview2,
        check_config_and_secrets,
        check_writable_paths,
        check_ports,
        check_startup_smoke,
    ]
    results = [check() for check in checks]

    print()
    if all(results):
        print("Doctor passed. The local environment looks ready.")
        return 0
    print("Doctor found blocking issues. Fix the [FAIL] items above and run again.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
