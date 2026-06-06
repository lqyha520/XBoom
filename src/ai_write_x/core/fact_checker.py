import json
import re
from dataclasses import dataclass, field
from typing import List, Optional

from src.ai_write_x.core.llm_client import LLMClient
from src.ai_write_x.core.prompt_loader import prompt_loader
from src.ai_write_x.utils import log as lg


@dataclass
class FactCheckIssue:
    issue_type: str
    location: str
    description: str
    severity: str
    suggestion: str


@dataclass
class FactCheckResult:
    passed: bool = True
    issues: List[FactCheckIssue] = field(default_factory=list)
    summary: str = ""
    raw_json: str = ""

    @property
    def high_severity_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "high")

    @property
    def has_high_severity(self) -> bool:
        return self.high_severity_count > 0


class FactChecker:
    @classmethod
    def check(
        cls,
        content: str,
        topic: str,
        source_publish_time: str = "未知",
        current_date_str: str = "",
    ) -> FactCheckResult:
        if not content or len(content.strip()) < 100:
            return FactCheckResult(passed=True, summary="内容过短，跳过事实核查")

        if not current_date_str:
            from datetime import datetime
            current_date_str = datetime.now().strftime("%Y年%m月%d日")

        client = LLMClient()
        system_prompt = prompt_loader.get("fact_checker.yaml", "fact_checker", "system_prompt")
        user_prompt = prompt_loader.get("fact_checker.yaml", "fact_checker", "user_prompt").format(
            topic=topic,
            source_publish_time=source_publish_time,
            current_date_str=current_date_str,
            content=content,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = client.chat(messages=messages)
            return cls._parse_response(response)
        except Exception as e:
            lg.print_log(f"[FactChecker] 事实核查异常: {e}", "error")
            return FactCheckResult(passed=True, summary=f"核查异常，放行: {e}")

    @classmethod
    def fix(
        cls,
        content: str,
        fact_check_result: FactCheckResult,
        topic: str,
    ) -> str:
        if fact_check_result.passed or not fact_check_result.issues:
            return content

        report_lines = []
        for i, issue in enumerate(fact_check_result.issues, 1):
            report_lines.append(
                f"{i}. [{issue.severity.upper()}] {issue.issue_type}: {issue.description}\n"
                f"   位置: {issue.location}\n"
                f"   建议: {issue.suggestion}"
            )
        fact_check_report = "\n".join(report_lines)

        client = LLMClient()
        system_prompt = prompt_loader.get("fact_checker.yaml", "fact_fix", "system_prompt")
        user_prompt = prompt_loader.get("fact_checker.yaml", "fact_fix", "user_prompt").format(
            topic=topic,
            fact_check_report=fact_check_report,
            content=content,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            fixed = client.chat(messages=messages)
            if fixed and len(fixed.strip()) > len(content) * 0.5:
                return fixed.strip()
            lg.print_log("[FactChecker] 修正结果异常（过短），保留原文", "warning")
            return content
        except Exception as e:
            lg.print_log(f"[FactChecker] 事实修正异常: {e}", "error")
            return content

    @staticmethod
    def _parse_response(response: str) -> FactCheckResult:
        if not response:
            return FactCheckResult(passed=True, summary="核查响应为空，默认放行")

        json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
        if not json_match:
            json_match = re.search(r"\{[\s\S]*\}", response)

        if not json_match:
            lg.print_log("[FactChecker] 无法解析核查结果JSON，默认放行", "warning")
            return FactCheckResult(passed=True, summary="无法解析核查结果", raw_json=response)

        try:
            data = json.loads(json_match.group(1) if json_match.lastindex else json_match.group())
        except json.JSONDecodeError:
            lg.print_log("[FactChecker] JSON解析失败，默认放行", "warning")
            return FactCheckResult(passed=True, summary="JSON解析失败", raw_json=response)

        passed = data.get("fact_check_passed", True)
        issues = []
        for item in data.get("issues", []):
            issues.append(FactCheckIssue(
                issue_type=item.get("type", "未知"),
                location=item.get("location", ""),
                description=item.get("description", ""),
                severity=item.get("severity", "low"),
                suggestion=item.get("suggestion", ""),
            ))

        summary = data.get("summary", "")
        return FactCheckResult(
            passed=passed,
            issues=issues,
            summary=summary,
            raw_json=response,
        )
