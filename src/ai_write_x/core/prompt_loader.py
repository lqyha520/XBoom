import yaml
import threading
from pathlib import Path
from typing import Dict, Any, Optional

from src.ai_write_x.utils import log


class PromptLoader:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(PromptLoader, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._cache: Dict[str, Any] = {}
        self._prompts_dir: Optional[Path] = None
        self._initialized = True

    def _get_prompts_dir(self) -> Path:
        if self._prompts_dir is not None:
            return self._prompts_dir
        import sys
        from src.ai_write_x.utils.path_manager import PathManager
        base = PathManager.get_base_dir()
        candidates = []
        if hasattr(sys, "_MEIPASS"):
            candidates.append(Path(sys._MEIPASS) / "config" / "prompts")
        candidates.append(base / "config" / "prompts")
        for candidate in candidates:
            if candidate.exists():
                self._prompts_dir = candidate
                return self._prompts_dir
        self._prompts_dir = candidates[0]
        return self._prompts_dir

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        if filename in self._cache:
            return self._cache[filename]
        filepath = self._get_prompts_dir() / filename
        if not filepath.exists():
            log.print_log(f"[PromptLoader] 提示词文件不存在: {filepath}", "warning")
            return {}
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self._cache[filename] = data
            return data
        except Exception as e:
            log.print_log(f"[PromptLoader] 加载提示词文件失败 {filename}: {e}", "error")
            return {}

    def reload(self, filename: Optional[str] = None):
        if filename:
            self._cache.pop(filename, None)
        else:
            self._cache.clear()
        log.print_log(f"[PromptLoader] 缓存已清除: {'全部' if filename is None else filename}", "info")

    def get(self, filename: str, *keys: str, default: str = "") -> str:
        data = self._load_yaml(filename)
        for key in keys:
            if isinstance(data, dict) and key in data:
                data = data[key]
            else:
                log.print_log(f"[PromptLoader] 提示词路径不存在: {filename} -> {' -> '.join(keys)}", "warning")
                return default
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            return str(data)
        return default

    def get_dict(self, filename: str, *keys: str) -> Dict[str, Any]:
        data = self._load_yaml(filename)
        for key in keys:
            if isinstance(data, dict) and key in data:
                data = data[key]
            else:
                return {}
        return data if isinstance(data, dict) else {}

    def get_writer(self, *keys: str, default: str = "") -> str:
        return self.get("writer.yaml", *keys, default=default)

    def get_reviewer(self, *keys: str, default: str = "") -> str:
        return self.get("reviewer.yaml", *keys, default=default)

    def get_rsc(self, *keys: str, default: str = "") -> str:
        return self.get("rsc.yaml", *keys, default=default)

    def get_visual(self, *keys: str, default: str = "") -> str:
        return self.get("visual.yaml", *keys, default=default)

    def get_template_designer(self, *keys: str, default: str = "") -> str:
        return self.get("template_designer.yaml", *keys, default=default)

    def get_quality(self, *keys: str, default: str = "") -> str:
        return self.get("quality.yaml", *keys, default=default)

    def get_platform(self, *keys: str, default: str = "") -> str:
        return self.get("platform.yaml", *keys, default=default)

    def get_news(self, *keys: str, default: str = "") -> str:
        return self.get("news_analysis.yaml", *keys, default=default)

    def get_adaptive(self, *keys: str, default: str = "") -> str:
        return self.get("adaptive.yaml", *keys, default=default)

    def get_style_migration(self, platform: str) -> str:
        data = self.get_dict("platform.yaml", "style_migration", platform)
        if not data:
            data = self.get_dict("platform.yaml", "style_migration", "wechat")
        if not data:
            return ""
        persona = data.get("persona", "")
        rules = data.get("rules", "")
        template = self.get("platform.yaml", "style_migration_template", default="")
        return template.format(persona=persona, rules=rules)


prompt_loader = PromptLoader()
