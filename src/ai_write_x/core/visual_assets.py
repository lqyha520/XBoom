import re
from typing import Optional, Tuple
from src.ai_write_x.core.llm_client import LLMClient
from src.ai_write_x.core.prompt_loader import prompt_loader
import src.ai_write_x.utils.log as lg
import threading
import time

class HeartbeatLogger:
    def __init__(self, message="[Pulse] 仍在阅读文章并构思绘画分镜中...", interval=5.0):
        self.interval = interval
        self.message = message
        self._stop_event = threading.Event()
        self._thread = None
        self._start_time = 0

    def start(self):
        self._start_time = time.time()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run)
        self._thread.daemon = True
        self._thread.start()

    def _run(self):
        while not self._stop_event.wait(self.interval):
            elapsed = int(time.time() - self._start_time)
            lg.print_log(f"{self.message} (已耗时 {elapsed}s)", "info")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join()

class VisualAssetsManager:
    """视觉资产管理器：负责文本到图像的自动化提示词生成与后台同步渲染链路"""

    DEFAULT_COMFY_WORKFLOW_FILENAME = "z-image专用nf4快速备份.json"

    _visual_translation_cache = {}
    _paragraph_scene_cache = {}
    _visual_translation_lock = threading.Lock()

    _VSCENE_LINE_RE = re.compile(
        r'\[\[V-SCENE:\s*(.+?)\s*(?:\((.*?)\))?\s*(?:\|\s*(.+?)\s*)?\|\s*([\d\.:]+)\s*\]\]',
        re.DOTALL,
    )

    @staticmethod
    def _count_english_words(text: str) -> int:
        return len(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text or ""))

    @classmethod
    def _get_scene_word_bounds(cls) -> Tuple[int, int]:
        settings = cls._get_runtime_settings()
        min_words = cls._coerce_int(settings.get("visual_scene_min_words"), default=25, minimum=15, maximum=40)
        max_words = cls._coerce_int(settings.get("visual_scene_max_words"), default=50, minimum=25, maximum=80)
        if max_words < min_words:
            max_words = min_words + 10
        return min_words, max_words

    @classmethod
    def _sanitize_english_visual_text(cls, text: str) -> str:
        result = re.sub(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+', ' ', text or "")
        result = re.sub(r'^```[a-z]*\s*', '', result, flags=re.I)
        result = re.sub(r'```$', '', result)
        result = re.sub(r'\s+', ' ', result).strip()
        return result

    @classmethod
    def _translate_to_visual_english(cls, chinese_text: str, max_retries: int = 1) -> str:
        """将中文片段转为英文画面描述句（质量优先，约 25~50 词）。"""
        if not chinese_text or not chinese_text.strip():
            return ""
        has_chinese = bool(re.search(r'[\u4e00-\u9fff]', chinese_text))
        if not has_chinese:
            return chinese_text.strip()
        min_words, max_words = cls._get_scene_word_bounds()
        cache_key = f"desc:{chinese_text.strip()[:400]}:{min_words}:{max_words}"
        with cls._visual_translation_lock:
            if cache_key in cls._visual_translation_cache:
                return cls._visual_translation_cache[cache_key]
        try:
            llm = LLMClient()
            prompt = (
                f"将以下中文内容转换为适合 AI 绘画的英文画面描述。\n"
                f"要求：输出恰好 1 句英文，{min_words}~{max_words} 个英文词；"
                f"包含主体、环境、构图/镜头、光线；photorealistic editorial 风格；"
                f"不要列表、不要解释、不要中文、不要引号。\n\n"
                f"{chinese_text[:400]}"
            )
            settings = cls._get_runtime_settings()
            timeout = cls._coerce_int(
                settings.get("visual_paragraph_llm_timeout"),
                default=20,
                minimum=8,
                maximum=60,
            )
            result = llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.35,
                timeout=float(timeout),
                max_retries_override=max_retries,
            ).strip()
            result = cls._sanitize_english_visual_text(result)
            if cls._count_english_words(result) < 8:
                result = (
                    "editorial photography, medium wide shot, "
                    "professional editorial concept inspired by the article theme, "
                    "natural soft lighting, detailed environment, photorealistic, 8k"
                )
            with cls._visual_translation_lock:
                cls._visual_translation_cache[cache_key] = result
            return result
        except Exception as e:
            lg.print_log(f"[VisualAssets] 画面描述生成失败: {e}, 使用通用描述", "warning")
            fallback = (
                "editorial photography, medium wide shot, professional editorial scene, "
                "natural lighting, detailed environment, photorealistic, 8k, detailed"
            )
            with cls._visual_translation_lock:
                cls._visual_translation_cache[cache_key] = fallback
            return fallback

    @classmethod
    def _extract_vscene_line(cls, raw: str) -> Optional[str]:
        if not raw:
            return None
        text = raw.strip()
        match = cls._VSCENE_LINE_RE.search(text)
        if match:
            return match.group(0).strip()
        for line in text.splitlines():
            line = line.strip().strip("*")
            if "V-SCENE:" in line and "[[" in line:
                fixed = line if line.startswith("[[") else f"[[{line.lstrip('[')}"
                if fixed.endswith("]]"):
                    return fixed
        return None

    @classmethod
    def _normalize_vscene_line(cls, line: str, is_cover: bool) -> str:
        from src.ai_write_x.core.article_polish import append_no_text_negative

        match = cls._VSCENE_LINE_RE.search(line)
        if not match:
            return line
        pos = cls._sanitize_english_visual_text(match.group(1).strip())
        neg = append_no_text_negative(
            cls._sanitize_english_visual_text((match.group(3) or "").strip())
            or "bad anatomy, blurry, low quality, duplicate subject"
        )
        ratio = (match.group(4) or "").strip() or ("2.35:1" if is_cover else "16:9")
        if is_cover and ratio in ("16:9", "4:3", "3:4"):
            ratio = "2.35:1"
        min_words, _ = cls._get_scene_word_bounds()
        if cls._count_english_words(pos) < min_words // 2:
            pos = (
                f"{pos}, editorial photography, photorealistic, natural lighting, "
                "detailed environment, coherent perspective, 8k, detailed"
            ).strip(", ")
        pos = (
            f"{pos}, absolutely no text, no words, no letters, no Chinese characters, "
            "no subtitles, no watermark"
        )
        return f"[[V-SCENE: {pos} | {neg} | {ratio}]]"

    @classmethod
    def _build_vscene_fallback(cls, snippet: str, is_cover: bool = False) -> str:
        """LLM 不可用时的模板兜底（仍使用完整英文描述句，而非 3~8 关键词）。"""
        cleaned = cls._clean_visual_text(snippet)
        if not cleaned:
            cleaned = "article theme scene"
        scene_desc = cls._translate_to_visual_english(cleaned[:400])
        ratio = "2.35:1" if is_cover else "16:9"
        composition = (
            "cinematic hero cover, wide environmental composition, strong focal subject"
            if is_cover
            else "editorial photography, medium wide shot, clear single-subject composition"
        )
        pos_prompt = (
            f"{composition}, {scene_desc}, natural lighting, detailed environment, "
            "coherent perspective, professional color grading, photorealistic, 8k, detailed"
        )
        neg_prompt = (
            "text, words, letters, typography, Chinese characters, watermark, logo, "
            "subtitle, bad anatomy, blurry face, duplicate features, low detail"
        )
        return f"[[V-SCENE: {pos_prompt} | {neg_prompt} | {ratio}]]"

    @classmethod
    def _generate_vscene_from_paragraph(
        cls,
        paragraph: str,
        is_cover: bool = False,
        title_hint: str = "",
    ) -> str:
        """按段落调用 LLM 生成单条 V-SCENE（质量优先）。"""
        cleaned = cls._clean_visual_text(paragraph)
        if len(cleaned) < 12:
            return cls._build_vscene_fallback(paragraph, is_cover=is_cover)

        min_words, max_words = cls._get_scene_word_bounds()
        settings = cls._get_runtime_settings()
        timeout = cls._coerce_int(
            settings.get("visual_paragraph_llm_timeout"),
            default=20,
            minimum=8,
            maximum=60,
        )
        cache_key = f"vscene:{is_cover}:{title_hint[:80]}:{cleaned[:500]}:{min_words}:{max_words}"
        with cls._visual_translation_lock:
            if cache_key in cls._paragraph_scene_cache:
                return cls._paragraph_scene_cache[cache_key]

        cover_ratio = "2.35:1"
        body_ratio = "16:9"
        role_hint = "本图为文章封面，需有视觉冲击与明确主体。" if is_cover else "本图为正文配图，需贴合本段叙事。"
        title_hint = (title_hint or "（无）").strip()[:120]
        paragraph_text = cleaned[:800]

        system_prompt = prompt_loader.get_visual("paragraph_scene", "system_prompt").format(
            min_words=min_words,
            max_words=max_words,
            cover_ratio=cover_ratio,
            body_ratio=body_ratio,
        )
        user_prompt = prompt_loader.get_visual("paragraph_scene", "user_prompt").format(
            role_hint=role_hint,
            title_hint=title_hint,
            paragraph=paragraph_text,
        )

        try:
            llm = LLMClient()
            raw = llm.chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.45,
                timeout=float(timeout),
                max_retries_override=0,
            ).strip()
            line = cls._extract_vscene_line(raw)
            if line:
                normalized = cls._normalize_vscene_line(line, is_cover=is_cover)
                with cls._visual_translation_lock:
                    cls._paragraph_scene_cache[cache_key] = normalized
                return normalized
            lg.print_log("[VisualAssets] 段落分镜未返回有效 V-SCENE，使用模板兜底", "warning")
        except Exception as e:
            lg.print_log(f"[VisualAssets] 段落分镜 LLM 失败: {e}，使用模板兜底", "warning")

        fallback = cls._build_vscene_fallback(paragraph, is_cover=is_cover)
        with cls._visual_translation_lock:
            cls._paragraph_scene_cache[cache_key] = fallback
        return fallback
    
    @staticmethod
    def _get_runtime_settings() -> dict:
        from src.ai_write_x.config.config import Config

        config = Config.get_instance()
        return config.img_runtime_settings

    @staticmethod
    def _coerce_int(value, default: int, minimum: int = 1, maximum: Optional[int] = None) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        parsed = max(minimum, parsed)
        if maximum is not None:
            parsed = min(maximum, parsed)
        return parsed

    @staticmethod
    def _coerce_bool(value, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return default

    @staticmethod
    def _clean_visual_text(text: str) -> str:
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'!\[[^\]]*\]\([^)]+\)', ' ', text)
        text = re.sub(r'\[[^\]]+\]\([^)]+\)', ' ', text)
        text = re.sub(r'[`*_>#-]+', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    @staticmethod
    def _enforce_no_text_prompt(prompt: str, is_comfyui: bool = False) -> str:
        """统一给生图提示词追加"禁止图片文字"约束。

        说明：
        - 先移除提示词中的中文字符（防止模型在图片中渲染中文文字）
        - ComfyUI模式：正向提示词不加禁字后缀（避免模型误解），
          负向提示词由专用CLIPTextEncode节点处理，效果更好。
        - 其他API模式：正向和负向都加禁字约束。
        """
        from src.ai_write_x.core.article_polish import append_no_text_negative

        clean = (prompt or "").strip()
        if not clean:
            return clean

        clean = re.sub(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+', ' ', clean)
        clean = re.sub(r',\s*,', ',', clean)
        clean = re.sub(r',\s*$', '', clean)
        clean = re.sub(r'^\s*,\s*', '', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()

        if is_comfyui:
            if "--no" in clean:
                pos, neg = clean.split("--no", 1)
                return f"{pos.strip().rstrip(',')} --no {append_no_text_negative(neg.strip())}"
            return f"{clean} --no {append_no_text_negative('')}"

        positive_suffix = (
            "absolutely no text, no words, no letters, no Chinese characters, "
            "no subtitles, no captions, no watermark, no logo, no readable signs, "
            "no UI text, no QR code, no barcode"
        )
        if positive_suffix.lower() not in clean.lower():
            clean = f"{clean.rstrip(',')}, {positive_suffix}"

        if "--no" in clean:
            pos, neg = clean.split("--no", 1)
            return f"{pos.strip().rstrip(',')} --no {append_no_text_negative(neg.strip())}"
        return f"{clean} --no {append_no_text_negative('')}"

    @classmethod
    def get_target_image_count(cls) -> int:
        """每篇文章目标配图总数（含封面），来自基础设置 img_api.settings.article_image_count"""
        settings = cls._get_runtime_settings()
        raw = settings.get("article_image_count")
        if raw is None:
            raw = settings.get("fast_mode_prompt_count", 3)
        return cls._coerce_int(raw, default=3, minimum=1, maximum=12)

    @classmethod
    def get_body_image_slot_count(cls) -> int:
        """正文配图槽位数（总数减封面）"""
        return max(0, cls.get_target_image_count() - 1)

    @classmethod
    def _resolve_comfy_workflow_path(cls) -> Tuple[str, str, list]:
        """解析 ComfyUI 工作流 JSON 路径。返回 (路径, 文件名, 候选列表)。"""
        import os
        import shutil
        from src.ai_write_x.config.config import Config
        from src.ai_write_x.utils import utils
        from src.ai_write_x.utils.path_manager import PathManager

        comfy_cfg = Config.get_instance().config.get("img_api", {}).get("comfyui", {}) or {}
        custom = (comfy_cfg.get("workflow_file") or comfy_cfg.get("model") or "").strip()
        if custom and not custom.lower().endswith(".json"):
            custom = ""
        workflow_filename = custom or cls.DEFAULT_COMFY_WORKFLOW_FILENAME

        resource_workflow_path = utils.get_res_path(workflow_filename)
        appdata_workflow_path = os.path.join(str(PathManager.get_app_data_dir()), workflow_filename)
        base_dir = str(PathManager.get_base_dir())

        candidates = []
        if custom and os.path.isabs(custom):
            candidates.append(custom)
        candidates.extend([
            appdata_workflow_path,
            os.path.join(base_dir, workflow_filename),
            os.path.join(base_dir, "workflows", workflow_filename),
            os.path.join(str(PathManager.get_root_dir()), workflow_filename),
            str(resource_workflow_path),
        ])
        if utils.get_is_release_ver():
            candidates.extend([
                os.path.join(base_dir, "_internal", workflow_filename),
                os.path.join(base_dir, "_internal", "workflows", workflow_filename),
            ])

        if (
            utils.get_is_release_ver()
            and not os.path.isfile(appdata_workflow_path)
            and resource_workflow_path
            and os.path.isfile(resource_workflow_path)
        ):
            try:
                os.makedirs(os.path.dirname(appdata_workflow_path), exist_ok=True)
                shutil.copy2(resource_workflow_path, appdata_workflow_path)
                lg.print_log(f"  [ComfyUI] 已将工作流复制到用户目录: {appdata_workflow_path}", "info")
            except Exception as copy_e:
                lg.print_log(f"  [ComfyUI] 工作流复制到用户目录失败: {copy_e}", "warning")

        if os.path.isfile(appdata_workflow_path):
            candidates.insert(0, appdata_workflow_path)

        found = next((p for p in candidates if p and os.path.isfile(p)), "")
        return found, workflow_filename, candidates

    @classmethod
    def _build_fast_scene_prompt(cls, snippet: str, is_cover: bool = False, title_hint: str = "") -> str:
        """生成单条配图占位符（质量优先：按段落 LLM 分镜）。"""
        return cls._generate_vscene_from_paragraph(snippet, is_cover=is_cover, title_hint=title_hint)

    @classmethod
    def _extract_article_title_hint(cls, markdown_text: str) -> str:
        for line in markdown_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                return cls._clean_visual_text(stripped.lstrip("#").strip())
        return ""

    @classmethod
    def inject_image_prompts_fast(cls, markdown_text: str) -> str:
        """轻量注入：按段落 LLM 分镜（质量优先，不做全文重写）。"""
        if not markdown_text.strip():
            return markdown_text

        if "V-SCENE:" in markdown_text or "IMG_PROMPT:" in markdown_text:
            return markdown_text

        title_hint = cls._extract_article_title_hint(markdown_text)

        lines = markdown_text.splitlines()
        blocks = []
        current = []
        for line in lines:
            if line.strip():
                current.append(line)
            elif current:
                blocks.append("\n".join(current))
                current = []
        if current:
            blocks.append("\n".join(current))

        candidate_blocks = []
        for block in blocks:
            cleaned = cls._clean_visual_text(block)
            if len(cleaned) < 24:
                continue
            if cleaned.startswith("V SCENE") or cleaned.startswith("IMG PROMPT"):
                continue
            candidate_blocks.append(block)

        if not candidate_blocks:
            return markdown_text

        target_total = cls.get_target_image_count()
        prompt_limit = target_total
        prompt_count = min(prompt_limit, max(1, len(candidate_blocks)))
        body_slots = max(0, prompt_count - 1)
        chosen_blocks = candidate_blocks[: max(1, body_slots + 1)]

        lg.print_log(
            f"[VisualAssets] 按段落生成分镜（质量优先），共 {len(chosen_blocks)} 张，目标 {target_total} 张",
            "info",
        )

        cover_prompt = cls._generate_vscene_from_paragraph(
            chosen_blocks[0], is_cover=True, title_hint=title_hint
        )
        updated_text = markdown_text
        first_non_heading = re.search(r'\n(?!#)(.+)', markdown_text)
        if first_non_heading:
            insert_pos = first_non_heading.start()
            updated_text = updated_text[:insert_pos] + "\n" + cover_prompt + "\n" + updated_text[insert_pos:]
        else:
            updated_text = cover_prompt + "\n\n" + updated_text

        for block in chosen_blocks[1:]:
            marker = cls._generate_vscene_from_paragraph(
                block, is_cover=False, title_hint=title_hint
            )
            updated_text = updated_text.replace(block, f"{block}\n\n{marker}", 1)

        lg.print_log(
            f"[VisualAssets] 已注入 {len(chosen_blocks)} 组高质量配图提示词（目标共 {target_total} 张）",
            "info",
        )
        return updated_text

    @classmethod
    def inject_image_prompts(cls, markdown_text: str) -> str:
        """根据正文内容，自动分析并在适当位置插入 [IMG_PROMPT: prompt | ratio] 标签"""
        client = LLMClient()
        
        # 长度检查：如果文章太长，只取摘要/分段标题，防止 LLM 超时或 Context 爆炸
        # 提高阈值到 15000 字符，并允许更长的处理长度
        if len(markdown_text) > 1500000:
            lg.print_log(f"[VisualAssets] 文章长度 ({len(markdown_text)} 字符) 超过阈值，切换至分段场景抽离...")
            # 提取前 3000 字和后 3000 字，以及中间的所有标题
            lines = markdown_text.split('\n')
            headers = [line for line in lines if line.strip().startswith('#')]
            sample_text = markdown_text[:3000] + "\n\n" + "\n".join(headers) + "\n\n" + markdown_text[-3000:]
            processing_text = sample_text
        else:
            processing_text = markdown_text

        # 艺术化动态策略：从“机械字数配给”转向“叙事呼吸感分析”
        content_len = len(markdown_text)
        target_count = cls.get_target_image_count()
        safe_min = target_count
        safe_max = target_count
        
        system_prompt = prompt_loader.get_visual("visual_engineer", "system_prompt").format(safe_min=safe_min)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt_loader.get_visual("visual_engineer", "user_prompt").format(content_len=content_len, processing_text=processing_text)}
        ]
        
        try:
            lg.print_log("[PROGRESS:VISUAL:START]", "internal")
            lg.print_log(f"[PROGRESS:VISUAL:DETAIL] 模型: {client.current_model}<br>模式: 叙事呼吸感分析", "internal")
            lg.print_log(f"[VisualAssets] 🧠 正在分析全文并植入配图占位符（目标 {safe_min} 张）...")
            lg.print_log("[VisualAssets] 正在测算“视觉缓冲区”并植入绘画提示词...")
            
            heartbeat = HeartbeatLogger(interval=8.0)
            heartbeat.start()
            try:
                # 该步骤只用于“生成占位符”，对稳定性要求高：
                # - 缩短超时，避免卡几分钟
                # - 禁止重试，超时后直接降级到极速注入
                settings = cls._get_runtime_settings()
                visual_timeout = cls._coerce_int(
                    settings.get("visual_paragraph_llm_timeout"),
                    default=20,
                    minimum=15,
                    maximum=90,
                )
                enhanced_text = client.chat(
                    messages=messages,
                    temperature=0.7,
                    timeout=float(max(45, visual_timeout * 2)),
                    max_retries_override=1,
                )
            finally:
                heartbeat.stop()
                
            # 清理代码块包裹
            enhanced_text = re.sub(r'^```markdown\s*', '', enhanced_text)
            enhanced_text = re.sub(r'^```\s*', '', enhanced_text)
            enhanced_text = re.sub(r'```$', '', enhanced_text)
            
            # 如果是摘要模式处理的结果，且结果远短于原文，说明只输出了带标记的片段，需要合回原文
            if len(enhanced_text) < len(markdown_text) * 0.7 and 'V-SCENE:' in enhanced_text:
                lg.print_log("[VisualAssets] 检测到片段式输出，正在将提示词合并回原长文...")
                prompts = re.findall(r'\[\[V-SCENE:\s*.+?\s*\|\s*.+?\]\]', enhanced_text)
                if prompts:
                    lines = markdown_text.split('\n')
                    # 封面插入第一段后
                    for i, line in enumerate(lines):
                        if line.strip() and not line.strip().startswith('#'):
                            lines.insert(i+1, "\n" + prompts[0])
                            break
                    # 其余均衡分布
                    if len(prompts) > 1:
                        chunk_size = len(lines) // len(prompts)
                        for i in range(1, len(prompts)):
                            pos = min((i + 1) * chunk_size, len(lines)-1)
                            lines.insert(pos, "\n" + prompts[i])
                    enhanced_text = "\n".join(lines).strip()
                
            # strip_leaked_prompt_text 可能会误判并删除包含负向词的 V-SCENE 行，
            # 因此先“占位保护”再清理，最后再“还原”占位符。
            from src.ai_write_x.core.article_polish import strip_leaked_prompt_text
            placeholders = re.findall(r"\[\[V-SCENE:\s*[\s\S]*?\]\]", enhanced_text)
            protected_text = enhanced_text
            for i, ph in enumerate(placeholders):
                token = f"__VSCENE_PLACEHOLDER_{i}__"
                protected_text = protected_text.replace(ph, token, 1)

            cleaned = strip_leaked_prompt_text(protected_text.strip())
            for i, ph in enumerate(placeholders):
                token = f"__VSCENE_PLACEHOLDER_{i}__"
                cleaned = cleaned.replace(token, ph, 1)

            return cleaned
        except Exception as e:
            lg.print_log(
                f"[Warning] 视觉资产提示词植入失败：{str(e)}，已降级为极速注入占位符",
                "warning",
            )
            return cls.inject_image_prompts_fast(markdown_text)

    @classmethod
    def sync_trigger_image_generation(cls, text_with_prompts: str, timeout: Optional[int] = None) -> str:
        """扫描文本中的提示词标记（Markdown 或 HTML 占位符），调用图像 API 生成图片并替换

        Args:
            text_with_prompts: 包含图片占位符的文本
            timeout: 单张图片生成超时时间（秒），未传时读取配置
        """
        from bs4 import BeautifulSoup
        all_tasks = []
        
        # 1. 扫描提示词标记 
        # 优先级 A: 标准双中括号 [[V-SCENE: prompt | ratio]]
        # 优先级 B: 旧版 [IMG_PROMPT: prompt | ratio] 或 [图片解析: prompt]
        # 优先级 C: 捕捉自然语言出现的圆括号描述 (prompt)
        
        # 模式 A & B
        # 模式 A & B (V19.5 升级版：支持三段式格式 & 鲁棒性 Markdown 兼容)
        # [[V-SCENE: positive (comment) | negative | ratio]]
        # 兼容可能有 ** 包裹的情况: **[[V-SCENE: ...]]**
        pattern = r'(?:\*\*)?\[\[V-SCENE:\s*(.+?)\s*(?:\((.*?)\))?\s*(?:\|\s*(.+?)\s*)?\|\s*([\d\.:]+)\s*\]\](?:\*\*)?'
        for m in re.finditer(pattern, text_with_prompts):
            pos_prompt = m.group(1).strip()
            comment = m.group(2).strip() if m.group(2) else ""
            from src.ai_write_x.core.article_polish import append_no_text_negative
            neg_prompt = append_no_text_negative(
                m.group(3).strip() if m.group(3) else "bad anatomy, blurry face"
            )
            actual_ratio = m.group(4).strip() if m.group(4) else "16:9"
            
            # 整合提示词
            full_prompt = f"{pos_prompt} --no {neg_prompt}" if neg_prompt else pos_prompt
            full_prompt = cls._enforce_no_text_prompt(full_prompt)
            
            all_tasks.append({
                "prompt": full_prompt,
                "pos_prompt": pos_prompt,
                "neg_prompt": neg_prompt,
                "comment": comment,
                "ratio": actual_ratio,
                "original": m.group(0)
            })
            
        # 模式 C (仅当没有 A/B 且看起来像提示词时才尝试)
        if not all_tasks:
            # 扫描类似 (月偏食阶段对比图...) 的圆括号格式，通常出现在段落之后
            bracket_pattern = r'\n\s*\(([^)\n]{10,100})\)\s*\n' # 10-100字符的圆括号行
            for m in re.finditer(bracket_pattern, text_with_prompts):
                all_tasks.append({
                    "prompt": cls._enforce_no_text_prompt(m.group(1).strip()),
                    "ratio": "16:9",
                    "original": m.group(0)
                })
            
        # 2. 扫描 HTML 格式的占位符 <div class="img-placeholder" ...>...</div>
        try:
            soup = BeautifulSoup(text_with_prompts, "html.parser")
            placeholders = soup.find_all(class_="img-placeholder")
            for ph in placeholders:
                prompt = ph.get("data-img-prompt", "").strip()
                ratio = ph.get("data-aspect-ratio", "16:9").strip()
                if prompt:
                    # 使用 BeautifulSoup 的 replace_with 方法进行更稳定的替换
                    all_tasks.append({
                        "prompt": cls._enforce_no_text_prompt(prompt),
                        "ratio": ratio,
                        "original_element": ph # 保存元素对象
                    })
        except Exception as e:
            lg.print_log(f"[VisualAssets] BS 解析失败，降级使用正则: {e}", "warning")
            html_blocks = re.finditer(r'<div[^>]*class="img-placeholder"[^>]*>.*?</div>', text_with_prompts, re.DOTALL)
            for m in html_blocks:
                block = m.group(0)
                prompt_match = re.search(r'data-img-prompt=["\']([^"\']+)["\']', block)
                ratio_match = re.search(r'data-aspect-ratio=["\']([^"\']+)["\']', block)
                if prompt_match:
                    all_tasks.append({
                        "prompt": cls._enforce_no_text_prompt(prompt_match.group(1).strip()),
                        "ratio": (ratio_match.group(1).strip() if ratio_match else "16:9"),
                        "original": block
                    })
            
            # 模式 E: 扫描 <img> 标签 (鲁棒性加强)
            img_tags = re.finditer(r'<img[^>]*data-img-prompt=["\']([^"\']+)["\']([^>]*)>', text_with_prompts, re.IGNORECASE)
            for m in img_tags:
                prompt = m.group(1).strip()
                tag_body = m.group(0)
                ratio_match = re.search(r'data-aspect-ratio=["\']([^"\']+)["\']', tag_body)
                all_tasks.append({
                    "prompt": cls._enforce_no_text_prompt(prompt),
                    "ratio": (ratio_match.group(1).strip() if ratio_match else "16:9"),
                    "original": tag_body
                })

        if not all_tasks:
            return text_with_prompts

        def _task_priority(task):
            element = task.get("original_element")
            if element is not None and element.get("data-cover") == "1":
                return 0
            ratio = str(task.get("ratio") or "")
            if "2.35" in ratio or "21:9" in ratio:
                return 1
            return 2

        all_tasks.sort(key=_task_priority)
            
        lg.print_log(f"\n[VisualAssets] 共检测到 {len(all_tasks)} 张图片需要生成")
        
        from src.ai_write_x.config.config import Config
        from src.ai_write_x.utils.path_manager import PathManager
        import os, requests as req_lib
        
        config = Config.get_instance()
        runtime_settings = cls._get_runtime_settings()
        effective_timeout = cls._coerce_int(
            timeout if timeout is not None else runtime_settings.get("default_timeout_seconds"),
            default=60,
            minimum=5,
            maximum=600,
        )
        allow_placeholder_fallback = cls._coerce_bool(
            runtime_settings.get("allow_placeholder_fallback"),
            default=True,
        )
        img_api_type = config.img_api_type
        # 获取所有可用 Key 列表
        img_api_keys = config.get_img_api_keys()
        img_api_model = config.img_api_model
        
        # 初始化 Key 指针
        current_img_key_idx = 0
        if not img_api_keys:
            img_api_keys = [config.img_api_key]
        
        img_api_key = img_api_keys[current_img_key_idx]
        image_dir = PathManager.get_image_dir()
        
        # 获取 API base
        img_config = config.config.get("img_api", {})
        api_bases = {
            "modelscope": "https://api-inference.modelscope.cn/v1",
            "ali": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "agnes": "https://apihub.agnes-ai.com/v1",
        }
        
        # 智能提取当前选中的配置
        img_type_cfg = img_config.get(img_api_type, {})
        if img_api_type == "custom" and isinstance(img_type_cfg, list):
            custom_index = int(img_config.get("custom_index", 0) or 0)
            if 0 <= custom_index < len(img_type_cfg):
                img_type_cfg = img_type_cfg[custom_index]
            else:
                img_type_cfg = img_type_cfg[0] if img_type_cfg else {}
        elif not isinstance(img_type_cfg, dict):
            img_type_cfg = {}
            
        api_base = img_type_cfg.get("api_base", api_bases.get(img_api_type, ""))
        # 兼容性补充：如果全局 config 没拿到 key/model，尝试从局部提取
        if img_api_type == "custom":
            extracted_key = img_type_cfg.get("api_key")
            if extracted_key:
                img_api_key = extracted_key
            extracted_model = img_type_cfg.get("model")
            if extracted_model:
                img_api_model = extracted_model

        # 统一提取 api_base (供所有分支使用)
        actual_api_base = api_base
        if img_api_type == "agnes":
            actual_api_base = img_type_cfg.get("api_base", api_bases.get("agnes", ""))
            agnes_key = img_type_cfg.get("api_key", "")
            if agnes_key:
                img_api_key = agnes_key
            agnes_model = img_type_cfg.get("model", "")
            if agnes_model:
                img_api_model = agnes_model
            
        result_text = text_with_prompts
        generated_count = 0
        total_images = len(all_tasks)
        
        for idx, task in enumerate(all_tasks):
            prompt = task["prompt"]
            ratio = task["ratio"]
            # 'original' 仅在非 HTML 模式任务中存在，HTML 模式使用 'original_element'
            original_marker = task.get("original", "")
            
            lg.print_log(f"[VisualAssets] 🎨 正在生成第 {idx+1}/{len(all_tasks)} 张图片...")
            lg.print_log(f"  提示词: {prompt[:80]}...")
            lg.print_log(f"  比例: {ratio}, API: {img_api_type}, 模型: {img_api_model}")
            lg.print_log(f"[PROGRESS:VISUAL:DETAIL] 图片 {idx+1}/{len(all_tasks)} | {img_api_type} / {img_api_model}", "internal")
            
            # 根据比例计算尺寸
            size = cls._ratio_to_size(ratio.strip())
            
            img_path = None
            try:
                if img_api_type == "picsum":
                    # Picsum 随机图片
                    w_h = size.split("*")
                    download_url = f"https://picsum.photos/{w_h[0]}/{w_h[1]}?random={idx+1}"
                    from src.ai_write_x.utils import utils as u
                    img_path = u.download_and_save_image(download_url, str(image_dir))
                    
                elif img_api_type in ("modelscope", "ali", "custom") and (api_base or img_api_type == "custom") and img_api_key:
                    # OpenAI 兼容的图像 API (ModelScope/Ali 使用异步任务模式，Custom 使用 requests)
                    # 注意: Agnes 使用 OpenAI SDK 同步模式，不在此分支处理

                    if not actual_api_base:
                        lg.print_log(f"  [跳过] {img_api_type} API未配置 api_base", "warning")
                        continue
                    is_modelscope = img_api_type == "modelscope" or "modelscope" in actual_api_base.lower()
                    is_ali = img_api_type == "ali" or "dashscope" in actual_api_base.lower()

                    if idx > 0 and (is_modelscope or is_ali):
                         lg.print_log("  [等待] 为避免并发限制，稍作停顿 (2秒)...")
                         time.sleep(2)

                    if is_modelscope or is_ali:
                        import requests
                        headers = {
                            "Authorization": f"Bearer {img_api_key}",
                            "Content-Type": "application/json",
                        }
                        if is_modelscope:
                            headers["X-ModelScope-Async-Mode"] = "true"
                        if is_ali:
                            headers["X-DashScope-Async"] = "enable"
                        
                        endpoint = actual_api_base.rstrip('/')
                        if not endpoint.endswith('images/generations') and not endpoint.endswith('image-synthesis'):
                            # append standard openai path
                            endpoint = f"{endpoint}/images/generations"
                            
                        payload = {
                            "model": img_api_model,
                            "prompt": prompt,
                            "n": 1,
                            "size": size.replace("*", "x")
                        }
                        
                        # 获取全局代理
                        proxy = config.proxy
                        proxies = {"http": proxy, "https": proxy} if proxy else None
                        
                        res = req_lib.post(endpoint, headers=headers, json=payload, timeout=effective_timeout, proxies=proxies)

                        # --- 多 Key 自动容灾逻辑 (V19.0) ---
                        if (res.status_code == 429 or res.status_code == 401) and len(img_api_keys) > 1:
                            # 如果当前 Key 限流或失效，尝试切换下一个
                            current_img_key_idx = (current_img_key_idx + 1) % len(img_api_keys)
                            img_api_key = img_api_keys[current_img_key_idx]
                            lg.print_log(f"  [Failover] 图片 API {res.status_code}，切换至 Key {current_img_key_idx} 重试...", "warning")
                            # 重新执行当前任务循环 (通过继续外部循环的一个微调逻辑)
                            # 为了简单起见，我们在这里直接进行一次内部递归或重发请求
                            # 这里采用重发请求以保持逻辑线性
                            headers["Authorization"] = f"Bearer {img_api_key}"
                            res = req_lib.post(endpoint, headers=headers, json=payload, timeout=effective_timeout, proxies=proxies)
                        
                        res_json = res.json()
                        
                        if res.status_code == 429:
                            lg.print_log(f"  [跳过] {img_api_type} API 触发限流 (429) 且备用 Key 已耗尽。保留原文空位。", "warning")
                            continue
                            
                        elif res.status_code != 200:
                            raise Exception(f"图像生成请求失败: {res.status_code} - {res.text}")
                            
                        if not img_path: # IF not already fulfilled by fallback
                            task_id = None
                            # 灵活获取 task_id
                            if "task_id" in res_json:
                                task_id = res_json["task_id"]
                            elif "output" in res_json and "task_id" in res_json["output"]:
                                task_id = res_json["output"]["task_id"]
                            elif "id" in res_json: # 部分通用 API
                                task_id = res_json["id"]
                                
                            img_url = None
                            if not task_id:
                                # 尝试直接获取 url
                                if "data" in res_json and len(res_json["data"]) > 0:
                                    img_url = res_json["data"][0].get("url")
                                elif "output" in res_json and "url" in res_json["output"]:
                                    img_url = res_json["output"]["url"]
                                else:
                                    raise Exception(f"未能获取 task_id 或直接的 img_url: {res.text}")
                            else:
                                lg.print_log(f"  获取到任务ID: {task_id}, 开始轮询任务状态...")
                                # 构建任务查询地址
                                # 如果 api_base 包含 v1/images/generations, 尝试转换为 v1/tasks/task_id
                                base_task_url = actual_api_base.rstrip('/')
                                if "/images/generations" in base_task_url:
                                    base_task_url = base_task_url.replace("/images/generations", "")
                                
                                # 支持 ModelScope 和 DashScope 的任务端点
                                if is_ali:
                                    task_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
                                else:
                                    task_url = f"{base_task_url}/tasks/{task_id}"
                                
                                poll_headers = {
                                    "Authorization": f"Bearer {img_api_key}"
                                }
                                if is_modelscope:
                                    poll_headers["X-ModelScope-Task-Type"] = "image_generation"
                                    
                                # 通用轮询逻辑
                                for poll_idx in range(150): # 约 7-8 分钟
                                    time.sleep(5)
                                    try:
                                        # 获取全局代理
                                        proxy = config.proxy
                                        proxies = {"http": proxy, "https": proxy} if proxy else None
                                        task_res = req_lib.get(task_url, headers=poll_headers, timeout=10, proxies=proxies)
                                        t_json = task_res.json()
                                        
                                        # 兼容多种状态字段
                                        status = ""
                                        output = t_json.get("output", {}) if isinstance(t_json.get("output"), dict) else t_json
                                        status = t_json.get("task_status") or output.get("task_status") or t_json.get("status") or output.get("status")
                                        
                                        if not status and "task" in t_json: # 部分 API 嵌套在 task 中
                                            status = t_json["task"].get("status")
                                            
                                        if status in ("SUCCEEDED", "SUCCEED", "COMPLETED", "success"):
                                            lg.print_log(f"  ✅ 任务生成成功 (耗时 ~{poll_idx*5}s)")
                                            # 获取结果 URL
                                            if "output_images" in t_json and len(t_json["output_images"]) > 0:
                                                img_url = t_json["output_images"][0]
                                            elif "results" in output and len(output["results"]) > 0:
                                                img_url = output["results"][0].get("url")
                                            elif "data" in t_json and len(t_json["data"]) > 0:
                                                img_url = t_json["data"][0].get("url")
                                            elif "url" in output:
                                                img_url = output["url"]
                                            break
                                        elif status in ("FAILED", "CANCELED", "failed", "error"):
                                            raise Exception(f"生成任务失败: {status} - {t_json}")
                                        
                                        if poll_idx % 4 == 0:
                                            lg.print_log(f"  ⏳ 正在排队或渲染中... ({status})")
                                    except Exception as poll_e:
                                        lg.print_log(f"  [轮询警告] {str(poll_e)}", "warning")
                                        
                                if not img_url:
                                    raise Exception("轮询获取图片超时")
                                    
                            if img_url:
                                file_name = f"{img_api_type}_{int(time.time()*1000)}_{idx}.png"
                                file_path = os.path.join(str(image_dir), file_name)
                                # 获取全局代理
                                proxy = config.proxy
                                proxies = {"http": proxy, "https": proxy} if proxy else None
                                with open(file_path, "wb") as f:
                                    f.write(req_lib.get(img_url, timeout=30, proxies=proxies).content)
                                img_path = file_path
                            
                    else:
                        from openai import OpenAI
                        # 获取全局代理
                        proxy = config.proxy
                        proxies = {"http": proxy, "https": proxy} if proxy else None
                        
                        # OpenAI 客户端目前主要通过 HTTP 代理
                        http_client = None
                        if proxy:
                            import httpx
                            http_client = httpx.Client(proxy=proxy)
                            
                            client = OpenAI(api_key=img_api_key, base_url=actual_api_base, http_client=http_client)
                            try:
                                response = client.images.generate(
                                    model=img_api_model,
                                    prompt=prompt,
                                    n=1,
                                    size=size.replace("*", "x")  # OpenAI format: 1024x1024
                                )
                            except Exception as oai_err:
                                # OpenAI SDK 错误捕捉与多 Key 容灾
                                if ("429" in str(oai_err) or "401" in str(oai_err)) and len(img_api_keys) > 1:
                                    current_img_key_idx = (current_img_key_idx + 1) % len(img_api_keys)
                                    img_api_key = img_api_keys[current_img_key_idx]
                                    lg.print_log(f"  [Failover] OpenAI 图像接口故障，切换 Key {current_img_key_idx}...", "warning")
                                    client = OpenAI(api_key=img_api_key, base_url=actual_api_base, http_client=http_client)
                                    response = client.images.generate(
                                        model=img_api_model,
                                        prompt=prompt,
                                        n=1,
                                        size=size.replace("*", "x")
                                    )
                                else:
                                    raise oai_err

                            if response.data and len(response.data) > 0:
                                img_url = response.data[0].url
                                file_name = f"{img_api_type}_{int(time.time()*1000)}_{idx}.png"
                                file_path = os.path.join(str(image_dir), file_name)
                                # 获取全局代理
                                proxy = config.proxy
                                proxies = {"http": proxy, "https": proxy} if proxy else None
                                with open(file_path, "wb") as f:
                                    f.write(req_lib.get(img_url, timeout=30, proxies=proxies).content)
                                img_path = file_path

                elif img_api_type == "agnes" and img_api_key:
                    # Agnes 使用 OpenAI SDK 同步模式 (与 ModelScope/Ali 的异步任务模式不同)
                    if not actual_api_base:
                        lg.print_log("  [跳过] Agnes API未配置 api_base", "warning")
                        continue
                    # Agnes API 仅支持标准尺寸，将非标准尺寸映射到最接近的支持尺寸
                    # Agnes 支持的尺寸: 1024x1024, 1152x768, 768x1152, 1152x864, 864x1152, 1360x768, 768x1360
                    agnes_size_map = {
                        "1024x436": "1360x768",   # 2.35:1 → 16:9 宽幅（最接近）
                        "1024x576": "1360x768",   # 16:9 → Agnes 的 16:9
                        "1024x768": "1152x768",   # 4:3 → 3:2（最接近）
                        "768x1024": "768x1152",   # 3:4 → 2:3（最接近）
                        "1024x1024": "1024x1024", # 1:1
                    }
                    raw_size = size.replace("*", "x")
                    agnes_size = agnes_size_map.get(raw_size, "1024x1024")
                    if agnes_size != raw_size:
                        lg.print_log(f"  [Agnes] 尺寸映射: {raw_size} → {agnes_size}")
                    from openai import OpenAI
                    proxy = config.proxy
                    http_client = None
                    if proxy:
                        import httpx
                        http_client = httpx.Client(proxy=proxy)
                    client = OpenAI(api_key=img_api_key, base_url=actual_api_base, http_client=http_client)
                    try:
                        lg.print_log(f"  [Agnes] 正在调用 agnes-image API (size={agnes_size})...")
                        response = client.images.generate(
                            model=img_api_model or "agnes-image-2.1-flash",
                            prompt=prompt,
                            n=1,
                            size=agnes_size
                        )
                    except Exception as agnes_err:
                        err_str = str(agnes_err)
                        # 503/500 服务暂时不可用 → 短暂等待后重试一次
                        if "503" in err_str or "500" in err_str or "ServiceUnavailable" in err_str:
                            lg.print_log(f"  [Agnes] 服务暂时不可用，5秒后重试... ({err_str[:80]})", "warning")
                            import time as _t
                            _t.sleep(5)
                            response = client.images.generate(
                                model=img_api_model or "agnes-image-2.1-flash",
                                prompt=prompt,
                                n=1,
                                size=agnes_size
                            )
                        # 429/401 → 切换 Key
                        elif ("429" in err_str or "401" in err_str) and len(img_api_keys) > 1:
                            current_img_key_idx = (current_img_key_idx + 1) % len(img_api_keys)
                            img_api_key = img_api_keys[current_img_key_idx]
                            lg.print_log(f"  [Failover] Agnes 图像接口故障，切换 Key {current_img_key_idx}...", "warning")
                            client = OpenAI(api_key=img_api_key, base_url=actual_api_base, http_client=http_client)
                            response = client.images.generate(
                                model=img_api_model or "agnes-image-2.1-flash",
                                prompt=prompt,
                                n=1,
                                size=agnes_size
                            )
                        else:
                            raise agnes_err

                    if response.data and len(response.data) > 0:
                        img_url = response.data[0].url
                        file_name = f"agnes_{int(time.time()*1000)}_{idx}.png"
                        file_path = os.path.join(str(image_dir), file_name)
                        proxy = config.proxy
                        proxies = {"http": proxy, "https": proxy} if proxy else None
                        with open(file_path, "wb") as f:
                            f.write(req_lib.get(img_url, timeout=30, proxies=proxies).content)
                        img_path = file_path
                        lg.print_log(f"  ✅ Agnes 图片生成成功: {file_name}")

                elif img_api_type == "comfyui":
                    # 通用 ComfyUI 支持 - 端口从用户配置中读取，不硬编码默认值
                    if not api_base:
                        lg.print_log("  [跳过] ComfyUI API地址未配置，请在设置中配置 API 地址", "error")
                        continue
                    comfy_base_url = api_base.rstrip('/')
                    
                    # 0. 先测试 ComfyUI 服务是否可用
                    try:
                        test_res = req_lib.get(f"{comfy_base_url}/system_stats", timeout=5)
                        if test_res.status_code == 200:
                            lg.print_log(f"  ✅ ComfyUI 服务连接成功 ({comfy_base_url})", "info")
                        else:
                            lg.print_log(f"  ⚠️ ComfyUI 服务响应异常 (HTTP {test_res.status_code})，尝试继续...", "warning")
                    except Exception as test_e:
                        lg.print_log(f"  ❌ 无法连接到 ComfyUI 服务 ({comfy_base_url}): {test_e}", "error")
                        lg.print_log(f"  [提示] 请确认 ComfyUI 已启动并运行在 {comfy_base_url}", "warning")
                        continue
                    
                    from src.ai_write_x.utils import utils
                    comfy_workflow_path, workflow_filename, comfy_workflow_candidates = (
                        cls._resolve_comfy_workflow_path()
                    )
                    lg.print_log(f"  [ComfyUI] 正在查找工作流: {workflow_filename}", "info")
                    lg.print_log(
                        f"  [ComfyUI] 运行模式: {'打包版' if utils.get_is_release_ver() else '开发版'}",
                        "info",
                    )
                    if not comfy_workflow_path:
                        for idx_c, candidate in enumerate(comfy_workflow_candidates, 1):
                            lg.print_log(f"  [路径{idx_c}] {candidate} ❌ 不存在", "warning")
                    else:
                        lg.print_log(f"  [ComfyUI] 工作流文件: {comfy_workflow_path}", "info")
                    if not comfy_workflow_path:
                        if allow_placeholder_fallback:
                            lg.print_log(f"  [降级] 未找到 ComfyUI 工作流文件，自动切换为 Picsum 占位图", "warning")
                            w_h = size.split("*")
                            download_url = f"https://picsum.photos/{w_h[0]}/{w_h[1]}?random={idx+1}"
                            from src.ai_write_x.utils import utils as u
                            img_path = u.download_and_save_image(download_url, str(image_dir))
                            if not img_path:
                                lg.print_log("  [失败] Picsum 降级也失败，保留原占位符", "warning")
                            else:
                                lg.print_log("  [降级成功] 已使用 Picsum 占位图替代 ComfyUI输出", "warning")
                                task["fallback_notice"] = "当前图片为占位图：ComfyUI 工作流文件缺失，已临时回退到 Picsum。"
                            if not img_path:
                                continue
                        else:
                            raise Exception("未找到 ComfyUI 工作流文件，且当前配置已禁用占位图回退")
                        
                    import json
                    try:
                        with open(comfy_workflow_path, 'r', encoding='utf-8') as f:
                            workflow_data = json.load(f)
                    except Exception as json_e:
                        lg.print_log(f"  [失败] 工作流文件读取异常: {json_e}", "error")
                        continue
                        
                    # 2. 动态替换长宽和提示词参数
                    w_str, h_str = size.split("*")
                    
                    # 节点 34 是 CLIPTextEncode 正向提示词节点（按我们的专用工作流约定）
                    # 重要：ComfyUI 的工作流一般是“正向/负向”分离的，
                    # 不能指望模型理解 `--no ...` 语法，因此这里自动拆分并注入两个节点。
                    from src.ai_write_x.core.article_polish import append_no_text_negative
                    pos_for_comfy = prompt
                    neg_for_comfy = task.get("neg_prompt") or ""
                    if isinstance(pos_for_comfy, str) and "--no" in pos_for_comfy:
                        p, n = pos_for_comfy.split("--no", 1)
                        pos_for_comfy = p.strip().rstrip(",")
                        neg_for_comfy = (n or "").strip()
                    # ComfyUI正向提示词中移除"no text"类描述（由负向节点专门处理）
                    _no_text_patterns = [
                        r',?\s*absolutely no text[^,]*',
                        r',?\s*no words[^,]*',
                        r',?\s*no letters[^,]*',
                        r',?\s*no Chinese characters[^,]*',
                        r',?\s*no subtitles[^,]*',
                        r',?\s*no captions[^,]*',
                        r',?\s*no watermark[^,]*',
                        r',?\s*no logo[^,]*',
                        r',?\s*no readable signs[^,]*',
                        r',?\s*no UI text[^,]*',
                        r',?\s*no QR code[^,]*',
                        r',?\s*no barcode[^,]*',
                    ]
                    for pat in _no_text_patterns:
                        pos_for_comfy = re.sub(pat, '', pos_for_comfy, flags=re.I)
                    pos_for_comfy = pos_for_comfy.strip().rstrip(',')
                    # 统一加强"禁字"负向词库
                    neg_for_comfy = append_no_text_negative(neg_for_comfy or "bad anatomy, blurry face")

                    if "34" in workflow_data and "inputs" in workflow_data["34"]:
                        workflow_data["34"]["inputs"]["text"] = pos_for_comfy
                        
                    # 节点 37 是 EmptyLatentImage 空白画布节点
                    if "37" in workflow_data and "inputs" in workflow_data["37"]:
                        workflow_data["37"]["inputs"]["width"] = int(w_str)
                        workflow_data["37"]["inputs"]["height"] = int(h_str)
                        # 给模型每次不同的 noise seed
                        import random
                        if "35" in workflow_data and "inputs" in workflow_data["35"]:
                            workflow_data["35"]["inputs"]["seed"] = random.randint(1000000000, 99999999999999)
                        
                        # V19.5 Revision: 自动注入负向提示词 (Negative Prompt Injection)
                        # 你的专用工作流里默认用 ConditioningZeroOut 作为 negative（并不接收文本），
                        # 会导致负向提示词永远无法生效，所以这里做一次“工作流自愈”：
                        # - 若存在独立的负向 CLIPTextEncode：直接写入
                        # - 否则若检测到 ConditioningZeroOut(常见为节点 36)：将其替换成 CLIPTextEncode 负向节点
                        neg_prompt = neg_for_comfy
                        injected = False

                        # 1) 优先检查节点36（约定为负向节点）
                        if "36" in workflow_data:
                            node_36 = workflow_data["36"]
                            if node_36.get("class_type") == "CLIPTextEncode" and "inputs" in node_36 and "text" in node_36["inputs"]:
                                node_36["inputs"]["text"] = neg_prompt
                                lg.print_log(f"  [Negative] 已将负面提示词注入节点 36 (CLIPTextEncode)")
                                injected = True
                            elif node_36.get("class_type") == "ConditioningZeroOut":
                                workflow_data["36"] = {
                                    "inputs": {
                                        "text": neg_prompt,
                                        "clip": ["32", 0],
                                    },
                                    "class_type": "CLIPTextEncode",
                                    "_meta": {"title": "CLIP负向文本编码(自动修复)"},
                                }
                                lg.print_log("  [Negative] 检测到 ConditioningZeroOut，已自动替换为负向 CLIPTextEncode 节点 36", "info")
                                injected = True

                        # 2) 兜底：扫描其他非节点34的CLIPTextEncode
                        if not injected:
                            for node_id, node_info in workflow_data.items():
                                if node_id in ("34", "36"):
                                    continue
                                if node_info.get("class_type") == "CLIPTextEncode" and "inputs" in node_info and "text" in node_info["inputs"]:
                                    node_info["inputs"]["text"] = neg_prompt
                                    lg.print_log(f"  [Negative] 已将负面提示词注入节点 {node_id}")
                                    injected = True
                                    break

                        if not injected:
                            lg.print_log("  [Negative] 未找到可注入的负向节点（将仅依赖正向禁字约束）", "warning")

                        # V7.0 特有：NF4 优化 - 如果检测到是 NF4 工作流，注入质量增强词 + 调整采样参数
                        if "z_image_turbo_nvfp4" in str(workflow_data):
                            if "34" in workflow_data and "inputs" in workflow_data["34"]:
                                pos_for_comfy = f"{pos_for_comfy}, high quality, high resolution, masterpiece, detailed, cinematic lighting"
                                workflow_data["34"]["inputs"]["text"] = pos_for_comfy
                            # NF4量化模型需提高CFG让负向提示词生效，同时增加步数补偿质量
                            if "35" in workflow_data and "inputs" in workflow_data["35"]:
                                ksampler = workflow_data["35"]["inputs"]
                                old_cfg = ksampler.get("cfg", 1)
                                old_steps = ksampler.get("steps", 9)
                                if old_cfg <= 1.5:
                                    ksampler["cfg"] = 3.5
                                    lg.print_log(f"  [NF4优化] CFG {old_cfg} → 3.5（启用负向提示词引导）")
                                # 固定使用9步采样，优化生成速度
                                ksampler["steps"] = 9
                                if old_steps != 9:
                                    lg.print_log(f"  [采样优化] Steps {old_steps} → 9（快速生成模式）")

                    # 3. 先建立 WebSocket 连接，再提交任务（确保不丢消息）
                    img_filename = None
                    try:
                        import websocket as ws_client  # websocket-client 库
                        import uuid
                        
                        ws_url = comfy_base_url.replace("http://", "ws://").replace("https://", "wss://")
                        client_id = str(uuid.uuid4())
                        
                        lg.print_log(f"  🔗 正在连接 ComfyUI WebSocket...")
                        ws = ws_client.WebSocket()
                        ws.settimeout(99999)  # 用户禁用超时限制
                        ws.connect(f"{ws_url}/ws?clientId={client_id}", timeout=60)
                        lg.print_log(f"  ✅ WebSocket 连接已建立 (clientId: {client_id[:8]})")
                        
                        # 提交任务时必须带上 client_id，让 WS 只收到自己任务的消息
                        prompt_payload = {"prompt": workflow_data, "client_id": client_id}
                        res = req_lib.post(f"{comfy_base_url}/prompt", json=prompt_payload, timeout=10)
                        if res.status_code != 200:
                            ws.close()
                            raise Exception(f"提交 ComfyUI 任务失败: {res.text}")
                            
                        res_json = res.json()
                        prompt_id = res_json.get("prompt_id")
                        if not prompt_id:
                            ws.close()
                            raise Exception(f"未能在返回体中找到 prompt_id: {res_json}")
                            
                        lg.print_log(f"  📤 任务已提交 (prompt_id: {prompt_id}), 实时跟踪进度中...")
                        
                        # 4. 实时监听 WebSocket 消息
                        try:
                            while True:
                                raw = ws.recv()
                                if isinstance(raw, bytes):
                                    continue  # 跳过二进制预览帧
                                msg = json.loads(raw)
                                msg_type = msg.get("type", "")
                                data = msg.get("data", {})
                                
                                if msg_type == "execution_start":
                                    lg.print_log(f"  ⚡ ComfyUI 开始执行工作流...")
                                    
                                elif msg_type == "execution_cached":
                                    cached_nodes = data.get("nodes", [])
                                    if cached_nodes:
                                        lg.print_log(f"  ⏩ 已缓存节点 (跳过): {', '.join(cached_nodes)}")
                                        
                                elif msg_type == "executing":
                                    node_id = data.get("node")
                                    if node_id is None:
                                        # node=None 表示该 prompt 执行完毕
                                        lg.print_log(f"  ✅ ComfyUI 工作流执行完毕!")
                                        break
                                    # 优先读 _meta.title（人性化名称），其次 class_type
                                    node_info = workflow_data.get(str(node_id), {})
                                    node_title = node_info.get("_meta", {}).get("title") or node_info.get("class_type", f"Node-{node_id}")
                                    lg.print_log(f"  🔄 正在执行节点 [{node_id}] {node_title}")
                                    lg.print_log(f"[PROGRESS:VISUAL:DETAIL] 图片 {idx+1}/{len(all_tasks)} | 节点 {node_title}", "internal")
                                    
                                elif msg_type == "progress":
                                    step = data.get("value", 0)
                                    max_step = data.get("max", 0)
                                    if max_step > 0:
                                        pct = int(step / max_step * 100)
                                        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                                        lg.print_log(f"  📊 采样进度: [{bar}] {step}/{max_step} ({pct}%)")
                                        lg.print_log(f"[PROGRESS:VISUAL:DETAIL] 图片 {idx+1}/{len(all_tasks)} | 采样 {step}/{max_step} ({pct}%)", "internal")
                                        
                                elif msg_type == "executed":
                                    output_data = data.get("output", {})
                                    if "images" in output_data and len(output_data["images"]) > 0:
                                        img_filename = output_data["images"][0].get("filename")
                                        lg.print_log(f"  🖼️ 节点输出图片: {img_filename}")
                                        
                                elif msg_type == "execution_error":
                                    err_msg = data.get("exception_message", "未知错误")
                                    err_node_id = data.get("node_id", "?")
                                    err_node_type = data.get("node_type", "?")
                                    err_traceback = data.get("traceback", [])
                                    # 从工作流中获取出错节点的人性化名称
                                    err_node_info = workflow_data.get(str(err_node_id), {})
                                    err_node_title = err_node_info.get("_meta", {}).get("title") or err_node_type
                                    
                                    lg.print_log(f"  ❌ ComfyUI 执行错误!", "error")
                                    lg.print_log(f"  ❌ 出错节点: [{err_node_id}] {err_node_title} (类型: {err_node_type})", "error")
                                    lg.print_log(f"  ❌ 错误信息: {err_msg}", "error")
                                    if err_traceback:
                                        # 只显示 traceback 的最后几行（最关键的部分）
                                        tb_text = "\n".join(err_traceback) if isinstance(err_traceback, list) else str(err_traceback)
                                        tb_lines = tb_text.strip().split("\n")
                                        # 最多显示最后5行
                                        relevant_lines = tb_lines[-5:] if len(tb_lines) > 5 else tb_lines
                                        for line in relevant_lines:
                                            lg.print_log(f"  ❌ {line.strip()}", "error")
                                    raise Exception(f"ComfyUI 节点 [{err_node_id}] {err_node_title} 执行错误: {err_msg}")
                        finally:
                            ws.close()
                            
                        # WebSocket 完成后，如果没从 executed 消息拿到文件名，从 history 兜底获取
                        if not img_filename:
                            hist_res = req_lib.get(f"{comfy_base_url}/history/{prompt_id}", timeout=10)
                            if hist_res.status_code == 200:
                                hist_data = hist_res.json()
                                if prompt_id in hist_data:
                                    outputs = hist_data[prompt_id].get("outputs", {})
                                    for node_id_str, output_info in outputs.items():
                                        if "images" in output_info and len(output_info["images"]) > 0:
                                            img_filename = output_info["images"][0].get("filename")
                                            break
                                            
                    except ImportError:
                        # websocket-client 未安装，降级回 HTTP 轮询
                        lg.print_log("  ⚠️ websocket-client 未安装，降级为 HTTP 轮询 (pip install websocket-client 可启用实时进度)", "warning")
                        
                        # 降级模式下独立提交任务
                        prompt_payload = {"prompt": workflow_data}
                        res = req_lib.post(f"{comfy_base_url}/prompt", json=prompt_payload, timeout=10)
                        if res.status_code != 200:
                            raise Exception(f"提交 ComfyUI 任务失败: {res.text}")
                        res_json = res.json()
                        prompt_id = res_json.get("prompt_id")
                        if not prompt_id:
                            raise Exception(f"未能在返回体中找到 prompt_id: {res_json}")
                        lg.print_log(f"  📤 任务已提交 (prompt_id: {prompt_id}), 开始轮询...")
                        
                        for poll_round in range(100):
                            time.sleep(3)
                            hist_res = req_lib.get(f"{comfy_base_url}/history/{prompt_id}", timeout=10)
                            if hist_res.status_code == 200:
                                hist_data = hist_res.json()
                                if prompt_id in hist_data:
                                    outputs = hist_data[prompt_id].get("outputs", {})
                                    for node_id_str, output_info in outputs.items():
                                        if "images" in output_info and len(output_info["images"]) > 0:
                                            img_filename = output_info["images"][0].get("filename")
                                            break
                                    if img_filename:
                                        break
                            if (poll_round + 1) % 5 == 0:
                                lg.print_log(f"  ⏳ 仍在等待 ComfyUI 生成... ({(poll_round+1)*3}s)")
                    
                    if not img_filename:
                        raise Exception("ComfyUI 生成图片超时或失败 (无输出文件)")
                        
                    # 5. 下载图片并保存到本项目 images 对应目录
                    view_url = f"{comfy_base_url}/view?filename={img_filename}&type=output"
                    file_name = f"comfyui_{int(time.time()*1000)}_{idx}.png"
                    file_path = os.path.join(str(image_dir), file_name)
                    with open(file_path, "wb") as f:
                        f.write(req_lib.get(view_url, timeout=30).content)
                    img_path = file_path
                    
                    # 6. 防止 OOM：显式调用 ComfyUI 清理显存和卸载模型的接口
                    try:
                        req_lib.post(f"{comfy_base_url}/free", json={"unload_models": True, "free_memory": True}, timeout=5)
                        lg.print_log("  [清理] 已发送 ComfyUI 显存释放指令，防止连续生成 OOM")
                    except Exception as clean_e:
                        lg.print_log(f"  [清理] 尝试发送清理指令失败 (可忽略): {str(clean_e)}", "warning")
                        
                else:
                    lg.print_log(f"  [跳过] 图像API未配置或不支持 (type={img_api_type})", "warning")
                    
            except Exception as e:
                lg.print_log(f"  [失败] 图片 {idx+1} 生成异常: {e}", "error")
            
            # 替换占位符
            if not img_path:
                continue
            generated_count += 1
            is_cover = False
            if task.get("original_element") is not None:
                is_cover = task["original_element"].get("data-cover") == "1"
            if not is_cover:
                ratio_str = str(task.get("ratio") or "")
                is_cover = "2.35" in ratio_str or "21:9" in ratio_str
            extra_attrs = ""
            if is_cover:
                extra_attrs += ' data-cover="1"'
            ratio_val = (task.get("ratio") or ("2.35:1" if is_cover else "16:9")).strip()
            extra_attrs += f' data-aspect-ratio="{ratio_val}"'
            img_tag = (
                f'<img src="/images/{os.path.basename(img_path)}" alt="{prompt[:50]}"'
                f'{extra_attrs} style="max-width:100%;border-radius:12px;margin:16px 0;'
                f'box-shadow:0 10px 30px rgba(0,0,0,0.1);display:block;">'
            )
            fallback_notice = task.get("fallback_notice", "")
            if fallback_notice:
                img_tag = (
                    '<div style="margin:16px 0;padding:10px 12px;border-radius:10px;'
                    'background:#fff7e6;border:1px solid #ffd591;color:#ad6800;font-size:13px;line-height:1.6;">'
                    f'{fallback_notice}</div>{img_tag}'
                )
            
            if "original_element" in task and task["original_element"]:
                # HTML 模式：使用 BeautifulSoup 对象直接替换
                try:
                    new_img_soup = BeautifulSoup(img_tag, 'html.parser')
                    task["original_element"].replace_with(new_img_soup.contents[0])
                    lg.print_log(f"  ✅ HTML 图片 {idx+1} 替换成功")
                except Exception as replace_e:
                    lg.print_log(f"  ⚠️ HTML 替换失败，降级使用字符串替换: {replace_e}", "warning")
                    result_text = result_text.replace(str(task["original_element"]), img_tag)
            elif "original" in task and task["original"]:
                # Markdown 或正则降级模式：暴力字符串替换
                result_text = result_text.replace(task["original"], img_tag)
                lg.print_log(f"  ✅ 标记图片 {idx+1} 替换成功")

        # 如果有解析过 BeautifulSoup，并且有任务是通过对象替换的，则需要同步回字符串
        if 'soup' in locals() and any("original_element" in t for t in all_tasks):
            # 使用 formatter=None 避免转义字符（如 URL 中的 &）
            result_text = soup.decode(formatter=None)
            
        # 计算失败数量
        failed_count = total_images - generated_count
        
        if failed_count > 0:
            lg.print_log(f"[VisualAssets] ⚠️ 图片生成部分失败：成功 {generated_count} 张，失败 {failed_count} 张", "warning")
            lg.print_log(f"[VisualAssets] 💡 提示：请检查 ComfyUI 是否正在运行，或图片API配置是否正确", "warning")
            
            # 对于失败的占位符，用占位图片替换（而不是直接删除）
            def replace_failed_placeholder(match):
                placeholder_text = match.group(0)
                # 提取提示词（如果有）
                prompt_match = re.search(r'\[\[V-SCENE:\s*(.+?)\s*\]\]', placeholder_text)
                alt_text = prompt_match.group(1)[:50] if prompt_match else "图片生成失败"
                # 返回一个占位图片标签
                return f'<div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);border-radius:12px;padding:40px 20px;margin:16px 0;text-align:center;color:#fff;box-shadow:0 10px 30px rgba(0,0,0,0.1);"><div style="font-size:24px;margin-bottom:10px;">🖼️</div><div style="font-size:14px;opacity:0.9;">图片待生成</div><div style="font-size:12px;opacity:0.7;margin-top:8px;max-width:80%;word-wrap:break-word;">{alt_text}</div></div>'
            
            # 替换 V-SCENE 占位符为占位图片
            result_text = re.sub(r'\[\[V-SCENE:.*?\]\]', replace_failed_placeholder, result_text, flags=re.DOTALL)
            # 移除其他类型的占位符标记（这些通常不包含重要信息）
            result_text = re.sub(r'\[IMG_PROMPT:.*?\]', '', result_text)
            result_text = re.sub(r'\[图片解析[:：].*?\]', '', result_text)
        else:
            lg.print_log(f"[VisualAssets] ✅ 生成完成：成功生成并替换了 {generated_count} 张图片")
            # 全部成功时，清理残留标记
            result_text = re.sub(r'\[\[V-SCENE:.*?\]\]', '', result_text)
            result_text = re.sub(r'\[IMG_PROMPT:.*?\]', '', result_text)
            result_text = re.sub(r'\[图片解析[:：].*?\]', '', result_text)
        
        # 清理后可能产生的连续空行
        result_text = re.sub(r'\n{3,}', '\n\n', result_text)
        
        return result_text

    @classmethod
    def is_stock_placeholder_url(cls, src: str) -> bool:
        """是否为 Picsum 等随机占位图（不应视为 AI 配图已完成）"""
        if not src:
            return False
        lower = src.lower()
        stock_hosts = (
            "picsum.photos",
            "placeholder.com",
            "via.placeholder",
            "placehold.co",
            "dummyimage.com",
        )
        return any(h in lower for h in stock_hosts)

    @classmethod
    def count_valid_article_images(cls, html: str) -> int:
        """统计文章中已落地的有效配图（仅本地 /images/ 或本地文件，不含随机占位图）"""
        if not html:
            return 0
        from bs4 import BeautifulSoup
        import os
        from src.ai_write_x.utils.path_manager import PathManager

        soup = BeautifulSoup(html, "html.parser")
        image_dir = PathManager.get_image_dir()
        count = 0
        for img in soup.find_all("img"):
            src = (img.get("src") or "").strip()
            if not src or src.startswith("data:") or cls.is_stock_placeholder_url(src):
                continue
            if "/images/" in src:
                name = src.split("/images/")[-1].split("?")[0]
                if (image_dir / name).exists():
                    count += 1
                    continue
            if src.startswith(("http://", "https://")):
                continue
            if os.path.isfile(src):
                count += 1
        return count

    @classmethod
    def has_scene_description_leaks(cls, html: str) -> bool:
        if not html:
            return False
        if re.search(r"场景描述[：:]|画面描述[：:]", html, re.I):
            return True
        if "<" in html:
            from bs4 import BeautifulSoup
            from src.ai_write_x.core.article_polish import _SCENE_LABEL_RE

            soup = BeautifulSoup(html, "html.parser")
            for p in soup.find_all("p"):
                t = p.get_text(" ", strip=True)
                if t and (_SCENE_LABEL_RE.match(t) or t.startswith("场景描述")):
                    return True
        return False

    @classmethod
    def prepare_html_for_image_generation(cls, html: str) -> str:
        """生图前：场景描述转占位符，并去掉误展示的提示词段落"""
        from src.ai_write_x.core.article_polish import (
            convert_scene_description_paragraphs_to_placeholders,
            strip_leaked_prompt_text,
        )

        html = convert_scene_description_paragraphs_to_placeholders(html)
        html = strip_leaked_prompt_text(html)
        return html

    @classmethod
    def _image_prompt_text(cls, topic: str, context: str = "", is_cover: bool = False) -> tuple:
        raw_subject = (topic or "article theme").strip()[:60]
        raw_context = (context or topic or "article illustration").strip()[:120]

        subject_en = cls._translate_to_visual_english(raw_subject)
        context_en = cls._translate_to_visual_english(raw_context)

        if not subject_en or len(subject_en) < 3:
            subject_en = "professional editorial concept"
        if not context_en or len(context_en) < 3:
            context_en = "editorial scene"

        ratio = "2.35:1" if is_cover else "16:9"
        if is_cover:
            pos = (
                f"photo realistic cover image, {subject_en}, inspired by {context_en}, "
                "natural lighting, single clear subject, cinematic composition, "
                "absolutely no text no words no letters no Chinese characters"
            )
        else:
            pos = (
                f"photo realistic scene, {subject_en}, inspired by {context_en}, "
                "editorial photography, coherent perspective, "
                "absolutely no text no words no letters no Chinese characters no watermark"
            )
        return pos, ratio

    @classmethod
    def _build_scene_prompt(cls, topic: str, context: str = "", is_cover: bool = False) -> str:
        from src.ai_write_x.core.article_polish import append_no_text_negative

        pos, ratio = cls._image_prompt_text(topic, context, is_cover)
        neg = append_no_text_negative("bad anatomy, blurry, low quality, duplicate subject")
        return f"[[V-SCENE: {pos} | {neg} | {ratio}]]"

    @classmethod
    def inject_html_image_placeholders(cls, html: str, topic: str, title: str, min_count: int = 2) -> str:
        """在 HTML 中插入可生图的占位符（HTML 包装后兜底）"""
        from bs4 import BeautifulSoup

        if not html or not html.strip():
            return html

        soup = BeautifulSoup(html, "html.parser")
        body = soup.body or soup
        headings = body.find_all(["h2", "h3"])
        insert_targets = []

        # 封面图：放在首个实质段落之后（不要顶在标题前）
        first_p = None
        for p in body.find_all("p"):
            if len(p.get_text(strip=True)) >= 40:
                first_p = p
                break
        if first_p:
            insert_targets.append((first_p, True))

        # 章节配图：放在该节首段文字之后（图在文下，不在标题下）
        for h in headings[: max(min_count + 2, 4)]:
            if len(insert_targets) >= min_count + 1:
                break
            section_p = h.find_next("p")
            if section_p and len(section_p.get_text(strip=True)) >= 20:
                insert_targets.append((section_p, False))
            elif h.find_next_sibling(name="p"):
                insert_targets.append((h.find_next_sibling(name="p"), False))

        if not insert_targets and body.find("section"):
            sec_p = body.find("section").find("p")
            if sec_p:
                insert_targets.append((sec_p, True))

        for anchor, is_cover in insert_targets:
            ctx = title if is_cover else anchor.get_text(strip=True)[:80]
            prompt_text, ratio = cls._image_prompt_text(topic, ctx, is_cover=is_cover)
            # BeautifulSoup 处理带连字符的属性：使用 **{} 展开字典
            attrs = {
                "class": "img-placeholder",
                "data-img-prompt": prompt_text,
                "data-aspect-ratio": ratio,
            }
            if is_cover:
                attrs["data-cover"] = "1"
            # 使用 **attrs 展开字典，而不是 attrs=attrs
            ph = soup.new_tag("div", **attrs)
            ph.string = "配图生成中"
            anchor.insert_after(ph)

        return soup.decode(formatter=None)

    @classmethod
    def pick_cover_file_from_html(cls, html: str) -> Optional[str]:
        """从 HTML 中选取最佳封面（跳过 Picsum 等随机占位图）"""
        import os
        from bs4 import BeautifulSoup
        from src.ai_write_x.utils import utils

        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")
        ranked = []
        for img in soup.find_all("img"):
            src = (img.get("src") or "").strip()
            if not src or src.startswith("data:") or cls.is_stock_placeholder_url(src):
                continue
            resolved = utils.resolve_image_path(src)
            if not resolved or not os.path.isfile(resolved):
                if "/images/" in src:
                    from src.ai_write_x.utils.path_manager import PathManager
                    name = src.split("/images/")[-1].split("?")[0]
                    candidate = PathManager.get_image_dir() / name
                    if candidate.exists():
                        resolved = str(candidate)
            if not resolved or not os.path.isfile(resolved):
                continue
            score = 0
            if img.get("data-cover") == "1":
                score += 20
            if "cover" in (img.get("alt") or "").lower() or "封面" in (img.get("alt") or ""):
                score += 15
            if "2.35" in (img.get("data-aspect-ratio") or ""):
                score += 8
            if "/images/" in src:
                score += 5
            ranked.append((score, resolved))

        if ranked:
            ranked.sort(key=lambda x: -x[0])
            return ranked[0][1]
        return None

    @classmethod
    def generate_standalone_cover(cls, topic: str, title: str = "") -> Optional[str]:
        """无有效正文图时，单独调用图片 API 生成微信封面（2.35:1）"""
        import os
        import re
        from src.ai_write_x.utils import utils

        label = (title or topic or "文章").strip()
        marker = cls._build_scene_prompt(topic or label, label, is_cover=True)
        lg.print_log(f"[VisualAssets] 正在生成专用封面: {label[:40]}...", "info")
        try:
            out = cls.sync_trigger_image_generation(marker + "\n", timeout=120)
        except Exception as e:
            lg.print_log(f"[VisualAssets] 封面生成失败: {e}", "warning")
            return None

        for m in re.finditer(r'src=["\']([^"\']+)["\']', out or ""):
            src = m.group(1)
            if cls.is_stock_placeholder_url(src):
                continue
            path = utils.resolve_image_path(src)
            if path and os.path.isfile(path):
                lg.print_log(f"[VisualAssets] 封面已生成: {os.path.basename(path)}", "success")
                return path
        return None

    @classmethod
    def resolve_cover_for_article(
        cls, html: str, topic: str = "", title: str = ""
    ) -> Optional[str]:
        cover = cls.pick_cover_file_from_html(html)
        if cover:
            return cover
        return cls.generate_standalone_cover(topic, title)

    @classmethod
    def persist_cover_metadata(cls, article_path: str, html: str) -> Optional[str]:
        """写入 .design.json 封面路径（本地 ComfyUI 图，非 Picsum 随机图）"""
        import json
        import os
        from pathlib import Path

        if not article_path or not html:
            return None

        stem = Path(article_path).stem.replace("_", "|")
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else stem

        cover_path = cls.resolve_cover_for_article(html, topic=stem, title=title)
        if not cover_path or not os.path.isfile(cover_path):
            lg.print_log("[VisualAssets] 未能解析有效封面路径，发布时可能需手动上传", "warning")
            return None

        design_file = Path(article_path).with_suffix(".design.json")
        data = {}
        if design_file.exists():
            try:
                data = json.loads(design_file.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data["cover"] = cover_path
        design_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        lg.print_log(f"[VisualAssets] 封面已关联: {os.path.basename(cover_path)}", "info")
        return cover_path

    @classmethod
    def finalize_html_images(
        cls,
        html: str,
        topic: str,
        title: str,
        fast_mode: bool = False,
        article_path: str = "",
    ) -> str:
        """HTML 定稿后统一生图（避免排版阶段冲掉 Markdown 阶段的配图）"""
        if not html or not html.strip():
            return html

        from src.ai_write_x.core.article_polish import strip_unprocessed_visual_markers

        html = cls.prepare_html_for_image_generation(html)
        target_total = cls.get_target_image_count()
        min_images = target_total
        body_slots = cls.get_body_image_slot_count()
        valid = cls.count_valid_article_images(html)
        has_pending = bool(
            re.search(r"\[\[V-SCENE:", html)
            or "img-placeholder" in html
            or re.search(r"data-img-prompt=", html)
        )

        lg.print_log(
            f"[VisualAssets] HTML 定稿检查: 有效配图 {valid} 张, 目标 {min_images} 张, 待处理占位 {has_pending}",
            "info",
        )

        if valid < min_images and not has_pending:
            lg.print_log("[VisualAssets] 正文缺少配图，正在注入 HTML 占位符...", "info")
            html = cls.inject_html_image_placeholders(
                html, topic, title, min_count=max(1, body_slots)
            )

        settings = cls._get_runtime_settings()
        timeout = cls._coerce_int(
            settings.get("fast_mode_timeout_seconds" if fast_mode else "default_timeout_seconds"),
            default=45 if fast_mode else 90,
            minimum=15,
            maximum=600,
        )
        html = cls.sync_trigger_image_generation(html, timeout=timeout)
        html = strip_unprocessed_visual_markers(html)
        from src.ai_write_x.core.article_polish import clean_article_visual_leaks

        # 生图完成后再清理模板残留的随机占位图，避免与自定义图叠加
        removed_stock = 0
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            for img in soup.find_all("img"):
                src = (img.get("src") or "").strip()
                if cls.is_stock_placeholder_url(src):
                    img.decompose()
                    removed_stock += 1
            if removed_stock:
                lg.print_log(
                    f"[VisualAssets] 生图后已清理 {removed_stock} 张随机占位图",
                    "info",
                )
                html = soup.decode(formatter=None)
        except Exception as e:
            lg.print_log(f"[VisualAssets] 生图后清理随机占位图失败: {e}", "warning")

        html_before_leaks = html
        html = clean_article_visual_leaks(html)

        def _plain_len(h: str) -> int:
            return len(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h or "")).strip())

        before_len = _plain_len(html_before_leaks)
        after_len = _plain_len(html)
        if before_len >= 80 and after_len < max(30, int(before_len * 0.4)):
            lg.print_log(
                f"[VisualAssets] 正文可能被误清理（{before_len}→{after_len} 字），已回退为清理前内容",
                "warning",
            )
            html = html_before_leaks

        if article_path:
            cls.persist_cover_metadata(article_path, html)

        final_valid = cls.count_valid_article_images(html)
        has_pending_after = bool(
            re.search(r"\[\[V-SCENE:", html)
            or "img-placeholder" in html
            or re.search(r"data-img-prompt=", html)
        )
        has_stock_after = bool(re.search(r"(?:picsum\.photos|placeholder\.com|via\.placeholder|placehold\.co)", html, re.I))

        # 审计日志：用于定位“图片数量异常/仍有随机图/仍有占位符”等问题
        try:
            lg.print_log(
                "[VisualAssets][AUDIT] "
                f"目标图={min_images} | 有效图={final_valid} | "
                f"清理随机占位图={removed_stock} | "
                f"仍有待处理占位={has_pending_after} | "
                f"仍含随机图={has_stock_after}",
                "info",
            )
        except Exception:
            pass
        if final_valid < 1:
            lg.print_log("[VisualAssets] 配图生成未完成，请检查图片 API / ComfyUI 配置", "warning")
        else:
            lg.print_log(f"[VisualAssets] HTML 配图完成，共 {final_valid} 张", "success")
        return html

    @classmethod
    def article_needs_image_fix(cls, html: str) -> bool:
        """判断文章是否仍需补图（含 Picsum 随机占位图）"""
        if not html or not html.strip():
            return True
        valid = cls.count_valid_article_images(html)
        target = cls.get_target_image_count()
        has_pending = bool(
            re.search(r"\[\[V-SCENE:", html)
            or "img-placeholder" in html
            or re.search(r"data-img-prompt=", html)
        )
        has_picsum = bool(re.search(r"picsum\.photos", html, re.I))
        has_leaks = cls.has_scene_description_leaks(html)
        return (
            valid < max(1, target)
            or has_pending
            or has_leaks
            or has_picsum
        )

    @classmethod
    def prepare_for_wechat_publish(cls, article_path: str) -> str:
        """发布前同步补齐配图并刷新封面，返回最新 HTML"""
        from pathlib import Path

        path = Path(article_path)
        if not path.exists():
            return ""

        content = path.read_text(encoding="utf-8")
        if cls.article_needs_image_fix(content):
            lg.print_log("[VisualAssets] 发布前检测到配图未就绪，正在同步补齐...", "info")
            cls.auto_fix_article_images(str(path))
            content = path.read_text(encoding="utf-8")
        else:
            cls.persist_cover_metadata(str(path), content)

        return content

    @classmethod
    def auto_fix_article_images(cls, article_path_str: str) -> dict:
        """自动化补图：扫描文章中的图片占位符并调用图片API生成图片"""
        from pathlib import Path
        import os
        
        file_path = Path(article_path_str)
        if not file_path.exists():
            msg = f"文章路径不存在: {article_path_str}"
            lg.print_log(msg, "error")
            return {"status": "error", "message": msg}

        try:
            lg.print_log(f"开始自动修复文章图片: {article_path_str}", "info")
            content = file_path.read_text(encoding="utf-8")
            
            has_vscene = bool(re.search(r'\[\[V-SCENE:', content))
            has_img_prompt = bool(re.search(r'\[(?:IMG_PROMPT|图片解析)[:：]', content))
            has_placeholder = "img-placeholder" in content or "data-img-prompt=" in content
            has_scene_leaks = cls.has_scene_description_leaks(content)
            valid_images = cls.count_valid_article_images(content)
            has_picsum_imgs = bool(re.search(r"picsum\.photos", content, re.I))

            if (
                not has_vscene
                and not has_img_prompt
                and not has_placeholder
                and not has_scene_leaks
                and not has_picsum_imgs
                and valid_images >= 1
            ):
                lg.print_log(
                    f"[VisualAssets] 文章 {file_path.name} 已有 {valid_images} 张本地配图，跳过补图",
                    "success",
                )
                cls.persist_cover_metadata(article_path_str, content)
                return {"status": "skipped", "message": f"已有 {valid_images} 张有效配图"}
            
            # 1. 扫描是否已有提示词 (避免对已包含 prompts 的 HTML 重复注入)
            # 如果文章已经有提示词标记（[IMG_PROMPT]）或者 placeholder 已包含数据属性，说明 LLM 已经完成了分析
            has_explicit_prompts = re.search(r'\[(?:IMG_PROMPT|图片解析)[:：]\s*.+?\s*\|', content)
            has_data_prompts = 'data-img-prompt="' in content and 'img-placeholder' in content
            
            if (not has_explicit_prompts and not has_data_prompts) and ('<div class="img-placeholder"' in content or '[图片解析：]' in content):
                lg.print_log(f"[VisualAssets] 文章 {file_path.name} 包含空位，启动智能分析进程...", "info")
                content = cls.inject_image_prompts(content)
                file_path.write_text(content, encoding="utf-8")
            
            # 2. 无占位符且缺图：注入后再生成
            from src.ai_write_x.core.article_polish import (
                strip_unprocessed_visual_markers,
                strip_leaked_prompt_text,
            )

            if has_picsum_imgs:
                from src.ai_write_x.config.config import Config
                api_label = Config.get_instance().img_api_type
                lg.print_log(
                    f"[VisualAssets] 检测到 Picsum 随机占位图，将改用 {api_label} API 按场景描述重新生图",
                    "warning",
                )
                from bs4 import BeautifulSoup
                soup_fix = BeautifulSoup(content, "html.parser")
                for img in soup_fix.find_all("img"):
                    if cls.is_stock_placeholder_url(img.get("src") or ""):
                        img.decompose()
                content = soup_fix.decode(formatter=None)

            content = cls.prepare_html_for_image_generation(content)
            valid_images = cls.count_valid_article_images(content)
            has_placeholder = "img-placeholder" in content or "data-img-prompt=" in content

            if valid_images < 1 and not has_vscene and not has_placeholder:
                topic_guess = file_path.stem
                slots = max(1, cls.get_body_image_slot_count())
                content = cls.inject_html_image_placeholders(
                    content, topic_guess, topic_guess, min_count=slots
                )

            updated_content = cls.sync_trigger_image_generation(content)
            updated_content = strip_unprocessed_visual_markers(updated_content)
            updated_content = strip_leaked_prompt_text(updated_content)
            cls.persist_cover_metadata(article_path_str, updated_content)

            if updated_content != content:
                file_path.write_text(updated_content, encoding="utf-8")
                lg.print_log("文章图片占位符已成功替换为生成的图片。", "success")
            
            lg.print_log(f"自动补图流程结束。", "success")
            return {"status": "success", "message": "文章图片占位符已成功替换为生成的图片。"}
            
        except Exception as e:
            msg = f"自动修复文章图片遇到异常: {str(e)}"
            lg.print_log(msg, "error")
            import traceback
            lg.print_log(traceback.format_exc(), "error")
            return {"status": "error", "message": msg}

    @classmethod
    def _handle_single_generation(cls, prompt, ratio, size, image_dir, idx):
        """内部辅助方法：处理单张图片的生成逻辑 (提取自原有庞大的 sync_trigger_image_generation)"""
        try:
            from src.ai_write_x.config.config import Config
            import os, time, requests as req_lib
            
            config = Config.get_instance()
            img_api_type = config.img_api_type
            img_api_key = config.img_api_key
            img_api_model = config.img_api_model
            
            # 获取 api_base
            img_config = config.config.get("img_api", {})
            api_bases = {
                "modelscope": "https://api-inference.modelscope.cn/v1",
                "ali": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "agnes": "https://apihub.agnes-ai.com/v1",
            }
            img_type_cfg = img_config.get(img_api_type, {})
            if img_api_type == "custom" and isinstance(img_type_cfg, list):
                custom_index = int(img_config.get("custom_index", 0) or 0)
                if 0 <= custom_index < len(img_type_cfg):
                    img_type_cfg = img_type_cfg[custom_index]
                else:
                    img_type_cfg = img_type_cfg[0] if img_type_cfg else {}
            elif not isinstance(img_type_cfg, dict):
                img_type_cfg = {}
            api_base = img_type_cfg.get("api_base", api_bases.get(img_api_type, ""))
            
            # 同步更新当前使用的 key/model
            if img_api_type == "custom":
                img_api_key = img_type_cfg.get("api_key", img_api_key)
                img_api_model = img_type_cfg.get("model", img_api_model)
            
            # --- 核心生成逻辑 ---
            img_path = None
            
            if img_api_type == "picsum":
                w_h = size.split("*")
                download_url = f"https://picsum.photos/{w_h[0]}/{w_h[1]}?random={int(time.time())+idx}"
                from src.ai_write_x.utils import utils as u
                img_path = u.download_and_save_image(download_url, str(image_dir))
                
            elif img_api_type in ("modelscope", "ali", "agnes", "custom") and (api_base or img_api_type == "custom") and img_api_key:
                # 复用原有 API 调用逻辑 (简化版，确保核心可用)
                # ... (由于长度限制，这里通常应该调用一个更通用的 generate_image_sync 方法)
                # 为了保持代码简洁且不破坏原有复杂逻辑，我们在这里直接声明一个 generate_image_sync 的代理调用
                # 实际上 sync_trigger_image_generation(str) 原本就包含了这些。
                # 我们可以通过临时构建一个带有该标记的字符串来复用原有方法。
                marker = f"[IMG_PROMPT: {prompt} | {ratio}]"
                result_content = cls.sync_trigger_image_generation(marker)
                # 如果成功，result_content 应该包含了图片的 markdown 链接或者已经被处理
                # 我们通过正则搜寻结果中的文件名
                match = re.search(r'\((images/[^)]+)\)', result_content)
                if match:
                    rel_path = match.group(1)
                    # 转换回绝对路径
                    from src.ai_write_x.utils.path_manager import PathManager
                    img_path = os.path.join(str(PathManager.get_image_dir()), os.path.basename(rel_path))

            elif img_api_type == "comfyui":
                # ComfyUI 的逻辑也可以通过同样的方式复用
                marker = f"[IMG_PROMPT: {prompt} | {ratio}]"
                result_content = cls.sync_trigger_image_generation(marker)
                match = re.search(r'\((images/[^)]+)\)', result_content)
                if match:
                    rel_path = match.group(1)
                    from src.ai_write_x.utils.path_manager import PathManager
                    img_path = os.path.join(str(PathManager.get_image_dir()), os.path.basename(rel_path))
            
            return img_path
        except Exception as e:
            lg.print_log(f"单张图片生成核心失败: {e}", "error")
            return None

    @staticmethod
    def _ratio_to_size(ratio: str) -> str:
        """将比例字符串转换为像素尺寸"""
        ratio_map = {
            "16:9": "1024*576",
            "2.35:1": "1024*436",
            "4:3": "1024*768",
            "3:4": "768*1024",
            "1:1": "1024*1024",
        }
        return ratio_map.get(ratio, "1024*1024")
