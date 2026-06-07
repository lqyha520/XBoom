# -*- coding: utf-8 -*-
"""Verify the Windows installer with a temporary install/uninstall cycle.

The script is intentionally conservative: it never deletes the real user data
folder. It creates a sentinel file in AppData and verifies silent uninstall
preserves it. If another XBoom instance is already running, launch validation is
skipped by default because the desktop app intentionally enforces single
instance behavior.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ai_write_x.branding.install import APP_BRAND, APP_SLUG, EXE_NAME


def _print(message: str) -> None:
    safe = message.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
        sys.stdout.encoding or "utf-8"
    )
    print(safe)


def _ok(message: str) -> None:
    _print(f"[OK] {message}")


def _warn(message: str) -> None:
    _print(f"[WARN] {message}")


def _fail(message: str) -> None:
    _print(f"[FAIL] {message}")


def run(command: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )


def powershell(script: str, *, timeout: int = 120) -> str:
    result = run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout.strip() or f"PowerShell failed: {result.returncode}")
    return result.stdout


def latest_installer() -> Path:
    candidates = sorted(
        (ROOT / "dist" / "installer").glob(f"{APP_BRAND}-Setup-v*.exe"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError("No installer found in dist/installer")
    return candidates[0]


def process_snapshot() -> list[dict[str, str]]:
    script = r"""
$items = Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*.exe' } | Select-Object ProcessId,Name,ExecutablePath,CommandLine
$items | ConvertTo-Json -Compress
"""
    output = powershell(script, timeout=60).strip()
    if not output:
        return []
    data = json.loads(output)
    if isinstance(data, dict):
        return [data]
    return data


def has_existing_app_instance(install_dir: Path) -> bool:
    install_prefix = str(install_dir).lower()
    for proc in process_snapshot():
        name = str(proc.get("Name") or "")
        exe_path = str(proc.get("ExecutablePath") or "")
        if name.lower() != EXE_NAME.lower():
            continue
        if exe_path and exe_path.lower().startswith(install_prefix):
            continue
        return True
    return False


def stop_processes_under(path: Path) -> None:
    prefix = str(path)
    script = rf"""
$prefix = {json.dumps(prefix)}
Get-CimInstance Win32_Process | Where-Object {{ $_.ExecutablePath -and $_.ExecutablePath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase) }} | ForEach-Object {{
  Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}}
