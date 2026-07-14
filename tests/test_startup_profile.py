from src.ai_write_x.web.startup import get_startup_profile, should_skip_startup_task


def test_lean_profile_defers_heavy_warmups_but_keeps_scheduler():
    assert should_skip_startup_task("global_tools", profile="lean", explicit_skip="")
    assert should_skip_startup_task("batch_processor", profile="lean", explicit_skip="")
    assert should_skip_startup_task("newshub", profile="lean", explicit_skip="")
    assert not should_skip_startup_task("scheduler", profile="lean", explicit_skip="")
    assert not should_skip_startup_task("menu_ip_access", profile="lean", explicit_skip="")


def test_full_profile_preserves_legacy_startup_behavior():
    assert not should_skip_startup_task("global_tools", profile="full", explicit_skip="")
    assert not should_skip_startup_task("batch_processor", profile="full", explicit_skip="")
    assert not should_skip_startup_task("newshub", profile="full", explicit_skip="")


def test_minimal_profile_disables_all_background_services():
    assert should_skip_startup_task("scheduler", profile="minimal", explicit_skip="")
    assert should_skip_startup_task("usage_stats", profile="minimal", explicit_skip="")
    assert should_skip_startup_task("menu_ip_access", profile="minimal", explicit_skip="")


def test_explicit_skip_groups_still_override_full_profile():
    assert should_skip_startup_task("usage_stats", profile="full", explicit_skip="network")
    assert should_skip_startup_task("scheduler", profile="full", explicit_skip="scheduler")
    assert should_skip_startup_task("scheduler", profile="full", explicit_skip="all")


def test_unknown_profile_falls_back_to_lean():
    assert get_startup_profile("unknown-profile") == "lean"
