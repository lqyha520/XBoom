from src.ai_write_x.database.models import Article, ScheduledTask, Topic


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
