# -*- coding: utf-8 -*-
"""Preflight checks for local development and release packaging."""

from __future__ import annotations

import argparse
import compileall
import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ok(message: str) -> None:
    print(f"[OK] {message}")


def _warn(message: str) -> None:
    print(f"[WARN] {message}")


def _fail(message: str) -> None:
    print(f"[FAIL] {message}")


def check_compile() -> bool:
    ok = compileall.compile_dir(str(SRC), quiet=1)
    ok = compileall.compile_file(str(ROOT / "main.py"), quiet=1) and ok
    if ok:
        _ok("Python sources compile")
    else:
        _fail("Python compilation failed")
    return ok


def check_entrypoint() -> bool:
    entry = SRC / "ai_write_x" / "main.py"
    if entry.exists():
        _ok("Package console entry point exists")
        return True
    _fail("Missing src/ai_write_x/main.py")
    return False


def check_secret_files(release: bool = False) -> bool:
    blocked = [
        ROOT / ".env",
        ROOT / "secrets" / "api_keys.yaml",
        ROOT / "scripts" / "gitee-release.env",
        ROOT / "scripts" / "update-mirror.env",
        ROOT / "scripts" / "usage-stats.env",
    ]
    found = [path for path in blocked if path.exists()]
    if found:
        for path in found:
            relative = path.relative_to(ROOT)
            if release:
                _fail(f"Local secret file exists: {relative}")
            else:
                _warn(f"Local secret file exists: {relative}")
        return not release
    _ok("No local secret files found in release-sensitive paths")
    return True


def check_tracked_runtime_files() -> bool:
    git = os.environ.get("GIT", "git")
    try:
        result = subprocess.run(
            [git, "ls-files", "data", "output", "secrets"],
            cwd=ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception as exc:
        _fail(f"Unable to inspect tracked files: {exc}")
        return False

    allowed = {
        "output/app/.gitkeep",
        "output/article/.gitkeep",
        "output/exe/.gitkeep",
        "secrets/README.md",
        "secrets/api_keys.example.yaml",
    }
    tracked = {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}
    unexpected = sorted(tracked - allowed)
    if unexpected:
        for path in unexpected:
            _fail(f"Runtime/generated file is tracked: {path}")
        return False
    _ok("No unexpected runtime files are tracked")
    return True


def check_config_defaults() -> bool:
    try:
        from src.ai_write_x.config.config import Config

        cfg = Config.get_instance()
        defaults = cfg.default_config
        required = ["api", "img_api", "update", "menu_access", "usage_stats"]
        missing = [key for key in required if key not in defaults]
        if missing:
            _fail(f"Default config missing keys: {', '.join(missing)}")
            return False
        _ok("Default config exposes required sections")
        return True
    except Exception as exc:
        _fail(f"Default config import failed: {exc}")
        return False


def check_pyproject_dependencies() -> bool:
    try:
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    except Exception as exc:
        _fail(f"Unable to parse pyproject.toml: {exc}")
        return False

    dependencies = data.get("project", {}).get("dependencies", [])
    normalized = {
        dep.split(";", 1)[0]
        .split("[", 1)[0]
        .split("=", 1)[0]
        .split(">", 1)[0]
        .split("<", 1)[0]
        .strip()
        .lower()
        for dep in dependencies
    }
    required = {"fastapi", "uvicorn", "sqlmodel", "pywebview", "requests", "crewai", "pydantic"}
    missing = sorted(required - normalized)
    if missing:
        _fail(f"pyproject.toml missing core dependencies: {', '.join(missing)}")
        return False

    scripts = data.get("project", {}).get("scripts", {})
    if scripts.get("ai_write_x") != "ai_write_x.main:run" or scripts.get("test") != "ai_write_x.main:test":
        _fail("pyproject.toml console scripts are not wired to package entry points")
        return False

    _ok("pyproject metadata exposes core dependencies and scripts")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run XBoom development/release preflight checks.")
    parser.add_argument(
        "--release",
        action="store_true",
        help="Fail when release-sensitive local secret files are present.",
    )
    args = parser.parse_args(argv)

    checks = [
        check_compile,
        check_entrypoint,
        lambda: check_secret_files(release=args.release),
        check_tracked_runtime_files,
        check_config_defaults,
        check_pyproject_dependencies,
    ]
    results = [check() for check in checks]
    if all(results):
        print("\nPreflight passed.")
        return 0
    print("\nPreflight failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
