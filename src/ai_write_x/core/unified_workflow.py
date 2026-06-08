import os
import re
import time
import json
import asyncio
from typing import Callable, Dict, Any, Generator, Optional

from src.ai_write_x.core.base_framework import (
    WorkflowConfig,
    AgentConfig,
    TaskConfig,
    WorkflowType,
    ContentType,
    ContentResult,
)
from src.ai_write_x.core.prompt_loader import prompt_loader
from src.ai_write_x.core.platform_adapters import (
    WeChatAdapter,
    XiaohongshuAdapter,
    DouyinAdapter,
    ToutiaoAdapter,
    BaijiahaoAdapter,
    ZhihuAdapter,
    DoubanAdapter,
)
from src.ai_write_x.core.monitoring import WorkflowMonitor
from src.ai_write_x.config.config import Config
from src.ai_write_x.core.content_generation import ContentGenerationEngine
from src.ai_write_x.utils.path_manager import PathManager
from src.ai_write_x.utils import utils
from src.ai_write_x.core.platform_adapters import PlatformType
import src.ai_write_x.utils.log as lg

# 导入维度化创意引擎
from src.ai_write_x.core.dimensional_engine import DimensionalCreativeEngine
try:
    from src.ai_write_x.core.dynamic_design_engine import DynamicDesignEngine
    DYNAMIC_DESIGN_AVAILABLE = True
except ImportError:
    DYNAMIC_DESIGN_AVAILABLE = False
    import src.ai_write_x.utils.log as lg
    lg.print_log("⚠️ DynamicDesignEngine 不可用，将使用内置强化模板", "warning")

from src.ai_write_x.core.wechat_preview import WeChatPreviewEngine
from src.ai_write_x.database import init_db


class WorkflowCancelled(Exception):
    """Raised when a caller requests cooperative workflow cancellation."""



