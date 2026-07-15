from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_health_reports_the_deployment_identity():
    app_source = (ROOT / "src/ai_write_x/web/app.py").read_text(encoding="utf-8")
    assert 'os.environ.get("AIWRITEX_DEPLOYMENT_ID", "local")' in app_source


def test_scheduler_runner_uses_a_linux_singleton_lock_and_graceful_drain():
    runner = (ROOT / "scripts/run_scheduler.py").read_text(encoding="utf-8")
    scheduler = (ROOT / "src/ai_write_x/core/scheduler.py").read_text(encoding="utf-8")
    assert "fcntl.LOCK_EX | fcntl.LOCK_NB" in runner
    assert "scheduler_service.wait_until_idle" in runner
    assert "def wait_until_idle" in scheduler


def test_blue_green_deploy_checks_health_before_nginx_switch():
    script = (ROOT / "scripts/deploy-blue-green.sh").read_text(encoding="utf-8")
    assert 'BLUE_PORT="${XBOOM_BLUE_PORT:-8001}"' in script
    assert 'GREEN_PORT="${XBOOM_GREEN_PORT:-8002}"' in script
    assert "wait_for_health" in script
    assert "wait_for_scheduler_idle" in script
    assert 'exec 9>"$RUNTIME_DIR/deploy-v2.lock"' in script
    assert "exec 9>&-" in script
    assert 'export AIWRITEX_SKIP_STARTUP_TASKS="scheduler"' in script
    assert '"$NGINX_BIN" -t' in script
    assert "systemctl enable xboom-scheduler.service" in script


def test_blue_green_deploy_preserves_all_user_settings_between_releases():
    script = (ROOT / "scripts/deploy-blue-green.sh").read_text(encoding="utf-8")
    assert 'CONFIG_RUNTIME_DIR="${XBOOM_CONFIG_RUNTIME_DIR:-$BASE_DIR/config-runtime}"' in script
    assert 'install -d -m 0700 "$CONFIG_RUNTIME_DIR"' in script
    for name in (
        "config.yaml",
        "aiforge.toml",
        "dimensional_creative_config.yaml",
        "ui_config.json",
        "mcp_services.json",
        "install_id.txt",
        "aesthetic_profile.json",
    ):
        assert name in script
    assert 'cp -aL -- "$source_path" "$CONFIG_RUNTIME_DIR/$path"' in script
    assert 'ln -s "$CONFIG_RUNTIME_DIR/$path" "$release_dir/src/ai_write_x/config/$path"' in script


def test_github_workflow_deploys_only_after_verification():
    workflow = (ROOT / ".github/workflows/deploy-server.yml").read_text(encoding="utf-8")
    assert "needs: verify" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "XBOOM_SSH_PRIVATE_KEY" in workflow
    assert "xboom-deploy.sh deploy" in workflow
    assert "rsync -azc --delete --partial" in workflow
    assert "ServerAliveInterval=30" in workflow
    assert "for attempt in 1 2 3 4 5" in workflow
    assert "scp -P" not in workflow
    assert "git -C" not in workflow
    assert "deployment_id" in workflow
