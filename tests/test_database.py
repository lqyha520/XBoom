from src.ai_write_x.database.models import Article, ScheduledTask, Topic
from sqlalchemy import create_engine, text

from src.ai_write_x.database import MigrationManager


def test_article_schema_keeps_content_required_and_publish_state_explicit():
    assert Article.model_fields["content"].is_required()
    assert Article.model_fields["is_published"].default is False
    assert Article.model_fields["published_at"].default is None


def test_topic_and_scheduler_defaults_match_primary_workflow():
    assert Topic.model_fields["hot_score"].default == 0
    assert ScheduledTask.model_fields["platform"].default == "wechat"
    assert ScheduledTask.model_fields["article_count"].default == 1
    assert ScheduledTask.model_fields["collection_mode"].default is False
    assert ScheduledTask.model_fields["target_account_id"].default is None
    assert ScheduledTask.model_fields["post_action"].default == "publish"
    assert ScheduledTask.model_fields["repeat_mode"].default == "interval"
    assert ScheduledTask.model_fields["image_style"].default == "auto"
    assert ScheduledTask.model_fields["account_binding_mode"].default == "default"
    assert ScheduledTask.model_fields["preflight_status"].default == "unchecked"
    assert ScheduledTask.model_fields["preflight_message"].default is None


def test_scheduler_binding_migration_preserves_old_rows():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE scheduled_tasks (id VARCHAR PRIMARY KEY, target_appid VARCHAR, target_account_id VARCHAR)"))
        conn.execute(text("INSERT INTO scheduled_tasks VALUES ('fixed', 'wx1', 'account-1')"))
        conn.execute(text("INSERT INTO scheduled_tasks VALUES ('none', NULL, NULL)"))

    MigrationManager(engine).run_migrations()

    with engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(scheduled_tasks)"))}
        modes = {row[0]: row[1] for row in conn.execute(text("SELECT id, account_binding_mode FROM scheduled_tasks"))}
    assert {"account_binding_mode", "preflight_status", "preflight_message", "preflight_checked_at"} <= columns
    assert modes == {"fixed": "fixed", "none": "none"}
