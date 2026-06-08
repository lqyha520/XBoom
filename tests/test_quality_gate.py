# -*- coding: utf-8 -*-
"""Regression tests for local quality gate wiring."""

from __future__ import annotations

from pathlib import Path
from hashlib import sha256


def test_quick_gate_includes_security_regressions():
    from scripts import run_quick_tests

    assert "tests/test_quality_gate.py" in run_quick_tests.CORE_TESTS
    assert "tests/test_scheduler_api.py" in run_quick_tests.CORE_TESTS
    assert "tests/test_web_security.py" in run_quick_tests.CORE_TESTS


def test_clean_workspace_defaults_to_dry_run():
    source = Path("scripts/clean_workspace.py")

    assert source.exists()
    text = source.read_text(encoding="utf-8")
    assert "--apply" in text
    assert "dry_run" in text


def test_generated_api_keys_yaml_is_release_warning_not_failure():
    source = Path("scripts/preflight_check.py").read_text(encoding="utf-8")

    assert 'ROOT / "secrets" / "api_keys.yaml"' in source
    assert "local_runtime_only" in source
    assert "Local runtime secret exists but is ignored and not packaged" in source


def test_known_sensitive_literals_are_not_tracked():
    forbidden_hashes = {
        "1e4c06b3ef9581b4b00c208603de985f33263ce3d538da16d2210e2645b8313e",
        "a323cd0e49e5e7c81ccd8a2b88643042e629e1959c51b8253ccdbcdfa45e78b8",
    }
    tracked_paths = [
        Path("src/ai_write_x/config/config.yaml"),
        Path("scripts/_remote_patch_xboom_row.py"),
        Path("scripts/_remote_encrypt_bt_pass.py"),
        Path("scripts/_remote_enc2.py"),
        Path("scripts/_remote_enc3.py"),
    ]

    for path in tracked_paths:
        text = path.read_text(encoding="utf-8")
        words = set(text.replace('"', " ").replace("'", " ").replace(":", " ").split())
        leaked = {
            digest
            for word in words
            if (digest := sha256(word.encode("utf-8")).hexdigest()) in forbidden_hashes
        }
        assert not leaked, f"known sensitive literal leaked in {path}"


def test_release_quick_gate_uses_release_preflight():
    source = Path("scripts/run_quick_tests.py").read_text(encoding="utf-8")

    assert 'preflight.append("--release")' in source


def test_ops_scripts_use_shared_secret_helpers():
    helper = Path("scripts/ops_secrets.py")
    assert helper.exists()

    scripts = [
        Path("scripts/_remote_patch_xboom_row.py"),
        Path("scripts/_remote_encrypt_bt_pass.py"),
        Path("scripts/_remote_enc2.py"),
        Path("scripts/_remote_enc3.py"),
    ]
    for script in scripts:
        text = script.read_text(encoding="utf-8")
        assert "ops_secrets" in text


def test_text_encoding_audit_exposes_scanner():
    from scripts import audit_text_encoding

    assert audit_text_encoding.MOJIBAKE_MARKERS
    findings = audit_text_encoding.scan_file(Path("README.md"))
    assert findings == []


def test_release_gate_runs_expected_checks():
    source = Path("scripts/release_gate.py")
    assert source.exists()
    text = source.read_text(encoding="utf-8")

    assert "preflight_check.py" in text
    assert "--release" in text
    assert "release_check.py" in text
    assert "audit_text_encoding.py" in text
    assert "run_quick_tests.py" in text


def test_startup_optional_task_switch_is_documented_in_code():
    source = Path("src/ai_write_x/web/app.py").read_text(encoding="utf-8")

    assert "AIWRITEX_SKIP_STARTUP_TASKS" in source
    assert "_schedule_optional_startup_task" in source
    assert "OPTIONAL_STARTUP_GROUPS" in source
    assert "_schedule_optional_startup_sync_task" in source
    assert "asyncio.to_thread(func" in source
    assert "_optional_startup_tasks.add(task)" in source
    assert "await asyncio.gather(*list(_optional_startup_tasks), return_exceptions=True)" in source
    assert "await batch_processor.stop()" in source
    assert "await ws_manager.stop()" in source


