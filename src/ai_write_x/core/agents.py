from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Generator

from src.ai_write_x.core.prompt_loader import prompt_loader
from src.ai_write_x.utils import log as lg


@dataclass
class AgentResult:
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str = ""


class BaseAgent(ABC):
    name: str = "base_agent"
    display_name: str = "基础Agent"

    def __init__(self):
        self._prompt_loader = prompt_loader

    @abstractmethod
    def execute(self, content: str, topic: str, **kwargs) -> AgentResult:
        pass

    def _log(self, message: str, level: str = "info"):
        lg.print_log(f"[{self.name}] {message}", level)

    def _get_prompt(self, yaml_key: str, *keys: str, default: str = "") -> str:
        return self._prompt_loader.get(f"{self.name}.yaml", yaml_key, *keys, default=default)


class ResearcherAgent(BaseAgent):
    name = "researcher"
    display_name = "研究员"

    def execute(self, content: str, topic: str, **kwargs) -> AgentResult:
        from src.ai_write_x.core.llm_client import LLMClient

        reference_content = kwargs.get("reference_content", "")
        source_publish_time = kwargs.get("source_publish_time", "未知")

        system_prompt = self._prompt_loader.get("researcher.yaml", "researcher", "system_prompt")
        user_prompt = self._prompt_loader.get("researcher.yaml", "researcher", "user_prompt").format(
            topic=topic,
            reference_content=reference_content[:5000] if reference_content else "无参考素材",
            source_publish_time=source_publish_time,
        )

        client = LLMClient()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            result = client.chat(messages=messages)
            return AgentResult(
                content=result,
                metadata={"topic": topic, "has_reference": bool(reference_content)},
            )
        except Exception as e:
            self._log(f"执行失败: {e}", "error")
            return AgentResult(content="", success=False, error=str(e))


class WriterAgent(BaseAgent):
    name = "writer"
    display_name = "写作者"

    def execute(self, content: str, topic: str, **kwargs) -> AgentResult:
        from src.ai_write_x.core.llm_client import LLMClient
        from src.ai_write_x.config.config import Config

        config = Config()
        research_data = content
        reference_content = kwargs.get("reference_content", "")
        min_len = config.min_article_len
        max_len = config.max_article_len

        if reference_content:
            core_req = self._prompt_loader.get_writer("core_requirements_with_reference").format(
                min_article_len=min_len, max_article_len=max_len
            )
        else:
            core_req = self._prompt_loader.get_writer("core_requirements_no_reference").format(
                min_article_len=min_len, max_article_len=max_len
            )

        system_prompt = self._prompt_loader.get_writer("persona_framework")
        user_prompt = f"{core_req}\n\n话题：{topic}\n\n"
        if research_data:
            user_prompt += f"【研究员输出】\n{research_data[:3000]}\n\n"
        if reference_content:
            user_prompt += f"【参考素材】\n{reference_content[:5000]}\n"

        client = LLMClient()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            result = ""
            for chunk in client.stream_chat(messages=messages):
                if chunk:
                    result += chunk
            return AgentResult(
                content=result,
                metadata={"topic": topic, "content_length": len(result)},
            )
        except Exception as e:
            self._log(f"执行失败: {e}", "error")
            return AgentResult(content="", success=False, error=str(e))


class ReviewerAgent(BaseAgent):
    name = "reviewer"
    display_name = "审核员"

    def execute(self, content: str, topic: str, **kwargs) -> AgentResult:
        from src.ai_write_x.core.final_reviewer import FinalReviewer

        try:
            review_result = FinalReviewer.assess_quality(content, {"topic": topic})
            return AgentResult(
                content=review_result.get("report", ""),
                metadata={
                    "passed": review_result.get("pass", True),
                    "score": review_result.get("score", 0),
                    "issue_categories": review_result.get("issue_categories", []),
                },
            )
        except Exception as e:
            self._log(f"执行失败: {e}", "error")
            return AgentResult(content="", success=False, error=str(e))


class FormatterAgent(BaseAgent):
    name = "formatter"
    display_name = "排版师"

    def execute(self, content: str, topic: str, **kwargs) -> AgentResult:
        from src.ai_write_x.core.visual_assets import VisualAssetsManager

        publish_platform = kwargs.get("publish_platform", "wechat")
        fast_mode = kwargs.get("fast_mode", False)

        try:
            if fast_mode:
                content = VisualAssetsManager.inject_image_prompts_fast(content)
            else:
                content = VisualAssetsManager.inject_image_prompts(content)

            return AgentResult(
                content=content,
                metadata={"platform": publish_platform},
            )
        except Exception as e:
            self._log(f"执行失败: {e}", "error")
            return AgentResult(content=content, success=False, error=str(e))


AGENT_REGISTRY = {
    "researcher": ResearcherAgent,
    "writer": WriterAgent,
    "reviewer": ReviewerAgent,
    "formatter": FormatterAgent,
    "fact_checker": lambda: __import__(
        "src.ai_write_x.core.fact_checker", fromlist=["FactChecker"]
    ).FactChecker,
}


def get_agent(name: str) -> BaseAgent:
    if name not in AGENT_REGISTRY:
        raise ValueError(f"未知Agent: {name}")
    cls = AGENT_REGISTRY[name]
    if callable(cls) and not isinstance(cls, type):
        return cls()
    return cls()