class UnifiedContentWorkflow:
    """统一的内容工作流编排器"""

    def __init__(self):
        try:
            from src.ai_write_x.core.system_init import initialize_global_tools
            initialize_global_tools()
        except Exception as e:
            lg.print_log(f"工具注册跳过: {e}", "warning")
        self.content_engine = None
        # 移除所有旧创意模块，只保留维度化创意引擎
        self.platform_adapters = {
            PlatformType.WECHAT.value: WeChatAdapter(),
            PlatformType.XIAOHONGSHU.value: XiaohongshuAdapter(),
            PlatformType.DOUYIN.value: DouyinAdapter(),
            PlatformType.TOUTIAO.value: ToutiaoAdapter(),
            PlatformType.BAIJIAHAO.value: BaijiahaoAdapter(),
            PlatformType.ZHIHU.value: ZhihuAdapter(),
            PlatformType.DOUBAN.value: DoubanAdapter(),
        }
        self.monitor = WorkflowMonitor.get_instance()
        # 初始化维度化创意引擎
        config = Config.get_instance()
        dimensional_config = config.dimensional_creative_config
        self.creative_engine = DimensionalCreativeEngine(dimensional_config)
        # 初始化数据库
        init_db()

    def _build_draft_prompt(self, topic: str, **kwargs) -> tuple:
        """构建初稿提示词，返回 (system_prompt, user_prompt)"""
        config = Config.get_instance()
        reference_content = kwargs.get("reference_content", "")

        from datetime import datetime
        current_date_str = datetime.now().strftime('%Y年%m月%d日 %H:%M')
        source_publish_time = kwargs.get("date_str", "近期 (以当前时间为准推算)")

        date_context = prompt_loader.get_writer("date_context").format(
            current_date_str=current_date_str,
            source_publish_time=source_publish_time,
        )

        memory_context = ""
        try:
            from src.ai_write_x.core.memory_manager import MemoryManager
            _topic = topic
            memory_manager = MemoryManager()
            memory_context = memory_manager.get_similarity_context(_topic) if _topic else ""
            rag_context = memory_manager.get_rag_context()
            if rag_context:
                memory_context += "\n" + rag_context
        except Exception as e:
            lg.print_log(f"读取记忆库失败: {e}", "warning")

        persona_framework = prompt_loader.get_writer("persona_framework")

        system_parts = [persona_framework, date_context]
        if memory_context:
            system_parts.append(memory_context)
        system_prompt = "\n\n".join(system_parts)

        topic_constraint = prompt_loader.get_writer("topic_constraint").format(topic=topic)

        collection_mode = kwargs.get("collection_mode", False)
        collection_constraint = ""
        if collection_mode:
            series_name = topic.split("：", 1)[0] if "：" in topic else topic
            collection_constraint = (
                f"\n\n【合集模式约束】本文属于「{series_name}」系列合集。"
                f"文章标题必须以「{series_name}：」开头，后接具体的子话题。"
                f"正文中可适当体现系列归属感，但不要生硬重复系列名。"
            )

        if reference_content:
            reference_injection = prompt_loader.get_writer("reference_injection").format(reference_content=reference_content)
            core_requirements = prompt_loader.get_writer("core_requirements_with_reference").format(
                min_article_len=config.min_article_len,
                max_article_len=config.max_article_len,
            )
            execution_instructions = prompt_loader.get_writer("execution_instructions").format(topic=topic)
            user_prompt = f"""{topic_constraint}

{reference_injection}

{core_requirements}

{execution_instructions}

{collection_constraint}"""
        else:
            core_requirements = prompt_loader.get_writer("core_requirements_no_reference").format(
                min_article_len=config.min_article_len,
                max_article_len=config.max_article_len,
            )
            execution_instructions = prompt_loader.get_writer("execution_instructions").format(topic=topic)
            user_prompt = f"""{topic_constraint}

{core_requirements}

{execution_instructions}

{collection_constraint}"""

        return system_prompt, user_prompt

    def _generate_base_content(self, topic: str, **kwargs) -> ContentResult:
        """直接调用 LLM 生成初稿，绕过 CrewAI 框架开销"""
        from src.ai_write_x.core.llm_client import LLMClient
        client = LLMClient()
        cancel_check = self._cancel_check_from_kwargs(kwargs)
        kwargs = self._kwargs_without_runtime_controls(kwargs)

        system_prompt, user_prompt = self._build_draft_prompt(topic, **kwargs)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        lg.print_log("✍️ 正在调用 LLM 生成初稿...", "info")

        result_str = ""
        char_count_logged = 0
        for chunk in client.stream_chat(messages=messages):
            self._raise_if_cancelled(cancel_check, "base_content_stream")
            if chunk:
                result_str += chunk
                if len(result_str) - char_count_logged >= 300:
                    lg.print_log(f"⏳ 初稿生成中... 已生成 {len(result_str)} 字", "status")
                    char_count_logged = len(result_str)

        result_str = utils.remove_code_blocks(result_str).strip()

        if not result_str:
            raise ValueError("LLM 返回空响应")

        title = topic
        lines = result_str.split('\n')
        for line in lines:
            line_stripped = line.strip()
            if line_stripped.startswith('# ') and not line_stripped.startswith('## '):
                title = line_stripped[2:].strip()
                break

        collection_mode = kwargs.get("collection_mode", False)
        if collection_mode:
            series_name = topic.split("：", 1)[0] if "：" in topic else topic
            if not title.startswith(series_name + "：") and not title.startswith(series_name + ":"):
                title = f"{series_name}：{title}"

        lg.print_log(f"✅ 初稿生成完成，约 {len(result_str)} 字", "success")

        return ContentResult(
            title=title,
            content=result_str,
            summary="",
            content_type=ContentType.ARTICLE,
            content_format="markdown",
            metadata={
                "workflow_name": "direct_llm_draft",
                "topic": topic,
            },
        )

    def execute(self, topic: str, **kwargs) -> Dict[str, Any]:
        """兼容旧版同步执行流程，并桥接日志流 (支持增量预览与进度条)"""
        import src.ai_write_x.utils.log as lg
        results = {}
        for step in self.execute_stepwise(topic, **kwargs):
            if step["type"] == "log":
                lg.print_log(step["message"], "info")
            elif step["type"] == "progress":
                lg.print_log(step["message"], "internal")
            elif step["type"] == "chunk":
                lg.print_log(step["message"], "status") # status 类型在前端用于实时预览抓取
            elif step["type"] == "final_results":
                results = step["content"]
        return results

    @staticmethod
    def _cancel_check_from_kwargs(kwargs: Dict[str, Any]) -> Optional[Callable[[], bool]]:
        cancel_check = kwargs.get("cancel_check")
        return cancel_check if callable(cancel_check) else None

    @staticmethod
    def _raise_if_cancelled(cancel_check: Optional[Callable[[], bool]], stage: str):
        if cancel_check and cancel_check():
            raise WorkflowCancelled(f"Workflow cancelled during {stage}")

    @staticmethod
    def _kwargs_without_runtime_controls(kwargs: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = kwargs.copy()
        cleaned.pop("cancel_check", None)
        return cleaned

    # V4: 每阶段最大允许时长（秒）- 用户禁用时间限制，全部设置为99999秒
    STAGE_TIMEOUT = {
        "INIT": 99999,      # 禁用 — 深度洞察
        "CREATIVE": 99999,  # 禁用 — 创意蓝图
        "WRITING": 99999,   # 禁用 — 大师撰稿
        "REVIEW": 99999,    # 禁用 — 打磨重塑
        "VISUAL": 99999,    # 禁用 — 视觉美化
        "SAVE": 99999,      # 禁用 — 持久化
        "COMPLETE": 99999,  # 禁用 — 发布交付
    }

    def _check_stage_timeout(self, stage_name: str, stage_start: float):
        """V4: 检查当前阶段是否超时"""
        elapsed = time.time() - stage_start
        max_time = self.STAGE_TIMEOUT.get(stage_name, 300)
        if elapsed > max_time:
            raise TimeoutError(f"阶段 [{stage_name}] 超时: 已耗时 {elapsed:.0f}秒 (上限 {max_time}秒)")

    @staticmethod
    def _assert_content(content_str: str, stage: str):
        """V4: 内容断言 — 确保生成内容符合最低质量标准"""
        if not content_str or not content_str.strip():
            raise ValueError(f"V4断言失败 [{stage}]: 内容为空")
        clean = content_str.strip()
        if len(clean) < 100:
            raise ValueError(f"V4断言失败 [{stage}]: 内容过短 ({len(clean)}字 < 100字下限)")

    @staticmethod
    def _topic_keyword_overlap(topic: str, content_str: str) -> float:
        """话题关键词在正文中的命中率（用于发现严重跑题）"""
        if not topic or not content_str:
            return 1.0
        keywords = list(dict.fromkeys(re.findall(r"[\u4e00-\u9fff]{2,}", topic)))
        if not keywords:
            return 1.0
        sample = content_str[:8000]
        hits = sum(1 for kw in keywords if kw in sample)
        return hits / len(keywords)

    @staticmethod
    def _is_fast_mode_off_topic(content_str: str) -> bool:
        if not content_str:
            return True
        trigger_patterns = [
            r"基础内容原文",
            r"请发送.*原文",
            r"还缺.*原文",
            r"根据指定的创意维度",
            r"你这次的任务目标很明确",
            r"请提供.*原文",
            r"改写建议",
            r"创作指导",
        ]
        for pattern in trigger_patterns:
            if re.search(pattern, content_str, flags=re.IGNORECASE):
                return True
        return False

    @staticmethod
    def _is_review_report_content(content_str: str) -> bool:
        from src.ai_write_x.core.final_reviewer import is_editorial_review_report

        return is_editorial_review_report(content_str or "")

    @staticmethod
    def _ensure_publishable_article(content_str: str, fallback: str, stage: str) -> str:
        """若内容为审稿报告体，回退到上一版可用正文。"""
        cleaned = utils.remove_code_blocks(content_str or "").strip()
        if not UnifiedContentWorkflow._is_review_report_content(cleaned):
            return cleaned
        lg.print_log(f"[{stage}] 检测到审稿/评分拆解体，已回退到上一版正文", "warning")
        return fallback

    def _stream_article_rewrite(self, client, messages: list) -> str:
        rewritten = ""
        for chunk in client.stream_chat(messages=messages):
            self._raise_if_cancelled(None, "stream_rewrite")
            if chunk:
                rewritten += chunk
        return utils.remove_code_blocks(rewritten).strip()

    def _stream_article_rewrite_checked(self, client, messages: list, cancel_check: Optional[Callable[[], bool]] = None) -> str:
        rewritten = ""
        for chunk in client.stream_chat(messages=messages):
            self._raise_if_cancelled(cancel_check, "stream_rewrite")
            if chunk:
                rewritten += chunk
        return utils.remove_code_blocks(rewritten).strip()

    def _fast_mode_topic_rewrite(self, topic: str, bad_content: str, cancel_check: Optional[Callable[[], bool]] = None) -> str:
        from src.ai_write_x.core.llm_client import LLMClient
        client = LLMClient()
        rewrite_prompt = (
            prompt_loader.get_rsc("off_topic_rewrite").format(topic=topic)
            + f"\n\n以下是需要纠偏的异常内容，请完全忽略其任务请求口吻，仅提炼可用事实后重写：\n{bad_content[:3000]}"
        )
        rewritten = ""
        for chunk in client.stream_chat(messages=[{"role": "user", "content": rewrite_prompt}]):
            self._raise_if_cancelled(cancel_check, "topic_rewrite")
            if chunk:
                rewritten += chunk
        return utils.remove_code_blocks(rewritten).strip()

    def _quality_gate_passed(self, qa_result) -> bool:
        """Return True when local quality metrics meet the publishable threshold."""
        return (
            qa_result.overall_score >= 75
            and qa_result.originality_score >= 75
            and qa_result.ai_detection_score <= 30
        )

    def _quality_gate_summary(self, qa_result) -> str:
        return (
            f"综合分 {qa_result.overall_score:.1f}，"
            f"原创性 {qa_result.originality_score:.1f}，"
            f"AI检测 {qa_result.ai_detection_score:.1f}"
        )

    def _repair_quality_with_llm(
        self,
        topic: str,
        content: str,
        qa_result,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> str:
        """Rewrite the article body when the local quality gate fails."""
        self._raise_if_cancelled(cancel_check, "QUALITY_REPAIR")
        from src.ai_write_x.core.llm_client import LLMClient

        suggestions = []
        for score in qa_result.quality_scores.values():
            suggestions.extend(getattr(score, "suggestions", []) or [])
        suggestion_text = "\n".join(f"- {item}" for item in suggestions[:8]) or "- 提升表达自然度、信息密度和段落衔接。"

        user_prompt = f"""请根据本地质量检测结果，对下面文章进行一次完整修复。

话题：{topic}
当前检测结果：{self._quality_gate_summary(qa_result)}
合格标准：综合分 >= 75，原创性 >= 75，AI检测概率 <= 30。

修复重点：
{suggestion_text}

硬性要求：
1. 只输出修复后的完整正文，不要输出评分报告、解释、清单或代码块。
2. 不改变文章核心事实、人物、时间、结论和主题立场。
3. 保留 Markdown 正文结构，增强具体信息、过渡自然度和真人表达感。
4. 避免模板化套话、机械排比、总结腔和“首先/其次/综上”等高AI痕迹表达。

待修复文章：
{content}
"""
        messages = [
            {
                "role": "system",
                "content": "你是一位严谨的新媒体主编，只负责把低分文章修复成可发布正文。你绝不输出审稿报告或评分拆解。",
            },
            {"role": "user", "content": user_prompt},
        ]
        repaired = LLMClient().chat(messages=messages, temperature=0.55)
        self._raise_if_cancelled(cancel_check, "QUALITY_REPAIR")
        return utils.remove_code_blocks(repaired or "").strip()

    def execute_stepwise(self, topic: str, **kwargs) -> Generator[Dict[str, Any], None, None]:
        """
        V4: 核心 7 阶 Agent 驱动工作流 (Generator) — 增加超时保护、内容断言、细粒度进度

        通过生成器 yield 返回每个阶段的增量状态，用于前端实时显示与后台异步监控。

        Args:
            topic: 目标生成话题
            **kwargs: 其他生成参数（例如发布平台等）

        Yields:
            Generator[Dict[str, Any], None, None]: 每步执行后的状态字典
        """
        start_time = time.time()
        success = False
        config = Config.get_instance()
        cancel_check = self._cancel_check_from_kwargs(kwargs)
        kwargs = self._kwargs_without_runtime_controls(kwargs)

        # V26: 清理缓存和上下文，防止上一篇文章的评估报告污染新文章
        try:
            from src.ai_write_x.core.semantic_cache_v2 import get_semantic_cache
            cache = get_semantic_cache()
            if hasattr(cache, 'clear'):
                cache.clear()
                lg.print_log("🧹 已清理语义缓存，防止旧数据污染", "info")
        except Exception as cache_err:
            lg.print_log(f"⚠️ 缓存清理失败（非致命）: {cache_err}", "warning")

        # 优先从 kwargs 获取，如果没有则从配置获取
        publish_platform = kwargs.get("publish_platform", config.publish_platform)
        # 统一存入 kwargs 供子流程使用
        kwargs["publish_platform"] = publish_platform

        quality_score = None  # V4: 用于记忆库质量反馈
        fast_mode = bool(kwargs.get("fast_mode") or getattr(config, "fast_mode", False))

        # V11: 注入全局时间上下文，初始化对话链
        from datetime import datetime
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
        conversation_history = [
            {
                "role": "system",
                "content": prompt_loader.get_writer("global_context_injection").format(current_time=current_time)
            }
        ]

        try:
            # --- Step 1: Logic Deep Dive Agent (深度洞察) ---
            stage_start = time.time()
            yield {"type": "progress", "message": "[PROGRESS:INIT:START]"}
            self._raise_if_cancelled(cancel_check, "INIT")
            yield {"type": "log", "message": "🧠 Agent Step 1: 正在进行全维度逻辑解构与内容建模..."}

            # V11: 在生成前，先注入“对抗性共鸣”元数据
            try:
                from src.ai_write_x.core.memory_manager import MemoryManager
                resonance_prompt = MemoryManager().get_resonance_context(topic)
                if resonance_prompt and kwargs.get("reference_content", "").strip():
                    kwargs["reference_content"] = (kwargs.get("reference_content", "") + "\n\n" + resonance_prompt).strip()
            except:
                pass

            # V12.0: 数据库存证 - 话题初始化
            try:
                from src.ai_write_x.database.db_manager import db_manager
                topic_db = db_manager.add_topic(topic, publish_platform, 0)
                kwargs["topic_id"] = topic_db.id
            except Exception as db_err:
                lg.print_log(f"数据库记录失败: {db_err}", "warning")

            base_content = self._generate_base_content(
                topic, **kwargs
            )

            conversation_history.append({"role": "user", "content": f"请针对话题'{topic}'撰写初稿。要求字数在 {config.min_article_len} 到 {config.max_article_len} 之间。"})
            conversation_history.append({"role": "assistant", "content": base_content.content})

            self._check_stage_timeout("INIT", stage_start)
            self._assert_content(base_content.content, "Step1-深度洞察")

            yield {"type": "log", "message": "✅ 初稿生成完成（含内置逻辑自检）"}
            yield {"type": "log", "message": f"✅ 深度洞察阶段完成 ({time.time()-stage_start:.1f}s)"}
            yield {"type": "progress", "message": "[PROGRESS:INIT:END]"}
            self._raise_if_cancelled(cancel_check, "INIT")

            # --- Step 2: Creative Blueprint Agent (创意蓝图) ---
            stage_start = time.time()
            yield {"type": "progress", "message": "[PROGRESS:CREATIVE:START]"}
            self._raise_if_cancelled(cancel_check, "CREATIVE")
            if fast_mode:
                yield {"type": "log", "message": "⚡ 极速模式：跳过维度化创意改写，锁定原话题直出"}
                final_content = base_content
            else:
                yield {"type": "log", "message": "🎨 Agent Step 2: 正在构建维度化创意蓝图与情感锚点..."}
                final_content = self._apply_dimensional_creative_transformation(base_content, **kwargs)
                yield {"type": "log", "message": "✨ 创意框架已落定：已注入差异化认知角度"}
            self._check_stage_timeout("CREATIVE", stage_start)
            yield {"type": "progress", "message": "[PROGRESS:CREATIVE:END]"}
            self._raise_if_cancelled(cancel_check, "CREATIVE")

            # --- Step 3: Master Drafting Agent (大师撰稿) ---
            stage_start = time.time()
            yield {"type": "progress", "message": "[PROGRESS:WRITING:START]"}
            self._raise_if_cancelled(cancel_check, "WRITING")
            yield {"type": "log", "message": "✍️ Agent Step 3: 首席撰稿手正在进行高感知度正文创作..."}
            if fast_mode and self._is_fast_mode_off_topic(final_content.content):
                yield {"type": "log", "message": "🚨 极速模式熔断触发：检测到跑题/元话术，正在自动纠偏重写..."}
                corrected = self._fast_mode_topic_rewrite(topic, final_content.content, cancel_check)
                if corrected and not self._is_fast_mode_off_topic(corrected):
                    final_content.content = corrected
                    yield {"type": "log", "message": "✅ 极速模式纠偏完成：已回归话题主线"}
                else:
                    yield {"type": "log", "message": "⚠️ 极速模式纠偏未完全达标，保留原结果继续流程"}
            yield {"type": "chunk", "message": final_content.content}
            self._assert_content(final_content.content, "Step3-大师撰稿")

            off_topic_meta = self._is_fast_mode_off_topic(final_content.content)
            overlap = self._topic_keyword_overlap(topic, final_content.content)
            if off_topic_meta or overlap < 0.25:
                yield {
                    "type": "log",
                    "message": f"🚨 检测到内容与话题「{topic[:24]}」偏离（命中率 {overlap:.0%}），正在纠偏重写...",
                }
                corrected = self._fast_mode_topic_rewrite(topic, final_content.content, cancel_check)
                if corrected and self._topic_keyword_overlap(topic, corrected) >= max(overlap, 0.35):
                    if not self._is_fast_mode_off_topic(corrected):
                        final_content.content = corrected
                        yield {"type": "log", "message": "✅ 话题纠偏完成，已回归主线"}
                else:
                    yield {"type": "log", "message": "⚠️ 话题纠偏未完全成功，请检查参考素材是否与话题一致"}

            yield {"type": "log", "message": f"📝 初稿已生成 (约 {len(final_content.content)} 字, V4断言通过)"}
            publishable_draft = final_content.content

            # --- Step 3.5: RSC Recursive Self-Correction (递归自我修正) ---
            if fast_mode:
                yield {"type": "log", "message": "⚡ 极速模式：跳过RSC递归自检，保留初稿直达打磨阶段"}
            else:
                yield {"type": "log", "message": "🧬 Agent Step 3.5: 正在启动RSC递归自我修正协议..."}
                try:
                    rsc_content = self._apply_recursive_self_correction(
                        final_content.content, topic, conversation_history, **kwargs
                    )
                    if rsc_content and len(rsc_content.strip()) > 200:
                        rsc_content = self._ensure_publishable_article(rsc_content, publishable_draft, "RSC")
                        final_content.content = rsc_content
                        publishable_draft = rsc_content
                        yield {"type": "log", "message": "✅ RSC递归自检完成，文章逻辑已强化"}
                    else:
                        yield {"type": "log", "message": "⚠️ RSC自检结果异常，保留原稿继续"}
                except Exception as rsc_err:
                    lg.print_log(f"RSC自检异常，跳过: {rsc_err}", "warning")
                    yield {"type": "log", "message": "⚠️ RSC自检异常，已跳过继续流程"}
            yield {"type": "progress", "message": "[PROGRESS:WRITING:END]"}
            self._raise_if_cancelled(cancel_check, "WRITING")


            # --- Step 3.8: Fact Check Agent (独立事实核查) ---
            _has_reference = bool(kwargs.get("reference_content", "").strip())
            if fast_mode or not _has_reference:
                if not _has_reference and not fast_mode:
                    yield {"type": "log", "message": "📋 无参考素材，跳过独立事实核查"}
                else:
                    yield {"type": "log", "message": "⚡ 极速模式：跳过独立事实核查"}
            else:
                stage_start_fact = time.time()
                yield {"type": "log", "message": "🔍 Agent Step 3.8: 正在启动独立事实核查员逐句审查..."}
                try:
                    from src.ai_write_x.core.fact_checker import FactChecker
                    source_publish_time = kwargs.get("source_publish_time", "未知")
                    fact_result = FactChecker.check(
                        content=final_content.content,
                        topic=topic,
                        source_publish_time=source_publish_time,
                        current_date_str=current_time,
                    )
                    if fact_result.passed:
                        yield {"type": "log", "message": f"✅ 事实核查通过: {fact_result.summary}"}
                    else:
                        issue_count = len(fact_result.issues)
                        high_count = fact_result.high_severity_count
                        yield {"type": "log", "message": f"⚠️ 事实核查发现 {issue_count} 个问题（严重 {high_count} 个）: {fact_result.summary}"}
                        if high_count > 0:
                            yield {"type": "log", "message": "🔧 正在根据核查报告修正事实错误..."}
                            fixed_content = FactChecker.fix(
                                content=final_content.content,
                                fact_check_result=fact_result,
                                topic=topic,
                            )
                            if fixed_content != final_content.content:
                                final_content.content = fixed_content
                                publishable_draft = final_content.content
                                yield {"type": "log", "message": "✅ 事实修正完成，已修正严重事实错误"}
                            else:
                                yield {"type": "log", "message": "⚠️ 事实修正未产生变化，保留原文"}
                        for issue in fact_result.issues:
                            if issue.severity == "high":
                                lg.print_log(f"[FactCheck] 严重问题: {issue.description} | 建议: {issue.suggestion}", "warning")
                    yield {"type": "log", "message": f"📋 事实核查完成 ({time.time()-stage_start_fact:.1f}s)"}
                except Exception as fc_err:
                    lg.print_log(f"事实核查异常，跳过: {fc_err}", "warning")
                    yield {"type": "log", "message": "⚠️ 事实核查异常，已跳过继续流程"}

                        # --- Step 4: Reflexion & Polish Agent (打磨重塑) ---
            stage_start = time.time()
            yield {"type": "progress", "message": "[PROGRESS:REVIEW:START]"}
            self._raise_if_cancelled(cancel_check, "REVIEW")
            yield {"type": "log", "message": "💎 Agent Step 4: 正在进行语境打磨、去 AI 化处理及深度优化..."}
            
            from src.ai_write_x.core.final_reviewer import (
                FinalReviewer,
                ARTICLE_ONLY_REWRITE_SUFFIX,
            )
            from src.ai_write_x.core.llm_client import LLMClient
            from src.ai_write_x.core.anti_ai import AntiAIEngine
            
            # V11: 基于系统熵动态调节打磨强度
            current_entropy = self.monitor.calculate_system_entropy()
            if fast_mode:
                max_reflections = 0
                yield {"type": "log", "message": "⚡ 极速模式：跳过 Reflexion 多轮打磨，直接进入抗AI与质量评估"}
            else:
                max_reflections = 2
            
            result_str = final_content.content
            publishable_draft = result_str
            iteration = 0

            while iteration < max_reflections:
                self._check_stage_timeout("REVIEW", stage_start)  # V4: 超时检查
                yield {"type": "log", "message": f"🔍 Reflexion Round {iteration+1}/{max_reflections}: 评估中..."}
                review_result = FinalReviewer.assess_quality(result_str, {"topic": topic})
                if review_result.get("pass", True):
                    yield {"type": "log", "message": f"✅ Reflexion Round {iteration+1}: 质量达标，跳过优化"}
                    break

                lg.print_log(f"[Reflexion] 正在启动第 {iteration+1} 轮深度打磨优化...")

                # V6: 将被打回的关键原因记录到潜意识经验库 (RAG)
                try:
                    from src.ai_write_x.core.memory_manager import MemoryManager
                    report_text = review_result.get("report", "")
                    if report_text and len(report_text) > 10:
                        lesson = f"曾经在写标题为'{title if 'title' in locals() else topic}'时犯错: {report_text[:200]}..."
                        MemoryManager().save_rag_lesson(lesson)
                        yield {"type": "log", "message": "🧠 已将本次失败教训写入 RAG 潜意识库"}
                except Exception:
                    pass

                client = LLMClient()
                editor_feedback = review_result.get("report", "")
                issue_categories = review_result.get("issue_categories", [])
                
                if issue_categories:
                    primary_fix = issue_categories[0]
                    yield {"type": "log", "message": f"🎯 定向修复策略: {primary_fix} (检测到问题类型: {', '.join(issue_categories)})"}
                    fix_system = prompt_loader.get_reviewer("directed_fix", primary_fix, "system_prompt")
                    fix_user = prompt_loader.get_reviewer("directed_fix", primary_fix, "user_prompt").format(
                        editor_feedback=editor_feedback,
                        topic=topic,
                        result_str=result_str,
                        article_only_rewrite_suffix=ARTICLE_ONLY_REWRITE_SUFFIX,
                    )
                else:
                    fix_system = prompt_loader.get_reviewer("reflexion_rewrite", "system_prompt")
                    fix_user = prompt_loader.get_reviewer("reflexion_rewrite", "user_prompt").format(
                        editor_feedback=editor_feedback,
                        topic=topic,
                        result_str=result_str,
                        article_only_rewrite_suffix=ARTICLE_ONLY_REWRITE_SUFFIX,
                    )

                rewrite_messages = [
                    {"role": "system", "content": fix_system},
                    {"role": "user", "content": fix_user},
                ]

                new_version = self._stream_article_rewrite_checked(client, rewrite_messages, cancel_check)
                new_version = self._ensure_publishable_article(
                    new_version, publishable_draft, f"Reflexion-R{iteration + 1}"
                )
                if new_version != publishable_draft:
                    result_str = new_version
                    publishable_draft = result_str

                iteration += 1
                yield {"type": "log", "message": f"📝 Reflexion Round {iteration}: 优化完成"}

            result_str = self._ensure_publishable_article(
                result_str, publishable_draft, "Step4-终审收尾"
            )

            # 统一执行一次抗AI粉碎与 Markdown 清洗（根据AI检测概率动态选择强度）
            anti_ai_mode = "deep"
            if quality_score is not None and quality_score >= 4.0:
                anti_ai_mode = "light"
            result_str = AntiAIEngine.pulverize(result_str, mode=anti_ai_mode)
            yield {"type": "log", "message": f"🛡️ 反AI化处理完成 (模式: {anti_ai_mode})"}
            
            # V15: 移除过度清洗逻辑，保留 Markdown 小标题 (##, ###)
            # 仅清理可能误输出的单个 # 或残留符号，或者完全信任后续流程
            # result_str = re.sub(r'^#+\s*', '', result_str, flags=re.MULTILINE)
            # result_str = re.sub(r'(?<=\n)#+\s*', '', result_str)
            
            result_str = self._ensure_publishable_article(
                result_str, publishable_draft, "Step4-抗AI前"
            )
            final_content.content = result_str

            # V4: 进行质量评估以获得分数
            try:
                from src.ai_write_x.core.quality_engine import ContentQualityEngine
                qe = ContentQualityEngine()
                qa_result = qe.analyze_content(result_str)
                quality_score = qa_result.overall_score / 20.0  # 转为 0-5 分
                yield {"type": "log", "message": f"📊 V4质量评估: 综合分 {qa_result.overall_score}, AI检测 {qa_result.ai_detection_score}"}
            except Exception as qe_err:
                lg.print_log(f"V4质量评估跳过: {qe_err}", "warning")
            
            yield {"type": "log", "message": f"🖋️ 完成人类感重塑 ({time.time()-stage_start:.1f}s)：强化阅读呼吸感与抗 AI 特征注入"}
            yield {"type": "progress", "message": "[PROGRESS:REVIEW:END]"}
            self._raise_if_cancelled(cancel_check, "REVIEW")

            # --- Step 5: Visual & Template Agent (视觉与排版美化) ---
            stage_start = time.time()
            yield {"type": "progress", "message": "[PROGRESS:VISUAL:START]"}
            self._raise_if_cancelled(cancel_check, "VISUAL")
            yield {"type": "log", "message": "📸 Agent Step 5: 正在进行视觉美化、注入图像占位符及 HTML 适配..."}

            # V20.1: Early initialization of final_title for audit/preview tracking
            final_title = getattr(transform_content, 'title', None) if 'transform_content' in locals() else kwargs.get("title", topic)

            from src.ai_write_x.core.visual_assets import VisualAssetsManager
            if fast_mode:
                yield {"type": "log", "message": "⚡ 极速模式：预置轻量配图提示词（HTML 定稿后统一生图）"}
                final_content.content = VisualAssetsManager.inject_image_prompts_fast(final_content.content)
            else:
                final_content.content = VisualAssetsManager.inject_image_prompts(final_content.content)
                yield {"type": "log", "message": "🖼️ 图像分镜已分析，将在 HTML 排版完成后生成配图..."}

            # 创建副本以防污染 kwargs
            transform_kwargs = kwargs.copy()
            # 移除已显式传递的 publish_platform 以防 TypeError
            if "publish_platform" in transform_kwargs:
                del transform_kwargs["publish_platform"]

            yield {"type": "log", "message": "🎨 正在启动 Visual Packaging Expert 进行 HTML 封装..."}
            transform_content = self._transform_content(final_content, publish_platform, topic=topic, **transform_kwargs)

            # V25: 在 HTML 定稿后生图，避免排版阶段冲掉 Markdown 里已生成的图片
            pack_title = getattr(transform_content, "title", None) or kwargs.get("title", topic)
            yield {"type": "log", "message": "🖼️ HTML 已定稿，正在生成并嵌入配图..."}
            transform_content.content = VisualAssetsManager.finalize_html_images(
                transform_content.content,
                topic=topic,
                title=pack_title,
                fast_mode=fast_mode,
                article_path=kwargs.get("article_path") or "",
            )

            # --- Step 5 验证 (V19.5 强制 HTML 校验) ---
            trimmed_content = transform_content.content.strip()
            if not trimmed_content.startswith('<'):
                lg.print_log("⚠️ 警告：HTML 转换可能未完全执行，内容仍以 Markdown 格式开头", "warning")
                lg.print_log(f"内容预览 (前 200 字): {trimmed_content[:200]}", "warning")
            elif "[[V-SCENE:" in trimmed_content:
                lg.print_log("⚠️ 警告：发现残留的 V-SCENE 标签，后处理可能未完全清理", "warning")

            # V4: VISUAL 阶段用软警告而非硬超时 — 图片已生成完毕时不应丢弃成果
            visual_elapsed = time.time() - stage_start
            visual_max = self.STAGE_TIMEOUT.get("VISUAL", 900)
            if visual_elapsed > visual_max:
                yield {"type": "log", "message": f"⚠️ VISUAL 阶段耗时 {visual_elapsed:.0f}s 超出预期 ({visual_max}s)，但图片已生成成功，继续保存"}

            yield {"type": "chunk", "message": transform_content.content}
            yield {"type": "log", "message": f"🖼️ 视觉资产已同步 ({time.time()-stage_start:.1f}s)：封面图与正文配图已就绪"}

            # --- Step 5.2: WeChat Preview (微信预览 - V19.5) ---
            if publish_platform == PlatformType.WECHAT.value and not fast_mode:
                # 4. (V20.1) 微信预览自测自纠与 1:1 仿真库截图 (V-AUDIT)
                yield {"type": "progress", "message": "[PROGRESS:V-AUDIT:START]"}
                try:
                    lg.print_log("📱 Agent Step 5.2: 正在生成微信 1:1 仿真预览与自测报告...", "info")
                    from src.ai_write_x.core.wechat_preview import WeChatPreviewEngine
                    preview_engine = WeChatPreviewEngine()
                    preview_path = preview_engine.save_preview(transform_content.content, final_title)

                    # 视觉自审
                    audit_res = preview_engine.audit_visuals(transform_content.content)
                    if not audit_res["passed"]:
                        lg.print_log(f"👀 视觉自审建议: {', '.join(audit_res['issues'])}", "warning")

                    # 截取手机端仿真图
                    lg.print_log("📸 正在捕获 3 张手机端 1:1 视觉仿真截图...", "status")
                    try:
                        # V20.2: 使用独立函数避免 lambda 作用域问题，在线程中安全调用 async 方法
                        import concurrent.futures

                        def _capture_screenshots():
                            import asyncio
                            return asyncio.run(preview_engine.capture_screenshots(preview_path, final_title))

                        with concurrent.futures.ThreadPoolExecutor() as pool:
                            screenshots = pool.submit(_capture_screenshots).result()

                        if screenshots:
                            lg.print_log(f"✅ 已完成视觉采集: {len(screenshots)} 张样图已归档至 output/previews/", "success")
                    except Exception as screenshot_e:
                        lg.print_log(f"⚠️ 截图捕获失败 (可能是环境限制): {str(screenshot_e)}", "warning")

                    report = preview_engine.generate_compatibility_report(transform_content.content)
                    lg.print_log(f"📊 兼容性报告: {report}", "info")
                except Exception as e:
                    yield {"type": "log", "message": f"⚠️ 预览与审计步骤失败: {str(e)}"}

                yield {"type": "progress", "message": "[PROGRESS:V-AUDIT:END]"}
            elif publish_platform == PlatformType.WECHAT.value and fast_mode:
                yield {"type": "log", "message": "⚡ 极速模式：跳过微信预览审计与截图采集"}

            yield {"type": "progress", "message": "[PROGRESS:VISUAL:END]"}
            self._raise_if_cancelled(cancel_check, "VISUAL")

            # --- Step 5.5: AI Auto Title Optimization (AI自动标题优化) ---
            stage_start = time.time()
            yield {"type": "progress", "message": "[PROGRESS:TITLE_OPT:START]"}
            self._raise_if_cancelled(cancel_check, "TITLE_OPT")
            yield {"type": "log", "message": "🎯 Agent Step 5.5: 正在启动AI智能标题优化引擎..."}

            # Note: final_title is now initialized earlier in Step 5 Visual.

            if fast_mode:
                yield {"type": "log", "message": "⚡ 极速模式：跳过AI标题优化，保留当前标题"}
            else:
                try:
                    import asyncio
                    from src.ai_write_x.core.quality_engine import TitleOptimizer
                    title = kwargs.get("title", topic)
                    current_title = transform_content.title if getattr(transform_content, 'title', None) else title

                    from src.ai_write_x.core.article_polish import extract_plain_text
                    content_preview = extract_plain_text(transform_content.content, max_len=1500)

                    # 安全调用标题优化器，处理事件循环冲突
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None

                    if loop and loop.is_running():
                        # 如果当前已有运行中的 loop，则在线程中运行
                        import concurrent.futures

                        def _optimize_title():
                            import asyncio
                            return asyncio.run(TitleOptimizer.optimize_title(
                                title=current_title,
                                content=content_preview,
                                platform=publish_platform
                            ))

                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            opt_result = executor.submit(_optimize_title).result()
                    else:
                        opt_result = asyncio.run(TitleOptimizer.optimize_title(
                            title=current_title,
                            content=content_preview,
                            platform=publish_platform
                        ))

                    if opt_result.get("optimized_titles") and len(opt_result["optimized_titles"]) > 0:
                        new_title = opt_result.get("recommended", current_title)
                        collection_mode = kwargs.get("collection_mode", False)
                        if collection_mode:
                            series_name = topic.split("：", 1)[0] if "：" in topic else topic
                            if not new_title.startswith(series_name + "：") and not new_title.startswith(series_name + ":"):
                                new_title = f"{series_name}：{new_title}"
                        transform_content.title = new_title
                        final_title = new_title
                        yield {"type": "log", "message": f"✨ AI标题优化完成: '{current_title[:30]}...' → '{new_title[:30]}...'"}
                        yield {"type": "log", "message": f"📊 共生成 {len(opt_result['optimized_titles'])} 个候选标题，已自动选择最优方案"}
                    else:
                        yield {"type": "log", "message": "⚠️ AI标题优化未返回有效结果，保留原标题"}

                except Exception as e:
                    yield {"type": "log", "message": f"⚠️ AI标题优化步骤出错: {str(e)}，跳过并保留原标题"}

            yield {"type": "progress", "message": "[PROGRESS:TITLE_OPT:END]"}
            self._raise_if_cancelled(cancel_check, "TITLE_OPT")

            # V4: 对最终成品进行质量评估；不合格时自动修复一次并复评。
            yield {"type": "progress", "message": "[PROGRESS:QUALITY:START]"}
            self._raise_if_cancelled(cancel_check, "QUALITY")
            try:
                from src.ai_write_x.core.quality_engine import ContentQualityEngine
                qe = ContentQualityEngine()
                qa_result = qe.analyze_content(transform_content.content)
                quality_score = qa_result.overall_score / 20.0  # 转为 0-5 分
                yield {"type": "log", "message": f"最终AI评分: {self._quality_gate_summary(qa_result)}"}

                if not self._quality_gate_passed(qa_result):
                    yield {"type": "progress", "message": f"[PROGRESS:QUALITY:DETAIL] 最终成品未达标，正在自动修复 | {self._quality_gate_summary(qa_result)}"}
                    repaired_content = self._repair_quality_with_llm(topic, transform_content.content, qa_result, cancel_check)
                    repaired_content = self._ensure_publishable_article(
                        repaired_content, transform_content.content, "QUALITY_REPAIR"
                    )
                    if repaired_content and repaired_content != transform_content.content:
                        transform_content.content = repaired_content
                        qa_result = qe.analyze_content(transform_content.content)
                        quality_score = qa_result.overall_score / 20.0
                        if self._quality_gate_passed(qa_result):
                            yield {"type": "log", "message": f"最终AI评分修复通过: {self._quality_gate_summary(qa_result)}"}
                            yield {"type": "progress", "message": f"[PROGRESS:QUALITY:DETAIL] 修复通过 | {self._quality_gate_summary(qa_result)}"}
                        else:
                            yield {"type": "log", "message": f"最终AI评分修复后仍未完全达标: {self._quality_gate_summary(qa_result)}，继续保存成品"}
                            yield {"type": "progress", "message": f"[PROGRESS:QUALITY:DETAIL] 修复后仍需人工确认 | {self._quality_gate_summary(qa_result)}"}
                    else:
                        yield {"type": "log", "message": "最终AI评分修复未产生有效改动，保留当前成品继续"}
                else:
                    yield {"type": "progress", "message": f"[PROGRESS:QUALITY:DETAIL] 最终成品已达标 | {self._quality_gate_summary(qa_result)}"}
            except Exception as qe_err:
                lg.print_log(f"V4最终质量评估跳过: {qe_err}", "warning")
            yield {"type": "progress", "message": "[PROGRESS:QUALITY:END]"}
            self._raise_if_cancelled(cancel_check, "QUALITY")

            # --- Step 6: Persistence & Orchestration Agent (持久化管理) ---
            stage_start = time.time()
            yield {"type": "progress", "message": "[PROGRESS:SAVE:START]"}
            self._raise_if_cancelled(cancel_check, "SAVE")
            yield {"type": "log", "message": "💾 Agent Step 6: 正在将灵感编码并安全存储至本地知识库..."}
            title = kwargs.get("title", topic)
            final_title = transform_content.title if getattr(transform_content, 'title', None) else title
            save_result = self._save_content(transform_content, final_title, reference_content=kwargs.get("reference_content", ""))

            if save_result.get("success", False):
                article_path = save_result.get("path")
                kwargs["article_path"] = article_path
                try:
                    from src.ai_write_x.core.visual_assets import VisualAssetsManager
                    VisualAssetsManager.persist_cover_metadata(article_path, transform_content.content)
                except Exception as cover_err:
                    lg.print_log(f"封面元数据写入失败: {cover_err}", "warning")
                yield {"type": "log", "message": f"📁 存储成功：文章已归档至 `{os.path.basename(article_path)}`"}
            yield {"type": "progress", "message": "[PROGRESS:SAVE:END]"}
            self._raise_if_cancelled(cancel_check, "SAVE")

            # V4: 成功后将话题写入全景记忆库（含质量反馈分数及全文内容分析）
            try:
                from src.ai_write_x.core.memory_manager import MemoryManager
                MemoryManager().add_topic(topic, content=result_str, quality_score=quality_score)
                yield {"type": "log", "message": f"🧠 全景记忆库已更新当前话题特征 (质量反馈: {quality_score:.1f}/5.0)" if quality_score else "🧠 全景记忆库已更新当前话题特征"}
            except Exception as e:
                self.monitor.log_error("unified_workflow", f"写入记忆库失败: {e}", {"topic": topic})

            # --- Step 7: UI Handover & Completion (交付刷新) ---
            yield {"type": "progress", "message": "[PROGRESS:COMPLETE:START]"}
            self._raise_if_cancelled(cancel_check, "COMPLETE")
            yield {"type": "log", "message": "🎉 Agent Step 7: 全流程审计完成。UI 资产同步中，准备交付..."}

            publish_result = None
            if self._should_publish():
                yield {"type": "log", "message": "📤 正在自动同步并发布至平台..."}
                transform_content.title = final_title

                # _publish_content 已经接收 publish_platform 作为参数，kwargs 中不应包含它
                publish_kwargs = kwargs.copy()
                if "publish_platform" in publish_kwargs:
                    del publish_kwargs["publish_platform"]

                publish_result = self._publish_content(
                    transform_content, publish_platform, **publish_kwargs
                )
                yield {"type": "log", "message": f"🚀 发布任务已下发：{publish_result.get('message')}"}

            total_duration = time.time() - start_time
            success = True
            results = {
                "base_content": base_content,
                "final_content": final_content,
                "formatted_content": transform_content.content,
                "save_result": save_result,
                "publish_result": publish_result,
                "quality_score": quality_score,
                "total_duration": round(total_duration, 1),
                "success": True,
            }
            yield {"type": "log", "message": f"⏱️ V4工作流总耗时: {total_duration:.1f}秒"}
            yield {"type": "final_results", "content": results}
            yield {"type": "done"}

        except WorkflowCancelled as cancelled:
            total_duration = time.time() - start_time
            results = {
                "success": False,
                "cancelled": True,
                "error": str(cancelled),
                "total_duration": round(total_duration, 1),
            }
            yield {"type": "log", "message": f"Workflow cancelled: {cancelled}"}
            yield {"type": "final_results", "content": results}
            yield {"type": "done"}

        except TimeoutError as te:
            self.monitor.log_error("unified_workflow", f"V4阶段超时: {te}", {"topic": topic})
            yield {"type": "log", "message": f"⏰ V4超时保护触发: {str(te)}"}
            raise
        except Exception as e:
            self.monitor.log_error("unified_workflow", str(e), {"topic": topic})
            yield {"type": "log", "message": f"❌ Agent 遭遇异常中断: {str(e)}"}
            raise
        finally:
            duration = time.time() - start_time
            self.monitor.track_execution("unified_workflow", duration, success, {"topic": topic})

    def _apply_final_html_packaging(self, content: ContentResult, publish_platform: str, **kwargs) -> ContentResult:
        """V23.0: 执行最终的 HTML 包装（新会话，零上下文）"""
        lg.print_log("[PROGRESS:HTML_PACKAGING:START]", "internal")

        # 预先导入需要的模块
        import re

        # 这种模式下，我们故意只传递最少的信息，避免干扰
        packaging_config = self._get_html_packaging_config(publish_platform, **kwargs)
        engine = ContentGenerationEngine(packaging_config)

        # 确保输入是字符串
        input_content = content.content if hasattr(content, 'content') else str(content)

        # V26/V27/V28: 过滤掉可能混入的评估报告/审核报告内容
        # 覆盖所有Agent输出：终审评估、事实核查、RSC逻辑审核、对齐检查、质量检测
        review_indicators = [
            # 终审评估 (final_reviewer.py)
            '维度点评', '爆款指数评分', '最终判定', '优化指令',
            '内部审稿报告', '终审评估', '五个维度点评', '精准可执行优化',
            '[PASS:', '[SCORE:', '判定代码',
            'AI痕迹专项补充', '原始标题警示',
            '深度文章评分与拆解', '评分与拆解',
            # 事实核查 (fact_checker.py)
            '逻辑审核报告', '经逐段审查', '逻辑跳跃',
            '事实核查报告', 'fact_check_passed',
            # RSC逻辑审核 (rsc.yaml)
            '逻辑审核官', '核心重构员',
            '观点堆砌', '论据空洞', '注水段落',
            # 对齐检查 (alignment_checker)
            '[ALIGNMENT:', '事实核对审查报告', '事实偏移', '对照审查',
            # 质量检测 (quality_engine.py)
            '质量分析报告', 'AI检测概率', '原创性评分', '综合评分',
            # Reflexion打磨
            '主编内部反馈', 'Reflexion Round',
            # 其他可能的元评论
            '【内部审稿】', '【审核意见】', '【修改建议】',
            '致命错误', '第一个致命错误', '第二个致命错误',
        ]
        has_review_content = any(indicator in input_content for indicator in review_indicators)

        if input_content and len(input_content) > 100 and has_review_content:
            lg.print_log("⚠️ 检测到审核/评估报告内容混入正文，已自动过滤", "warning")
            patterns_to_remove = [
                # HTML section块 - 审核报告卡片
                r'<!--\s*(?:维度点评|逻辑审核|审核报告|质量分析)卡片\s*-->.*?(?=<section|</section>\s*</article>|$)',
                r'<section[^>]*>.*?维度点评.*?</section>',
                r'<section[^>]*>.*?爆款指数评分.*?</section>',
                r'<section[^>]*>.*?最终判定.*?</section>',
                r'<section[^>]*>.*?优化指令.*?</section>',
                r'<section[^>]*>.*?逻辑审核报告.*?</section>',
                r'<section[^>]*>.*?核心问题.*?</section>',
                r'<section[^>]*>.*?五个维度点评.*?</section>',
                r'<section[^>]*>.*?精准可执行优化.*?</section>',
                r'<section[^>]*>.*?AI痕迹专项补充.*?</section>',
                r'<section[^>]*>.*?原始标题警示.*?</section>',
                r'<section[^>]*>.*?逻辑审核官.*?</section>',
                r'<section[^>]*>.*?核心重构员.*?</section>',
                r'<section[^>]*>.*?质量分析.*?</section>',
                r'<section[^>]*>.*?事实核查.*?</section>',
                r'<section[^>]*>.*?事实核对.*?</section>',
                # 纯文本报告块（带标题标记）
                r'\[AI 首席主编终审评估报告\].*?=+\s*$',
                r'【内部审稿报告】.*?=+',
                r'【逻辑审核报告】.*?=+',
                r'【事实核查报告】.*?=+',
                r'【事实核对审查报告】.*?=+',
                r'【质量分析报告】.*?=+',
                # RSC逻辑审核特征文本
                r'经逐段审查.*?需(补充|重构|修复)',
                r'结论：存在\d+处(逻辑跳跃|问题)',
                r'你是V\d+系统的【逻辑审核官】.*?直接输出优化后的完整正文',
                r'你是V\d+系统的【核心重构员】.*?直接输出优化后的完整正文',
                # 对齐检查特征
                r'\[ALIGNMENT:\s*(?:pass|fail)\]',
                r'比对.*?打磨后文章.*?是否忠于.*?原始(版本|文章)',
                # 元评论和反馈标记
                r'【主编内部反馈\s*—\s*勿写入正文】',
                r'Reflexion Round\s*\d+/\d+.*?评估中',
                # 致命错误列表（可能混入正文）
                r'(?:第[一二三四五六七八九十]\s*)?致命错误[：:].*?\n',
            ]
            for pattern in patterns_to_remove:
                input_content = re.sub(pattern, '', input_content, flags=re.DOTALL | re.IGNORECASE)
            input_content = re.sub(r'\n{3,}', '\n\n', input_content)
            lg.print_log(f"✅ 已过滤审核报告，剩余内容长度: {len(input_content)} 字符", "info")

        input_data = {
            "content": input_content, # Markdown 内容
            "title": kwargs.get("title", getattr(content, 'title', '')),
            "parse_result": False,
            "content_format": "html",
        }

        try:
            ret_val = engine.execute_workflow(input_data)
            lg.print_log("✅ 最终 HTML 包装完成", "success")
            lg.print_log("[PROGRESS:HTML_PACKAGING:END]", "internal")

            # 手动处理代码块提取 (如果是字符串返回)
            processed_html = ""
            if isinstance(ret_val, str):
                processed_html = ret_val
            elif hasattr(ret_val, 'content'):
                processed_html = ret_val.content

            # 提取 ```html ... ``` 块
            code_block_match = re.search(r'```html\s*(.*?)\s*```', processed_html, re.DOTALL)
            if code_block_match:
                processed_html = code_block_match.group(1).strip()

            from src.ai_write_x.core.article_polish import polish_html_output, strip_leaked_prompt_text
            processed_html = polish_html_output(processed_html)
            processed_html = strip_leaked_prompt_text(processed_html)

            if isinstance(ret_val, str):
                return ContentResult(
                    title=kwargs.get("title", getattr(content, 'title', '')),
                    content=processed_html,
                    content_format="html",
                    metadata={**content.metadata, "packaged": True}
                )
            ret_val.content = processed_html
            return ret_val
        except Exception as e:
            lg.print_log(f"⚠️ 最终 HTML 包装失败: {e}，回退到原始内容", "warning")
            lg.print_log("[PROGRESS:HTML_PACKAGING:END]", "internal")
            return content

    def _transform_content(
        self, content: ContentResult, publish_platform: str, **kwargs
    ) -> ContentResult:
        """转换内容格式，V23.0: 采用解耦的包装逻辑"""

        # 记录转换模式
        transform_mode = kwargs.get("transform_mode", "design")
        lg.print_log(f"🎨 工具链 Step 5.1: 正在使用 {transform_mode} 模式进行核心 HTML 包装...", "info")

        # V23.0: 所有路径最终都通过 _apply_final_html_packaging 保证零上下文质量
        # 但我们保留不同路径作为预处理或策略选择

        if transform_mode == "design":
            # 这种模式下直接使用我们的新视觉包装引擎
            return self._apply_final_html_packaging(content, publish_platform, **kwargs)
        elif transform_mode == "template":
            # 模板路径：先读取模板，再填充（由于填充也需要 AI 包装效果更好，所以嵌套调用）
            return self._apply_template_formatting(content, **kwargs)
        elif transform_mode == "minimalist":
            # 极简模式：直接转基础 HTML
            from src.ai_write_x.utils.utils import markdown_to_html
            html_content = markdown_to_html(content.content)
            return ContentResult(
                title=content.title,
                content=html_content,
                content_format="html",
                metadata={**content.metadata, "minimalist": True}
            )
        else:
            # 默认使用包装引擎
            return self._apply_final_html_packaging(content, publish_platform, **kwargs)

    def _apply_template_formatting(self, content: ContentResult, **kwargs) -> ContentResult:
        """Template路径：使用AI填充本地模板"""
        # 创建专门的模板处理工作流
        lg.print_log("[PROGRESS:TEMPLATE:START]", "internal")

        template_config = self._get_template_workflow_config(**kwargs)
        engine = ContentGenerationEngine(template_config)

        input_data = {
            "content": content.content,
            "title": content.title,
            "parse_result": False,
            "content_format": "html",
            **kwargs,
        }

        try:
            ret = engine.execute_workflow(input_data)
            lg.print_log("[PROGRESS:TEMPLATE:END]", "internal")
            return ret
        except Exception as e:
            # 模板填充失败时，返回原始内容作为降级策略
            lg.print_log(f"模板填充失败，使用原始内容: {str(e)}", "warning")
            lg.print_log("[PROGRESS:TEMPLATE:END]", "internal")
            # 返回原始内容，但标记为 HTML 格式
            return ContentResult(
                title=content.title,
                content=content.content,
                summary=content.summary,
                content_type=content.content_type,
                content_format="html",
                metadata={
                    **content.metadata,
                    "template_fallback": True,
                    "template_error": str(e),
                }
            )

    def _apply_dynamic_template(self, content: ContentResult, **kwargs) -> ContentResult:
        """动态模板路径：使用AI生成独特的HTML模板"""
        from src.ai_write_x.tools.dynamic_template_tool import DynamicTemplateTool

        lg.print_log("[PROGRESS:DYNAMIC_TEMPLATE:START]", "internal")

        try:
            # 提取主题信息
            topic = kwargs.get('topic', '')

            # 获取发布平台信息，判断是否开启极简模式
            publish_platform = kwargs.get('publish_platform', '')
            is_mobile = any(p in str(publish_platform).lower() for p in ['wechat', 'mobile', 'xiaohongshu'])
            format_mode = "simple" if is_mobile else "standard"

            # 使用动态模板工具生成模板（默认使用AI设计师）
            tool = DynamicTemplateTool()
            template_html = tool._run(
                title=content.title,
                content=content.content,
                topic=topic,
                use_ai_designer=True,  # 使用AI生成独特模板
                format_mode=format_mode
            )

            lg.print_log("[PROGRESS:DYNAMIC_TEMPLATE:END]", "internal")

            return ContentResult(
                title=content.title,
                content=template_html,
                summary=content.summary,
                content_type=ContentType.ARTICLE,
                content_format="html",
                metadata={
                    **content.metadata,
                    "template_type": "dynamic_ai",
                    "template_generated": True,
                }
            )

        except Exception as e:
            lg.print_log(f"AI动态模板生成失败，回退到预定义模板: {str(e)}", "warning")
            lg.print_log("[PROGRESS:DYNAMIC_TEMPLATE:END]", "internal")
            # 回退到预定义模板
            return self._apply_template_formatting(content, **kwargs)

    def _apply_design_formatting(
        self, content: ContentResult, publish_platform: str, **kwargs
    ) -> ContentResult:
        """Design路径：使用AI生成HTML设计"""
        # 创建专门的设计工作流
        lg.print_log("[PROGRESS:DESIGN:START]", "internal")

        design_config = self._get_design_workflow_config(publish_platform, **kwargs)
        engine = ContentGenerationEngine(design_config)

        input_data = {
            "content": content.content,
            "title": content.title,
            "platform": publish_platform,
            "parse_result": False,
            "content_format": "html",
            **kwargs,
        }

        ret_val = engine.execute_workflow(input_data)

        # V19.5: 后处理清理（确保执行且包含代码块提取）
        processed_html = ""
        if isinstance(ret_val, str):
            processed_html = ret_val
        elif hasattr(ret_val, 'content') and ret_val.content:
            processed_html = ret_val.content
        else:
            lg.print_log("⚠️ Design 路径返回内容为空，尝试从原始内容恢复", "warning")
            processed_html = content.content

        if processed_html:
            # 1. 提取代码块中的 HTML (AI 经常会将 HTML 放在 ```html 中)
            code_block_match = re.search(r'```html\s*(.*?)\s*```', processed_html, re.DOTALL)
            if code_block_match:
                processed_html = code_block_match.group(1).strip()
                lg.print_log("✅ 已成功从代码块中提取 HTML 内容", "success")

            # 2. 保留所有 V-SCENE 标签 (根据用户要求保存)
            # processed_html = re.sub(r'\[\[V-SCENE:.*?\]\]', '', processed_html, flags=re.DOTALL)

            # 3. 将残留的 ** 符号转为 <strong> (容错处理)
            processed_html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', processed_html)

            # 4. 移除残留的 Markdown 标题符号
            processed_html = re.sub(r'^#+\s+', '', processed_html, flags=re.MULTILINE)

            # 更新返回值
            if isinstance(ret_val, str):
                ret_val = processed_html
            else:
                ret_val.content = processed_html

        lg.print_log("[PROGRESS:DESIGN:END]", "internal")

        # V19.5: 确保返回 ContentResult 对象而非原始字符串
        if isinstance(ret_val, str):
            return ContentResult(
                title=content.title,
                content=ret_val,
                summary=getattr(content, 'summary', ''),
                content_format="html",
                metadata={**content.metadata, "design_transformed": True}
            )
        return ret_val

    def _apply_dimensional_creative_transformation(
        self, base_content: ContentResult, **kwargs
    ) -> ContentResult:
        """维度化创意变换"""
        config = Config.get_instance()
        dimensional_config = config.dimensional_creative_config

        # 检查是否启用维度化创意
        if not dimensional_config.get("enabled", False):
            return base_content

        # 重新初始化维度化创意引擎以获取最新配置
        self.creative_engine = DimensionalCreativeEngine(dimensional_config)

        # 应用维度化创意变换
        try:
            transformed_content = self.creative_engine.apply_dimensional_creative(
                base_content.content, base_content.title
            )

            # V19.5: 修正 ContentResult 参数构造，匹配 dataclass 定义
            result = ContentResult(
                title=base_content.title,
                content=transformed_content,
                summary=getattr(base_content, 'summary', ''),
                content_format=base_content.content_format,
                metadata=base_content.metadata.copy(),
                content_type=base_content.content_type
            )

            # 添加变换元数据
            result.metadata.update(
                {
                    "transformation_type": "dimensional_creative",
                    "original_content_id": id(base_content),
                    "creative_engine_config": dimensional_config,
                }
            )

            return result

        except Exception as e:
            lg.print_log(f"维度化创意变换失败: {str(e)}", "error")
            return base_content

    def _get_template_workflow_config(
        self, publish_platform: str = PlatformType.WECHAT.value, **kwargs
    ) -> WorkflowConfig:
        """生成模板处理工作流配置"""
        # 获取配置以获取字数限制
        config = Config.get_instance()

        if publish_platform == PlatformType.WECHAT.value:
            # 微信平台的详细模板填充要求
            task_description = f"""
# HTML内容适配任务
## 任务目标
使用工具 read_template_tool 读取本地HTML模板，将以下文章内容适配填充到HTML模板中：

**文章内容：**
{{content}}

**文章标题：**
{{title}}

## 执行步骤
1. 首先使用 read_template_tool 读取HTML模板
2. 分析模板的结构、样式和布局特点
3. 获取前置任务生成的文章内容
4. 将新内容按照模板结构进行适配填充
5. 确保最终输出是基于原模板的HTML，保持视觉效果和风格不变

## 具体要求
- 分析HTML模板的结构、样式和布局特点
- 识别所有内容占位区域（标题、副标题、正文段落、引用、列表等）
- 将新文章内容按照原模板的结构和布局规则填充：
    * 保持<section>标签的布局结构和内联样式不变
    * 保持原有的视觉层次、色彩方案和排版风格
    * 保持原有的卡片式布局、圆角和阴影效果
    * 保持SVG动画元素和交互特性

- 内容适配原则：
    * 标题替换标题、段落替换段落、列表替换列表
    * 内容总字数{config.min_article_len}~{config.max_article_len}字，不可过度删减前置任务生成的文章内容
    * 当新内容比原模板内容长或短时，请直接复制并复用原模板中相同级别的带样式的 `<section>` 或 `<p>` 标签，绝不可破坏布局
    * **绝对禁止输出任何 Markdown 标记**（例如 `**粗体**`, `*斜体*`, `# 标题`）。必须完全使用纯净的 HTML 标签进行排版
    * 若要强调内容，必须使用 HTML的 `<span>` 或 `<strong>`，并参考原模板的配色给其添加合适的内联 `style`
    * 保持图片位置不变
    * 不可使用模板中的任何日期作为新文章的日期

- **图片插入与排版建议**:
    - 建议平均每个段落配置一张图片，或在观点转折处精准切入，提升阅读快感。
    - **生图质量管控**：生成的配图必须清晰、高端，**严禁**出现任何文字、字体、中国国旗/国徽及额外/畸形的手部肢体。
    - 图片格式：使用项目内图片路径或最终生成后的 `<img>` 标签，保留原有图片位置与样式，不要使用随机外链占位图

- 严格限制：
    * 不输出任何 Markdown 字符
    * 不添加新的style标签或外部CSS
    * 不改变原有的色彩方案（限制在三种色系内）
    * 不修改模板的整体视觉效果和布局结构"""

            backstory = "你是微信公众号模板处理专家，能够将内容适配到纯净HTML模板中。严格按照以下要求：保持<section>的布局结构和内联样式不变、保持原有的视觉层次、色彩方案和排版风格、**绝对禁止输出任何Markdown格式**、不可使用模板中的任何日期作为新文章的日期"  # noqa 501
        else:
            # 其他平台的简化模板处理
            task_description = "使用工具 read_template_tool 读取本地模板，将内容适配填充到模板中"
            backstory = "你是模板处理专家，能够将内容适配到模板中"

        agents = [
            AgentConfig(
                role="模板调整与内容填充专家",
                name="templater",
                goal="根据文章内容，适当调整给定的HTML模板，去除原有内容，并填充新内容。",
                backstory=backstory,
                tools=["ReadTemplateTool"],
            )
        ]

        tasks = [
            TaskConfig(
                name="template_content",
                description=task_description,
                agent_name="templater",
                expected_output="填充新内容但保持原有视觉风格的文章（HTML格式）",
            )
        ]

        return WorkflowConfig(
            name="template_formatting",
            description="模板格式化工作流",
            workflow_type=WorkflowType.SEQUENTIAL,
            content_type=ContentType.ARTICLE,
            agents=agents,
            tasks=tasks,
        )

    def _get_design_workflow_config(self, publish_platform: str, **kwargs) -> WorkflowConfig:
        """生成设计工作流配置 - V19.5 强制 HTML 输出"""

        content_preview = kwargs.get("content", "")
        topic = kwargs.get("topic", "")

        # 1. 分析内容调性
        tone = self._analyze_content_tone(content_preview, topic)

        # 2. 尝试使用动态引擎，失败则回退到超强内置模板
        wechat_system_template = ""
        if DYNAMIC_DESIGN_AVAILABLE:
            try:
                design_engine = DynamicDesignEngine.get_instance()
                wechat_system_template = design_engine.get_wechat_system_template(content_preview, topic)
                lg.print_log("✅ 动态设计模板加载成功", "success")
            except Exception as e:
                lg.print_log(f"⚠️ 动态设计模板生成失败: {e}", "warning")

        if not wechat_system_template:
            lg.print_log("🔧 使用内置强化 HTML 排版设计规范...", "info")
            wechat_system_template = f"""<|start_header_id|>system<|end_header_id|>
# 微信公众号专业 HTML 排版设计规范 (V19.5 核心版)

## 【核心任务】
你现在是一位顶级视觉设计师。请将 Markdown 文章内容转换为**可直接发布**的精美 HTML 代码。

## 【内容基调分析】
当前文章核心调性：**{tone.upper()}**

## 【强制输出规范 - 违反则任务失败】
1. **必须输出完整 HTML**：所有内容必须包裹在 `<section>` 容器内。
2. **必须使用内联样式**：禁止 external CSS，禁止 `<style>` 标签。所有样式必须内化到 `style="..."` 属性中。
3. **必须彻底清理 Markdown**：移除所有 `**`、`##`、`-` 、`>` 等 Markdown 符号。用 HTML 标签 (`<strong>`, `<h2>`) 代替。
4. **图片处理**：保留已有 `<img>` 标签；`[[V-SCENE:...]]` 为内部占位符，排版时不得转成「场景描述」等可见正文。
5. **禁止泄露生图信息**：不得把英文提示词、Negative Prompt、场景描述段落写进读者可见正文。
5. **严禁输出解释文字**：禁止输出任何非 HTML 文本（如“好的”、“代码如下”）。

## 【布局与组件库】
- **外层容器**：`<section style="max-width: 100%; margin: 10px auto; font-family: -apple-system, sans-serif; line-height: 1.8; color: #333;">`
- **黄金开头/金句 (绝对命令：必须放在最前面)**：正文第一行必须是纯文本的“黄金开头/金句”，**严厉禁止在此之前放置任何图片或 `V-SCENE`**。**文字必须使用纯黑 (#000000)、加粗、16px及以上字号**，确保视觉重心第一位。
- **布局严禁重叠**：**严禁使用任何形式的负数 margin (如 margin-top: -XXpx)**，文字必须在图片下方清晰排版，禁止覆盖。
- **卡片段落**：使用带有圆角和微弱投影的 section 包裹段落。
  `<section style="background: #fff; border-radius: 12px; padding: 20px; margin: 16px 0; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">`
- **高亮文本**：`<span style="background: linear-gradient(to bottom, transparent 60%, #ffeb3b 40%); padding: 0 2px; font-weight: bold; color: #000000;">`
- **大师标题**：`<h2 style="font-size: 22px; font-weight: bold; color: #000000; border-left: 4px solid #007bff; padding-left: 12px; margin: 25px 0 15px;">`

## 【输出格式】
- 将 HTML 代码包裹在 ```html ``` 代码块中，确保内容干净。
- 直接以 `<section>` 开头，以 `</section>` 结束。

现在，请开始你的设计，直接输出 HTML 代码：
<|eot_id|>"""

        # 根据平台定制设计要求
        platform_requirements = {
            PlatformType.WECHAT.value: "微信公众号HTML设计要求：使用内联CSS样式，避免外部样式表；采用适合移动端阅读的字体大小和行距；使用微信官方推荐的色彩搭配；确保在微信客户端中显示效果良好",  # noqa 501
            PlatformType.XIAOHONGSHU.value: "小红书平台设计要求：注重视觉美感，使用年轻化的设计风格；适当使用emoji和装饰元素；保持简洁清新的排版",
            PlatformType.ZHIHU.value: "知乎平台设计要求：专业简洁的学术风格；重视内容的逻辑性和可读性；使用适合长文阅读的排版",
        }

        design_requirement = platform_requirements.get(
            publish_platform, "通用HTML设计要求：简洁美观，注重用户体验"
        )

        agents = [
            AgentConfig(
                role="微信排版专家",
                name="designer",
                goal=f"为{publish_platform}平台创建精美的HTML设计和排版",
                backstory="你是HTML设计专家",
                system_template=(
                    wechat_system_template
                    if publish_platform == PlatformType.WECHAT.value
                    else None
                ),
                prompt_template="<|start_header_id|>user<|end_header_id|>{{ .Prompt }}<|eot_id|>",
            )
        ]

    def _get_html_packaging_config(self, publish_platform: str, **kwargs) -> WorkflowConfig:
        """V23.0: 视觉包装节点配置 - 零上下文 HTML 包装"""

        from src.ai_write_x.core.template_manager import TemplateManager
        tm = TemplateManager()
        # 获取对应平台的推荐模板
        recommended_templates = tm.get_templates_by_platform(publish_platform)[:2]
        template_codes = "\n\n".join([f"【模板 {i+1}】:\n{t.code}" for i, t in enumerate(recommended_templates)])

        from src.ai_write_x.core.brand_style import get_brand_style_prompt

        brand_block = get_brand_style_prompt()

        designer_des = f"""
# 专业视觉包装专家 (Visual Packaging Expert)

## 【核心任务】
你现在的任务是将一份**纯净的 Markdown 文章**包装成**极致专业的 HTML 代码**。
你必须在没有任何历史上下文干扰的情况下，专注于将内容完美契合进我们提供的排版模板中。
{brand_block}

## 【文章待包装内容】
文章内容：
{{content}}

文章标题：
{{title}}

## 【参考模板库】
以下是我们系统管理的高端模板代码供你参考和应用：
{template_codes}

## 【包装强制规范】
1. **零 Markdown 残留**：彻底移除所有 `#`, `##`, `**` 等符号，将其转换为对应的 HTML 标签（如 `<h2>`, `<strong>`）。
2. **内联样式强控**：所有 CSS 样式必须通过 `style="..."` 写入标签内部，严禁 `<style>` 或外部引用。
3. **布局卡片化**：内容必须包裹在具有圆角、投影和呼吸感的 `<section>` 容器内。
4. **图片视觉增强**：务必保留文章中已有的 `<img>` 标签，并为其添加 `max-width: 100%; border-radius: 12px; margin: 16px 0; box-shadow: 0 10px 30px rgba(0,0,0,0.1);` 等视觉增强样式。
5. **严禁废话**：直接输出包装后的 HTML 代码块，禁止输出“好的”、“包装如下”等任何解释性文字。
6. **中文读者友好**：所有可见标题/小标题必须为中文，禁止 Cinematic、Wide shot、Medium close-up 等英文术语。
7. **克制装饰**：以正文可读为先，不要插入大量 SVG 动画或占满屏的 Hero；每段不超过 120 字，用清晰的 h2/h3 分段。
8. **结构简洁**：优先使用 `<section>` + 内联样式，避免输出完整 `<!DOCTYPE html>` 文档壳。
9. **配图位置**：图片放在对应段落文字之后，不要插在标题与小标题之间。
10. **品牌配色一致**：若上方已给出品牌色，全文标题、装饰线、引用块边框必须使用该主色及辅色，禁止另起红/绿/紫等新主色。

## 【输出格式】
直接输出以 `<section>` 开头，`</section>` 结尾的完整 HTML 段落。
"""

        agents = [
            AgentConfig(
                role="视觉包装专家",
                name="packager",
                goal="将Markdown内容完美包装成专业HTML",
                backstory="你是顶级网页设计师和排版专家",
            ),
        ]

        tasks = [
            TaskConfig(
                name="package_html",
                description=designer_des,
                agent_name="packager",
                expected_output="完美包装后的HTML源码（内联样式，符合平台审美）",
            ),
        ]

        return WorkflowConfig(
            name="html_packaging",
            description="Final Stage: Zero-Context HTML Packaging",
            workflow_type=WorkflowType.SEQUENTIAL,
            content_type=ContentType.ARTICLE,
            agents=agents,
            tasks=tasks,
        )
        tasks = [
            TaskConfig(
                name="design_content",
                description=f"为{publish_platform}平台设计HTML排版。{design_requirement}。创建精美的HTML格式，包含适当的标题层次、段落间距、颜色搭配和视觉元素，确保内容在{publish_platform}平台上有最佳的展示效果。",  # noqa 501
                agent_name="designer",
                expected_output=f"针对{publish_platform}平台优化的精美HTML内容",
            )
        ]

        return WorkflowConfig(
            name=f"{publish_platform}_design",
            description=f"面向{publish_platform}平台的HTML设计工作流",
            workflow_type=WorkflowType.SEQUENTIAL,
            content_type=ContentType.ARTICLE,
            agents=agents,
            tasks=tasks,
        )

    def _save_content(self, content: ContentResult, title: str, reference_content: str = "") -> Dict[str, Any]:
        """保存内容（非AI参与）"""
        config = Config.get_instance()
        # 确定文件格式和路径
        file_extension = utils.get_file_extension(config.article_format)
        save_path = self._get_save_path(title, file_extension)

        # 保存文件
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(content.content)

        # V18: 保存原始参考内容，供前端“查看原热点内容”功能使用
        if reference_content:
            try:
                # 清理文件名，确保安全
                safe_filename = utils.sanitize_filename(title)
                dir_path = PathManager.get_article_dir()
                source_path = os.path.join(dir_path, f"{safe_filename}.source.txt")
                with open(source_path, "w", encoding="utf-8") as f:
                    f.write(reference_content)
                lg.print_log(f"📄 原始参考内容已保存至: {os.path.basename(source_path)}", "success")
            except Exception as e:
                lg.print_log(f"⚠️ 原始参考内容保存失败: {str(e)}", "warning")

        return {"success": True, "path": save_path, "title": title, "format": config.article_format}

    def _get_save_path(self, title: str, file_extension: str) -> str:
        """获取保存路径"""

        # 获取文章保存目录
        dir_path = PathManager.get_article_dir()

        # 清理文件名，确保安全
        safe_filename = utils.sanitize_filename(title)

        # 构建完整路径
        save_path = os.path.join(dir_path, f"{safe_filename}.{file_extension}")

        return save_path

    def _publish_content(
        self, content: ContentResult, publish_platform: str, **kwargs
    ) -> Dict[str, Any]:
        """发布内容（非AI参与）"""
        adapter = self.platform_adapters.get(publish_platform)

        if not adapter:
            return {"success": False, "message": f"不支持的平台: {publish_platform}"}

        article_path = kwargs.get("article_path")
        if article_path and publish_platform == PlatformType.WECHAT.value:
            from src.ai_write_x.core.visual_assets import VisualAssetsManager

            fresh_html = VisualAssetsManager.prepare_for_wechat_publish(article_path)
            if fresh_html:
                content.content = fresh_html
                try:
                    with open(article_path, "w", encoding="utf-8") as f:
                        f.write(fresh_html)
                except Exception as write_err:
                    lg.print_log(f"发布前回写文章文件失败: {write_err}", "warning")

        # 将 cover_path 传递给适配器（配图补齐后再解析封面）
        kwargs["cover_path"] = utils.get_cover_path(article_path)

        # 使用平台适配器发布
        # 适配器内部会自动保存发布记录
        publish_result = adapter.publish_content(content, **kwargs)

        return {
            "success": publish_result.success,
            "message": publish_result.message,
            "platform": publish_platform,
        }

    def _should_publish(self) -> bool:
        """判断是否应该发布"""
        config = Config.get_instance()

        # 检查配置中的自动发布设置
        if not config.auto_publish:
            return False

        # 检查是否有有效的微信凭据
        valid_credentials = any(
            cred["appid"] and cred["appsecret"] for cred in config.wechat_credentials
        )

        if not valid_credentials:
            # 自动转为非自动发布并提示
            lg.print_log("检测到自动发布已开启，但未配置有效的微信公众号凭据", "warning")
            lg.print_log("请在配置中填写 appid 和 appsecret 以启用自动发布功能", "warning")
            lg.print_log("当前将跳过发布步骤，仅生成内容", "info")
            return False

        return True

    def get_performance_report(self) -> Dict[str, Any]:
        """获取性能报告"""
        return {
            "workflow_metrics": self.monitor.get_metrics(),
            "recent_executions": self.monitor.get_recent_logs(limit=20),
            "system_status": "healthy" if self._check_system_health() else "degraded",
        }

    def _check_system_health(self) -> bool:
        """检查系统健康状态"""
        metrics = self.monitor.get_metrics()
        for workflow_name, workflow_metrics in metrics.items():
            if workflow_metrics.get("success_rate", 0) < 0.8:  # 成功率低于80%
                return False
        return True

    def register_platform_adapter(self, name: str, adapter):
        """注册新的平台适配器"""
        self.platform_adapters[name] = adapter

    def _analyze_content_tone(self, content: str, topic: str) -> str:
        """分析内容调性，用于配色方案选择 (V19.5 视觉增强)"""
        text = (topic + " " + content).lower()

        # 调性关键词映射
        tone_map = {
            "military": ["军事", "战争", "国防", "武器", "航母", "演习"],
            "tech": ["科技", "AI", "人工智能", "芯片", "数码", "互联网", "机器人"],
            "emotion": ["情感", "故事", "暖心", "感人", "回忆", "家庭", "爱"],
            "finance": ["财经", "股市", "投资", "经济", "房产", "宏观"],
            "news": ["新闻", "快讯", "突发", "报道", "现场"],
            "lifestyle": ["生活", "美食", "旅游", "穿搭", "家居"],
            "growth": ["职场", "成长", "技能", "学习", "效率"],
            "medical": ["医疗", "健康", "医生", "疾病", "养生"]
        }

        for tone, keywords in tone_map.items():
            if any(kw in text for kw in keywords):
                return tone

        return "default"

    def _apply_recursive_self_correction(self, content: str, topic: str, conversation_history: list = None, **kwargs) -> str:
        """V12.0: RSC 递归自我修正协议 - 2轮深度修正"""
        from src.ai_write_x.core.llm_client import LLMClient
        client = LLMClient()

        current_content = content
        max_iterations = 2

        if conversation_history is None:
            conversation_history = [
                {"role": "user", "content": f"请针对话题'{topic}'撰写初稿。"},
                {"role": "assistant", "content": content}
            ]

        for i in range(max_iterations):
            lg.print_log(f"🧬 RSC 快速修正第 {i+1} 轮...", "info")

            adversarial_prompt = prompt_loader.get_rsc("rsc", "adversarial_prompt").format(topic=topic)
            refactor_prompt = prompt_loader.get_rsc("rsc", "refactor_prompt")

            combined_prompt = (
                f"{adversarial_prompt}\n\n"
                f"请先快速判断是否存在逻辑问题。如果有，直接按以下指令重构全文；如果逻辑无误，输出 PASS。\n\n"
                f"【重构指令】\n{refactor_prompt}"
            )

            conversation_history.append({"role": "user", "content": combined_prompt})

            current_content_streamed = ""
            char_count_logged = 0
            for chunk in client.stream_chat(messages=conversation_history):
                if chunk:
                    current_content_streamed += chunk
                    if len(current_content_streamed) - char_count_logged >= 200:
                        lg.print_log(f"⏳ RSC 快速修正中... 已生成 {len(current_content_streamed)} 字", "status")
                        char_count_logged = len(current_content_streamed)

            if "PASS" in current_content_streamed.upper()[:50]:
                lg.print_log(f"✅ RSC 逻辑验证通过，无需修正", "success")
                conversation_history.append({"role": "assistant", "content": current_content_streamed})
                return current_content

            conversation_history.append({"role": "assistant", "content": current_content_streamed})
            current_content = utils.remove_code_blocks(current_content_streamed)
            lg.print_log(f"📝 RSC 快速修正完成，内容长度: {len(current_content)} 字", "success")

        return current_content
