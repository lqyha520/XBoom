from pathlib import Path

import pytest

from src.ai_write_x.core.series_topics import (
    SeriesTopicPlanningError,
    filter_recent_topics_for_series,
    normalize_series_name,
    plan_series_topics,
    sanitize_subtopic,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSHOP_SCRIPT = ROOT / "src/ai_write_x/web/static/js/creative-workshop.js"
GENERATE_API = ROOT / "src/ai_write_x/web/api/generate.py"
SCHEDULER = ROOT / "src/ai_write_x/core/scheduler.py"
UNIFIED_WORKFLOW = ROOT / "src/ai_write_x/core/unified_workflow.py"


class FakeChat:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def __call__(self, messages, temperature=0.7):
        self.prompts.append(messages[0]["content"])
        return self.responses.pop(0)


def test_series_name_and_subtopic_normalization_are_domain_agnostic():
    assert normalize_series_name("  科技趋势：AI 芯片  ") == "科技趋势"
    assert normalize_series_name("健康管理:睡眠") == "健康管理"
    assert sanitize_subtopic("1. 科技趋势：端侧模型的新机会", "科技趋势") == "端侧模型的新机会"
    assert sanitize_subtopic("美食专题：家庭烘焙", "科技趋势") == "美食专题：家庭烘焙"


def test_recent_topics_are_isolated_by_series():
    recent = [
        "科技趋势：端侧模型的新机会",
        "健康管理：改善睡眠质量",
        "科技趋势：AI 芯片成本变化",
        "旅行攻略：夏季避暑路线",
    ]

    assert filter_recent_topics_for_series(recent, "科技趋势") == [
        "科技趋势：端侧模型的新机会",
        "科技趋势：AI 芯片成本变化",
    ]


def test_planner_repairs_cross_domain_candidates_before_returning():
    chat = FakeChat(
        [
            '{"topics":["亲子沟通中的情绪管理","远程团队晋升路径"]}',
            '{"valid":true,"topics":["跨部门协作中的晋升筹码","远程团队的绩效可见度"],"issues":[]}',
        ]
    )

    topics = plan_series_topics(
        chat,
        "职场成长",
        2,
        seed_topic="职场成长：远程协作与晋升",
        recent_topics=[
            "育儿经验：孩子情绪管理",
            "职场成长：高潜员工的能力模型",
        ],
    )

    assert topics == [
        "职场成长：跨部门协作中的晋升筹码",
        "职场成长：远程团队的绩效可见度",
    ]
    assert "育儿经验：孩子情绪管理" not in chat.prompts[0]
    assert "职场成长：高潜员工的能力模型" in chat.prompts[0]
    assert "本次方向：远程协作与晋升" in chat.prompts[0]


def test_planner_fails_closed_when_scope_review_keeps_failing():
    chat = FakeChat(
        [
            '{"topics":["完全无关的话题"]}',
            '{"valid":false,"topics":["仍然无关的话题"],"issues":["跨领域"]}',
            '{"valid":false,"topics":["还是无关的话题"],"issues":["跨领域"]}',
        ]
    )

    with pytest.raises(SeriesTopicPlanningError, match="未通过范围审核"):
        plan_series_topics(chat, "法律科普", 1)


def test_generation_paths_share_the_series_scope_contract():
    workshop = WORKSHOP_SCRIPT.read_text(encoding="utf-8")
    generate_api = GENERATE_API.read_text(encoding="utf-8")
    scheduler = SCHEDULER.read_text(encoding="utf-8")
    unified_workflow = UNIFIED_WORKFLOW.read_text(encoding="utf-8")

    assert "let topic = (topicInput?.value || '').trim();" in workshop
    assert "series_name: seriesName" in workshop
    assert "实际提交：系列" in workshop
    assert "plan_series_topics(" in generate_api
    assert '"series_name": requested_series_name' in generate_api
    assert "[GenerateContract]" in generate_api
    assert "成功/失败信号已在对应分支发送" in generate_api
    assert "plan_series_topics(" in scheduler
    assert "title = topic" in unified_workflow
    assert "不得再次改题" in unified_workflow
