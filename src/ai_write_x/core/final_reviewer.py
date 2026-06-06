from src.ai_write_x.core.llm_client import LLMClient
from src.ai_write_x.core.prompt_loader import prompt_loader
from src.ai_write_x.utils import log
import re

# 终审报告五维标签（成稿中不应出现）
REVIEW_DIMENSION_LABELS = (
    "开头吸引力",
    "论证深度",
    "信息密度",
    "叙事节奏",
    "AI痕迹",
    "阅读连贯性",
    "排版跳跃感",
    "情绪价值",
    "读者收获",
)

# Reflexion / 毒舌主编改稿时附加约束（禁止把审稿报告当正文）
ARTICLE_ONLY_REWRITE_SUFFIX = prompt_loader.get_reviewer("article_only_rewrite_suffix")


def is_editorial_review_report(content: str) -> bool:
    """判断文本是否为主编审稿/评分拆解/逻辑审核/事实核查（误当成稿）。"""
    if not content or len(content.strip()) < 40:
        return False
    text = content.strip()
    signals = 0
    if re.search(r"\[SCORE:\s*\d+\]", text, re.IGNORECASE):
        signals += 2
    if re.search(r"(?:深度文章)?评分与拆解", text):
        signals += 2
    if re.search(r"\[PASS:\s*(?:true|false)\]", text, re.IGNORECASE):
        signals += 2
    if "爆款指数" in text:
        signals += 1
    dim_hits = sum(1 for label in REVIEW_DIMENSION_LABELS if label in text)
    if dim_hits >= 2:
        signals += 2
    if dim_hits >= 3:
        signals += 1
    if re.search(
        r"(?:^|\n)\s*[\d①②③④⑤][\.、）\)]\s*(?:开头吸引力|论证深度|叙事节奏|AI痕迹|阅读连贯性|排版跳跃感|情绪价值)",
        text,
    ):
        signals += 1
    # V28: 扩展检测 - 逻辑审核报告、事实核查报告、RSC审核官输出
    if re.search(r"逻辑审核(?:报告)?", text):
        signals += 3
    if re.search(r"经逐段审查|经审查", text):
        signals += 2
    if re.search(r"逻辑跳跃", text):
        signals += 2
    if re.search(r"观点堆砌|论据空洞|注水段落", text):
        signals += 2
    if "核心重构员" in text:
        signals += 2
    if "逻辑审核官" in text:
        signals += 3
    if re.search(r"\[ALIGNMENT:\s*(?:pass|fail)\]", text, re.IGNORECASE):
        signals += 2
    if "事实核查报告" in text:
        signals += 3
    if re.search(r"致命错误[：:]", text):
        signals += 1
    if re.search(r"需(补充|重构|修复|进行二次重构)", text):
        signals += 1
    return signals >= 3