def test_updater_invalid_prepared_state_is_cleared():
    source = Path("src/ai_write_x/web/api/updater.py").read_text(encoding="utf-8")

    assert "_verify_installer_sha256(installer_path, str(data.get(\"sha256\") or \"\"), log_success=False)" in source
    assert "_clear_prepared_update_state()" in source
    assert "installer_path.with_suffix(installer_path.suffix + \".part\").unlink" in source
    assert "if _update_progress.get(\"status\") == \"ready_to_install\" and not has_prepared_update():" in source
    assert "\"sha256\": expected_sha256" in source
    assert "installer_path = _coerce_installer_path(state.get(\"download_path\"))" in source
    assert "if installer_path is None:" in source
    assert "path.is_file()" in source
    assert "path.suffix.lower() != \".exe\"" in source


def test_manual_generation_stop_is_scoped_away_from_scheduler():
    generate_source = Path("src/ai_write_x/web/api/generate.py").read_text(encoding="utf-8")
    manager_source = Path("src/ai_write_x/core/task_manager.py").read_text(encoding="utf-8")
    scheduler_source = Path("src/ai_write_x/core/scheduler.py").read_text(encoding="utf-8")
    scheduler_api_source = Path("src/ai_write_x/web/api/scheduler.py").read_text(encoding="utf-8")

    assert 'task_manager.stop_task("main_generate")' in generate_source
    assert 'status = "success" if success else "idle"' in generate_source
    assert "没有正在运行的手动生成任务" in generate_source
    assert 'task["stop_requested"] = True' in manager_source
    assert "def is_stop_requested" in manager_source
    assert "p.kill()" in manager_source
    assert 'is_stop_requested("main_generate")' in generate_source
    assert 'register_sub_process("main_generate", process)' in generate_source
    assert '"main_generate"' not in scheduler_source
    assert '"main_generate"' not in scheduler_api_source
    assert "stop_task(" not in scheduler_source
    assert "stop_task(" not in scheduler_api_source


def test_scheduler_has_independent_cancel_and_duplicate_guards():
    scheduler_source = Path("src/ai_write_x/core/scheduler.py").read_text(encoding="utf-8")
    scheduler_api_source = Path("src/ai_write_x/web/api/scheduler.py").read_text(encoding="utf-8")
    scheduler_js_source = Path("src/ai_write_x/web/static/js/scheduler-manager.js").read_text(encoding="utf-8")

    assert "def request_cancel" in scheduler_source
    assert "def is_cancel_requested" in scheduler_source
    assert "cancel_requested" in scheduler_source
    assert "cancelled" in scheduler_source
    assert "_running_task_ids" in scheduler_source
    assert "_mark_task_thread_started" in scheduler_source
    assert "skipped duplicate launch" in scheduler_source
    assert "Generating article" in scheduler_source
    assert "Task started, planned articles" in scheduler_source
    assert '@router.post("/tasks/{task_id}/cancel")' in scheduler_api_source
    assert "scheduler_service.request_cancel(task_id)" in scheduler_api_source
    assert "cancelTask(id)" in scheduler_js_source
    assert "/cancel" in scheduler_js_source
    assert "取消本次执行" in scheduler_js_source
    assert "getLogStatusText" in scheduler_js_source


def test_workflow_supports_cooperative_cancellation():
    workflow_source = Path("src/ai_write_x/core/unified_workflow.py").read_text(encoding="utf-8")
    crew_source = Path("src/ai_write_x/crew_main.py").read_text(encoding="utf-8")
    generate_source = Path("src/ai_write_x/web/api/generate.py").read_text(encoding="utf-8")
    scheduler_source = Path("src/ai_write_x/core/scheduler.py").read_text(encoding="utf-8")
    manager_source = Path("src/ai_write_x/core/task_manager.py").read_text(encoding="utf-8")

    assert "class WorkflowCancelled" in workflow_source
    assert "cancel_check" in workflow_source
    assert "_raise_if_cancelled" in workflow_source
    assert "base_content_stream" in workflow_source
    assert "_stream_article_rewrite_checked" in workflow_source
    assert '"cancelled": True' in workflow_source
    assert "cancel_marker_path" in crew_source
    assert "os.path.exists(path)" in crew_source
    assert "cancel_marker_path" in generate_source
    assert "cancel_check" in scheduler_source
    assert "is_cancel_marker_set" in manager_source


def test_scheduler_frontend_escapes_dynamic_content():
    scheduler_js_source = Path("src/ai_write_x/web/static/js/scheduler-manager.js").read_text(encoding="utf-8")

    assert "escapeHtml(this.truncate(this._taskLabel(task)" in scheduler_js_source
    assert "escapeHtml(entry.message || '')" in scheduler_js_source
    assert "tipEl.textContent" in scheduler_js_source
    assert "tipEl.innerHTML" not in scheduler_js_source