"""
    powershell(script, timeout=60)


def silent_uninstall(install_dir: Path) -> None:
    uninstallers = sorted(install_dir.glob("unins*.exe"))
    if not uninstallers:
        return
    result = run(
        [str(uninstallers[0]), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout.strip() or f"Uninstaller failed: {result.returncode}")


def install(installer: Path, install_dir: Path) -> None:
    result = run(
        [
            str(installer),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            f"/DIR={install_dir}",
        ],
        timeout=240,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout.strip() or f"Installer failed: {result.returncode}")


def wait_for_url_file(startup_url_file: Path, process: subprocess.Popen[object], timeout: float) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if startup_url_file.exists():
            url = startup_url_file.read_text(encoding="utf-8", errors="ignore").strip()
            if url:
                return url
        if process.poll() is not None:
            raise RuntimeError(f"Installed app exited early with code {process.returncode}")
        time.sleep(0.25)
    raise TimeoutError("startup.url was not written within timeout")


def request_ok(url: str, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status == 200:
                    return True
        except Exception as exc:  # pragma: no cover - diagnostics path
            last_error = exc
        time.sleep(0.25)
    if last_error:
        raise RuntimeError(f"Request failed for {url}: {last_error}")
    return False


def launch_check(install_dir: Path, appdata: Path, timeout: float) -> None:
    exe = install_dir / EXE_NAME
    if not exe.exists():
        raise FileNotFoundError(f"Installed executable missing: {exe}")

    logs_dir = appdata / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    startup_url_file = logs_dir / "startup.url"
    crash_log = logs_dir / "desktop_crash.log"
    startup_url_file.unlink(missing_ok=True)
    crash_log.unlink(missing_ok=True)

    proc = subprocess.Popen([str(exe)], cwd=str(install_dir))
    try:
        url = wait_for_url_file(startup_url_file, proc, timeout)
        request_ok(url, timeout=timeout)
        health = url.split("?", 1)[0].rstrip("/") + "/health"
        request_ok(health, timeout=timeout)
        if crash_log.exists() and crash_log.read_text(encoding="utf-8", errors="ignore").strip():
            raise RuntimeError(f"Crash log is not empty: {crash_log}")
        _ok("Installed app launches and health endpoint responds")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        stop_processes_under(install_dir)


def assert_no_runtime_state_in_install_dir(install_dir: Path) -> None:
    forbidden = [
        "logs",
        "previews",
        "data",
        "output",
        "temp",
        "image",
        "knowledge",
        "knowledge_graph.json",
        "port.txt",
        "config/aesthetic_profile.json",
        "data/cookies",
    ]
    leaks = [relative for relative in forbidden if (install_dir / Path(relative)).exists()]
    if leaks:
        raise RuntimeError("Runtime files leaked into install dir: " + ", ".join(leaks))
    _ok("No runtime state leaked into install directory")


def verify(args: argparse.Namespace) -> int:
    if sys.platform != "win32":
        _warn("Installer verification is only supported on Windows")
        return 0 if args.allow_skip else 1

    installer = args.installer or latest_installer()
    install_dir = (args.install_dir or (ROOT / "_installer_verify" / "app")).resolve()
    test_root = install_dir.parent
    appdata = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / APP_SLUG
    sentinel = appdata / "_verify_installer_preserve_sentinel.txt"

    _ok(f"Using installer: {installer}")

    stop_processes_under(install_dir)
    if install_dir.exists():
        silent_uninstall(install_dir)
    if test_root.exists():
        shutil.rmtree(test_root, ignore_errors=True)
    test_root.mkdir(parents=True, exist_ok=True)
    appdata.mkdir(parents=True, exist_ok=True)
    sentinel.write_text(f"preserve-test {time.time()}\n", encoding="utf-8")

    try:
        install(installer, install_dir)
        if not install_dir.exists():
            raise RuntimeError("Install directory was not created")
        _ok("Silent install completed")

        if has_existing_app_instance(install_dir):
            message = "Existing XBoom instance detected; skipping launch check because single-instance guard is expected"
            if args.fail_on_existing_instance:
                raise RuntimeError(message)
            _warn(message)
        else:
            launch_check(install_dir, appdata, args.launch_timeout)

        assert_no_runtime_state_in_install_dir(install_dir)
        silent_uninstall(install_dir)
        time.sleep(2)

        if not sentinel.exists():
            raise RuntimeError("Silent uninstall deleted AppData sentinel unexpectedly")
        _ok("Silent uninstall preserved AppData user data")

        remaining = list(install_dir.rglob("*")) if install_dir.exists() else []
        if remaining:
            sample = "; ".join(str(path) for path in remaining[:5])
            raise RuntimeError(f"Install directory still has files after uninstall: {sample}")
        _ok("Silent uninstall cleaned install directory")

        _print("\nInstaller verification passed.")
        return 0
    except Exception as exc:
        _fail(str(exc))
        _print("\nInstaller verification failed.")
        return 1
    finally:
        sentinel.unlink(missing_ok=True)
        stop_processes_under(install_dir)
        if install_dir.exists():
            silent_uninstall(install_dir)
        if test_root.exists() and not any(test_root.iterdir()):
            test_root.rmdir()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify XBoom Windows installer install/launch/uninstall behavior.")
    parser.add_argument("--installer", type=Path, help="Installer executable to verify. Defaults to latest dist/installer build.")
    parser.add_argument("--install-dir", type=Path, help="Temporary install directory.")
    parser.add_argument("--launch-timeout", type=float, default=90.0, help="Seconds to wait for installed app launch checks.")
    parser.add_argument("--fail-on-existing-instance", action="store_true", help="Fail instead of skipping launch check when another XBoom is already running.")
    parser.add_argument("--allow-skip", action="store_true", help="Return success when verification is skipped on non-Windows platforms.")
    return verify(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
