from src.ai_write_x.core.article_polish import clean_meta_template_phrases


def test_clean_meta_heading_prefix_from_plain_text():
    content = "## 结语：穿越周期的力量\n\n真正能留下来的，不是短期热度。"

    cleaned = clean_meta_template_phrases(content)

    assert "结语" not in cleaned
    assert "穿越周期的力量" in cleaned
    assert "真正能留下来的" in cleaned


def test_clean_meta_heading_prefix_from_bold_text():
    content = "**结语：穿越周期的力量**\n\n周期会奖励长期主义。"

    cleaned = clean_meta_template_phrases(content)

    assert "结语" not in cleaned
    assert "穿越周期的力量" in cleaned
    assert "周期会奖励长期主义" in cleaned


def test_clean_meta_heading_prefix_from_html_heading():
    content = "<article><h2>结语：穿越周期的力量</h2><p>长期主义不是口号。</p></article>"

    cleaned = clean_meta_template_phrases(content)

    assert "结语" not in cleaned
    assert "<h2>穿越周期的力量</h2>" in cleaned
    assert "长期主义不是口号" in cleaned
