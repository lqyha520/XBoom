# -*- coding: utf-8 -*-
"""Startup smoke checks that avoid launching the desktop GUI."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ok(message: str) -> None:
    print(f"[OK] {message}")


def _fail(message: str) -> None:
    print(f"[FAIL] {message}")


def _check_paths(paths: Iterable[Path]) -> bool:
    ok = True
    for path in paths:
        if not path.exists():
            _fail(f"Required startup path does not exist: {path}")
            ok = False
            continue
        if path.is_dir():
            test_file = path / ".startup_write_test"
            try:
                test_file.touch()
                test_file.unlink()
            except OSError as exc:
                _fail(f"Startup path is not writable: {path} ({exc})")
                ok = False
    if ok:
        _ok("Startup paths exist and writable runtime paths accept writes")
    return ok


def check_root_entrypoint() -> bool:
    root_main = ROOT / "main.py"
    spec = importlib.util.spec_from_file_location("xboom_root_main_smoke", root_main)
    if spec is None or spec.loader is None:
        _fail(f"Cannot load root launcher: {root_main}")
        return False

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        _fail(f"Root launcher import failed: {exc}")
        return False

    if not callable(getattr(module, "run", None)):
        _fail("Root launcher does not expose run().")
        return False

    _ok("Root launcher imports and exposes run()")
    return True


def check_config_and_paths() -> bool:
    try:
        from src.ai_write_x.config.config import Config
        from src.ai_write_x.utils.path_manager import PathManager

        config = Config.get_instance()
        defaults = config.default_config
        if "api" not in defaults or "update" not in defaults:
            _fail("Config defaults are missing required startup sections")
            return False

        paths = [
            PathManager.get_config_dir(),
            PathManager.get_output_dir(),
            PathManager.get_article_dir(),
            PathManager.get_image_dir(),
            PathManager.get_log_dir(),
            PathManager.get_temp_dir(),
        ]
        return _check_paths(paths)
    except Exception as exc:
        _fail(f"Config/path startup check failed: {exc}")
        return False


def check_database() -> bool:
    try:
        from src.ai_write_x.database.db_manager import DBManager

        db = DBManager()
        stats = db.get_system_stats()
        required = {"total_topics", "total_articles", "total_memories", "lessons_learned"}
        if not required.issubset(stats):
            _fail(f"Database stats missing keys: {sorted(required - set(stats))}")
            return False
        _ok("Database manager initializes and returns system stats")
        return True
    except Exception as exc:
        _fail(f"Database startup check failed: {exc}")
        return False


def check_web_app() -> bool:
    try:
        from src.ai_write_x.web.app import app, health_check

        routes = {getattr(route, "path", None) for route in app.routes}
        required = {"/", "/health", "/static", "/images", "/output"}
        missing = sorted(required - routes)
        if missing:
            _fail(f"Web app missing startup routes/mounts: {', '.join(missing)}")
            return False

        health = asyncio.run(health_check())
        if health.get("status") != "healthy":
            _fail(f"Health check returned unexpected status: {health}")
            return False

        _ok("Web app imports, routes are mounted, and health check is healthy")
        return True
    except Exception as exc:
        _fail(f"Web startup check failed: {exc}")
        return False


def main() -> int:
    checks = [
        check_root_entrypoint,
        check_config_and_paths,
        check_database,
        check_web_app,
    ]
    results = [check() for check in checks]
    if all(results):
        print("\nStartup smoke check passed.")
        return 0
    print("\nStartup smoke check failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