class FinalReviewer:
    """最终 AI 内容审查与打分器：担任主编视角对成稿进行终审"""

    ISSUE_KEYWORDS = {
        "fact_fix": ["事实", "数据", "时间", "日期", "年份", "数字", "错误", "不准确", "矛盾", "偏差", "编造", "虚构", "捏造"],
        "structure_fix": ["结构", "段落", "逻辑", "层次", "过渡", "衔接", "组织", "顺序", "跳跃", "前后"],
        "style_fix": ["文风", "语气", "表达", "修辞", "可读", "口语", "生动", "枯燥", "生硬", "模板化", "套话"],
        "anti_ai_fix": ["AI", "机器", "模板", "排比", "对称", "程式化", "套路", "痕迹", "检测", "人工智能"],
        "info_density_fix": ["信息密度", "空洞", "空泛", "具体", "数据", "案例", "细节", "收获", "干货", "内容不足"],
    }

    @classmethod
    def _classify_issues(cls, report: str) -> list:
        if not report:
            return []
        scores = {}
        for category, keywords in cls.ISSUE_KEYWORDS.items():
            count = sum(1 for kw in keywords if kw in report)
            if count > 0:
                scores[category] = count
        if not scores:
            return ["style_fix"]
        sorted_cats = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [cat for cat, _ in sorted_cats[:2]]
    
    @classmethod
    def assess_quality(cls, content: str, input_data: dict) -> dict:
        client = LLMClient()
        topic = input_data.get("topic", "未知主题")
        
        from datetime import datetime
        current_date_str = datetime.now().strftime('%Y年%m月%d日')
        
        system_prompt = prompt_loader.get_reviewer("reviewer", "system_prompt").format(current_date_str=current_date_str)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt_loader.get_reviewer("reviewer", "user_prompt").format(topic=topic, content=content)}
        ]
        
        import time
        max_retries = 2
        for attempt in range(max_retries):
            try:
                start_time = time.time()
                log.print_log(f"[FinalReviewer] 正在请求 Chief-Editor-AI 发起文章终审评估...(尝试 {attempt+1}/{max_retries})")
                report = client.chat(messages=messages, temperature=0.7)
                cost_time = time.time() - start_time
                report = report.replace("```markdown", "").replace("```", "").strip()
                
                # 精确提取分数（正则匹配比纯字符串更可靠）
                score_match = re.search(r'\[SCORE:\s*(\d+)\]', report, re.IGNORECASE)
                if not score_match:
                    # 备选正则容错：寻找末尾的"评分：85"等字样
                    score_match = re.search(r'(?:分数|评分|得分|爆款指数).*?(\d{2,3})', report[-100:], re.IGNORECASE)
                score = int(score_match.group(1)) if score_match else 0
                
                is_pass = "[pass: true]" in report.lower()
                # 如果AI漏了PASS标志但分数够高，容错通过
                if not is_pass and score >= 75:
                    is_pass = True
                # 如果分数太低，强制不通过
                if score > 0 and score < 60:
                    is_pass = False
                    
                log.print_log(f"\n\n{'='*20} [AI 首席主编终审评估报告] 耗时: {cost_time:.2f}s {'='*20}\n{report}\n{'='*64}\n")
                issue_categories = cls._classify_issues(report)
                return {"pass": is_pass, "report": report, "score": score, "issue_categories": issue_categories}
            except Exception as e:
                log.print_log(f"[Warning] 终审报告请求失败(尝试 {attempt+1}/{max_retries}): {str(e)}")
                if attempt == max_retries - 1:
                    return {"pass": True, "report": f"暂无评审数据 (错误: {str(e)})", "score": 0}
                time.sleep(2)


class AlignmentChecker:
    """最终 AI 内容对齐审查器：担任独立审核员核对二次打磨是否产生事实偏移"""
    
    @classmethod
    def check_alignment(cls, original_content: str, optimized_content: str) -> dict:
        client = LLMClient()
        
        from datetime import datetime
        current_date_str = datetime.now().strftime('%Y年%m月%d日')
        
        system_prompt = prompt_loader.get_reviewer("alignment_checker", "system_prompt").format(current_date_str=current_date_str)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt_loader.get_reviewer("alignment_checker", "user_prompt").format(original_content=original_content, optimized_content=optimized_content)}
        ]
        
        import time
        max_retries = 2
        for attempt in range(max_retries):
            try:
                start_time = time.time()
                log.print_log(f"[AlignmentChecker] 正在请求事实核查专员进行对照审查 (尝试 {attempt+1}/{max_retries})...")
                report = client.chat(messages=messages, temperature=0.1)
                cost_time = time.time() - start_time
                report = report.replace("```markdown", "").replace("```", "").strip()
                
                is_aligned = "[alignment: pass]" in report.lower()
                if "[alignment: pass]" not in report.lower() and "[alignment: fail]" not in report.lower():
                    is_aligned = True  # 宽容处理未遵从格式的情况
                    
                log.print_log(f"\n\n{'='*20} [AI 事实核对审查报告] 耗时: {cost_time:.2f}s {'='*20}\n{report}\n{'='*64}\n")
                return {"aligned": is_aligned, "report": report}
            except Exception as e:
                log.print_log(f"[Warning] 事实核对请求失败(尝试 {attempt+1}/{max_retries}): {str(e)}")
                if attempt == max_retries - 1:
                    return {"aligned": True, "report": "无法执行核对"}
                time.sleep(2)
