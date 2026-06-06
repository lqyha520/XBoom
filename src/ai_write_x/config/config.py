from typing import Any, Dict
import os
import yaml
import threading
import tomlkit

from src.ai_write_x.utils import log
from src.ai_write_x.utils import utils
from src.ai_write_x.utils.path_manager import PathManager

# 榛樿鍒嗙被閰嶇疆
DEFAULT_TEMPLATE_CATEGORIES = {
    "TechDigital": "绉戞妧鏁扮爜",
    "FinanceInvestment": "璐㈢粡鎶曡祫",
    "EducationLearning": "鏁欒偛瀛︿範",
    "HealthWellness": "鍋ュ悍鍏荤敓",
    "FoodTravel": "缇庨鏃呰",
    "FashionLifestyle": "鏃跺皻鐢熸椿",
    "CareerDevelopment": "鑱屽満鍙戝睍",
    "EmotionPsychology": "鎯呮劅蹇冪悊",
    "EntertainmentGossip": "濞变箰鍏崷",
    "NewsCurrentAffairs": "鏂伴椈鏃朵簨",
    "Others": "鍏朵粬",
}


# 鑷畾涔?Dumper锛屼粎璋冩暣鏁扮粍瀛愬厓绱犵缉杩?class IndentedDumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        # 寮哄埗鏁扮粍瀛愬厓绱狅紙-锛夌缉杩?2 涓┖鏍?        return super().increase_indent(flow, False)


class Config:
    """
    閰嶇疆绠＄悊绫?- 缁熶竴鐗堟湰绠＄悊绛栫暐

    鐗堟湰绠＄悊鏈€浣冲疄璺?
    1. 浣跨敤鏅鸿兘鍚堝苟绛栫暐澶勭悊閰嶇疆鍏煎鎬э紝鏇夸唬澶嶆潅鐨勭増鏈縼绉婚€昏緫
    2. 鎬绘槸浠ユ渶鏂伴粯璁ら厤缃负鍩哄噯锛屼繚鐣欑敤鎴锋湁鏁堥厤缃€?    3. 鐗堟湰鍙蜂富瑕佺敤浜庣敤鎴风晫闈㈡樉绀猴紝涓嶅奖鍝嶆牳蹇冨姛鑳?    """

    _instance = None
    # _lock = threading.Lock()
    _lock = threading.RLock()  # 鍙噸鍏ラ攣

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.config: Dict[Any, Any] = {}
        self.aiforge_config: Dict[Any, Any] = {}
        self.error_message = None
        self.config_path = self.__get_config_path()
        self.config_aiforge_path = self.__get_config_path("aiforge.toml")
        self.config_dimensional_path = self.__get_config_path("dimensional_creative_config.yaml")

        # 鍔犺浇缁村害鍖栧垱鎰忛厤缃?        self.dimensional_creative_options = {}

        # 榛樿閰嶇疆
        self.default_config = {
            "platforms": [
                {"name": "寰崥", "weight": 0.3, "enabled": True},
                {"name": "鎶栭煶", "weight": 0.2, "enabled": True},
                {"name": "灏忕孩涔?, "weight": 0.12, "enabled": True},
                {"name": "浠婃棩澶存潯", "weight": 0.1, "enabled": True},
                {"name": "鐧惧害鐑偣", "weight": 0.08, "enabled": True},
                {"name": "鍝斿摡鍝斿摡", "weight": 0.06, "enabled": True},
                {"name": "蹇墜", "weight": 0.05, "enabled": True},
                {"name": "铏庢墤", "weight": 0.05, "enabled": True},
                {"name": "璞嗙摚灏忕粍", "weight": 0.02, "enabled": True},
                {"name": "婢庢箖鏂伴椈", "weight": 0.01, "enabled": True},
                {"name": "鐭ヤ箮鐑", "weight": 0.01, "enabled": True},
            ],
            "publish_platform": "wechat",
            "wechat": {
                "credentials": [
                    {
                        "appid": "",
                        "appsecret": "",
                        "author": "",
                        "draft_only": False,
                        "call_sendall": False,
                        "sendall": True,
                        "tag_id": 0,
                    },
                ]
            },
            "api": {
                "api_type": "OpenRouter",
                "OpenRouter": {
                    "key": "OPENROUTER_API_KEY",
                    "key_index": 0,
                    "api_key": [],
                    "model_index": 0,
                    "fallback_model_index": -1,
                    "model": [
                        "openrouter/deepseek/deepseek-chat-v3-0324:free",
                        "openrouter/deepseek/deepseek-r1-0528:free",
                        "openrouter/deepseek/deepseek-prover-v2:free",
                        "openrouter/deepseek/deepseek-r1:free",
                        "openrouter/deepseek/deepseek-chat:free",
                        "openrouter/qwen/qwen3-32b:free",
                        "openrouter/qwen/qwq-32b:free",
                        "openrouter/google/gemini-2.0-flash-lite-preview-02-05:free",
                        "openrouter/google/gemini-2.0-flash-thinking-exp:free",
                    ],
                    "api_base": "https://openrouter.ai/api/v1",
                    "vision_model_index": 0,
                    "vision_model": [
                        "google/gemini-2.0-flash-001",
                        "google/gemini-2.0-pro-exp-02-05:free",
                        "openai/gpt-4o-mini",
                        "anthropic/claude-3.5-sonnet",
                        "qwen/qwen-vl-plus:free"
                    ],
                },
                "Deepseek": {
                    "key": "DEEPSEEK_API_KEY",
                    "key_index": 0,
                    "api_key": [],
                    "model_index": 0,
                    "fallback_model_index": -1,
                    "model": ["deepseek/deepseek-chat", "deepseek/deepseek-reasoner"],
                    "api_base": "https://api.deepseek.com/v1",
                },
                "Grok": {
                    "key": "XAI_API_KEY",
                    "key_index": 0,
                    "api_key": [],
                    "model_index": 0,
                    "fallback_model_index": -1,
                    "model": ["xai/grok-3"],
                    "api_base": "https://api.x.ai/v1/chat/completions",
                },
                "Qwen": {
                    "key": "OPENAI_API_KEY",
                    "key_index": 0,
                    "api_key": [],
                    "model_index": 0,
                    "fallback_model_index": -1,
                    "model": ["openai/qwen-plus"],
                    "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                },
                "Gemini": {
                    "key": "GEMINI_API_KEY",
                    "key_index": 0,
                    "api_key": [],
                    "model_index": 0,
                    "fallback_model_index": -1,
                    "model": [
                        "gemini/gemini-1.5-flash",
                        "gemini/gemini-1.5-pro",
                        "gemini/gemini-2.0-flash",
                    ],
                    "api_base": "https://generativelanguage.googleapis.com/v1beta/openai/",
                    "vision_model_index": 0,
                    "vision_model": [
                        "gemini/gemini-2.0-flash",
                        "gemini/gemini-1.5-flash",
                        "gemini/gemini-1.5-pro"
                    ],
                },
                "Ollama": {
                    "key": "OPENAI_API_KEY",
                    "model_index": 0,
                    "fallback_model_index": -1,
                    "key_index": 0,
                    "api_key": [],
                    "model": ["ollama/deepseek-r1:14b", "ollama/deepseek-r1:7b"],
                    "api_base": "http://localhost:11434",
                },
                "SiliconFlow": {
                    "key": "OPENAI_API_KEY",
                    "key_index": 0,
                    "api_key": [],
                    "model_index": 0,
                    "fallback_model_index": -1,
                    "model": [
                        "openai/deepseek-ai/DeepSeek-V3",
                        "openai/deepseek-ai/DeepSeek-R1",
                        "openai/Qwen/QwQ-32B",
                        "openai/Qwen/Qwen3-32B",
                    ],
                    "api_base": "https://api.siliconflow.cn/v1",
                    "provider": "openai",
                    "vision_model_index": 0,
                    "vision_model": [
                        "openai/Qwen/Qwen2-VL-72B-Instruct",
                        "openai/Qwen/Qwen2-VL-7B-Instruct",
                        "openai/Pro/Qwen/Qwen2-VL-7B-Instruct",
                        "openai/deepseek-ai/deepseek-vl2"
                    ],
                },
                "蹇冩祦": {
                    "key": "OPENAI_API_KEY",
                    "key_index": 0,
                    "api_key": [],
                    "model_index": 0,
                    "fallback_model_index": -1,
                    "model": [
                        "deepseek-v3",
                        "kimi-k2",
                        "glm-4.6",
                        "deepseek-r1",
                        "qwen3-32b",
                    ],
                    "api_base": "https://apis.iflow.cn/v1",
                    "provider": "zhipu",
                    "vision_model_index": 0,
                    "vision_model": [
                        "glm-4v",
                        "qwen-vl-plus",
                        "qwen-vl-max"
                    ],
                },
                "deleted_providers": [],  # 鐢ㄦ埛涓诲姩鍒犻櫎鐨勬彁渚涘晢榛戝悕鍗?            },
            "img_api": {
                "api_type": "picsum",
                "ali": {"api_key": "", "model": "wanx2.0-t2i-turbo", "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
                "modelscope": {"api_key": "", "model": "Tongyi-MAI/Z-Image-Turbo", "api_base": "https://api-inference.modelscope.cn/v1"},
                "agnes": {"api_key": "", "model": "agnes-image-2.1-flash", "api_base": "https://apihub.agnes-ai.com/v1"},
                "picsum": {"api_key": "", "model": ""},
                "comfyui": {"api_key": "", "model": "", "api_base": ""},
                "settings": {
                    "default_timeout_seconds": 60,
                    "fast_mode_timeout_seconds": 45,
                    "article_image_count": 3,
                    "fast_mode_prompt_count": 3,
                    "fast_mode_prompt_excerpt_length": 120,
                    "visual_scene_min_words": 25,
                    "visual_scene_max_words": 50,
                    "visual_paragraph_llm_timeout": 20,
                    "allow_placeholder_fallback": True,
                },
                "custom": [],
            },
            "update": {
                "enabled": True,
                "startup_check": True,
                "mandatory_update_enabled": True,
                "auto_update_on_startup": True,
                "auto_update_silent": True,
                "provider": "gitee_release",
                "gitee_owner": "lqyha520",
                "gitee_repo": "XBoom",
                "gitee_branch": "master",
                "gitee_release_path": "releases",
                "gitee_token": "",
                "github_owner": "lqyha520",
                "github_repo": "XBoom",
                "allow_prerelease": False,
                "manifest_url": "https://updates.bcxtech.cn/updates/version-policy.json",
                "update_mirror_base": "https://updates.bcxtech.cn/updates",
                "manifest_asset_name": "version-policy.json",
                "installer_asset_name": "灏忕垎鏉ュ挴-Setup.exe",
                "installer_silent_args": "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS",
                "restart_executable": "灏忕垎鏉ュ挴.exe",
                "check_timeout_seconds": 15,
                "download_timeout_seconds": 600,
                "min_supported_version": "",
                "latest_version": "",
                "manual_download_url": "",
                "prefer_mirror": True,
                "fallback_github": False,
            },
            "usage_stats": {
                "enabled": True,
                "report_url": "https://updates.bcxtech.cn/stats/report.php",
                "report_token": "",
                "timeout_seconds": 8,
                "release_only": False,
            },
            # 鍙楅檺鑿滃崟鐧藉悕鍗曪細鍚姩鏃惰繛 MySQL锛堝彲涓?MaxScale 鍦板潃锛夎鍙?menu_ip_whitelist 琛?            "menu_access": {
                "enabled": True,
                "api_url": "https://updates.bcxtech.cn/stats/menu_access_check.php",
                "api_token": "",
                "timeout_seconds": 8,
                "mysql": {
                    "host": "",
                    "port": 3306,
                    "database": "XBoom",
                    "user": "",
                    "password": "",
                    "connect_timeout": 5,
                },
            },
            "proxy": "",  # 鍏ㄥ眬浠ｇ悊 (e.g., http://127.0.0.1:7890)
            "use_template": True,
            "use_dynamic_template": True,  # 浣跨敤AI鍔ㄦ€佺敓鎴愭ā鏉?            "strict_freshness": True,      # 寮哄埗璇濋鏂伴矞搴﹁繃婊?            "designer_model": "",          # 妯℃澘璁捐妯″瀷 (鐣欑┖鍒欎娇鐢ㄤ富妯″瀷)
            "refiner_model": "",           # 璇箟绮句慨妯″瀷 (鐣欑┖鍒欎娇鐢ㄤ富妯″瀷)
            "template_category": "",
            "template": "",
            "use_compress": True,
            "enable_aiforge": True,
            "aiforge_search_max_results": 10,
            "aiforge_search_min_results": 1,
            "min_article_len": 1000,
            "max_article_len": 2000,
            # V15.0: 閲忓瓙浼樺寲閰嶇疆
            "v15_quantum_optimization": {
                "enabled": True,                           # 鍚敤 V15 浼樺寲
                "enable_smart_batching": True,             # 鏅鸿兘鎵瑰鐞?                "enable_semantic_cache": True,             # 璇箟缂撳瓨 V2
                "enable_adaptive_routing": True,           # 鑷€傚簲妯″瀷璺敱
                "cache_similarity_threshold": 0.88,        # 缂撳瓨鐩镐技搴﹂槇鍊?                "batch_window_ms": 50,                     # 鎵瑰鐞嗙獥鍙?(姣)
                "max_batch_size": 20,                      # 鏈€澶ф壒澶勭悊鏁?            },
            # V18.0: 鑷富 Agent 铚傜兢骞跺彂閰嶇疆
            "swarm_settings": {
                "swarm_mode_enabled": False,               # 榛樿涓嶅紑鍚渹缇ゆā寮?                "serial_mode_forced": True,                # 榛樿寮哄埗涓茶妯″紡(骞跺彂=1)
                "max_concurrency": 1                       # 褰撳己鍒朵覆琛屼负 True 鏃讹紝閿佸畾涓?1
            },
            "auto_publish": False,
            "auto_delete_published": False,
            "article_format": "html",
            "format_publish": True,
            # 缁村害鍖栧垱鎰忛厤缃?            "dimensional_creative": {
                "enabled": False,
                "creative_intensity": 0.7,  # 闄嶄綆榛樿寮哄害
                "preserve_core_info": True,
                "allow_experimental": False,
                "auto_dimension_selection": True,
                "selected_dimensions": [],
                "priority_categories": ["audience", "format", "emotion", "theme"],  # 閲嶆柊鎺掑簭
                "max_dimensions": 3,  # 闄嶄綆鏈€澶х淮搴︽暟
                "compatibility_threshold": 0.7,  # 鎻愰珮鍏煎鎬ц姹?                "available_categories": [
                    "style",  # 鏂囦綋椋庢牸
                    "culture",  # 鏂囧寲瑙嗚
                    "time",  # 鏃剁┖鑳屾櫙
                    "personality",  # 浜烘牸瑙掕壊
                    "emotion",  # 鎯呮劅璋冩€?                    "format",  # 琛ㄨ揪鏍煎紡
                    "scene",  # 鍦烘櫙鐜
                    "audience",  # 鐩爣鍙椾紬
                    "theme",  # 涓婚鍐呭
                    "technique",  # 琛ㄧ幇鎶€娉?                    "language",  # 璇█椋庢牸
                    "tone",  # 璇皟璇皵
                    "perspective",  # 鍙欒堪瑙嗚
                    "structure",  # 鏂囩珷缁撴瀯
                    "rhythm",  # 鑺傚闊靛緥
                ],
                # 榛樿涓嶅惎鐢ㄤ换浣曠淮搴?                "enabled_dimensions": {
                    "style": False,
                    "culture": False,
                    "time": False,
                    "personality": False,
                    "emotion": False,
                    "format": False,
                    "scene": False,
                    "audience": False,
                    "theme": False,
                    "technique": False,
                    "language": False,
                    "tone": False,
                    "perspective": False,
                    "structure": False,
                    "rhythm": False,
                },
                "dimension_options": {
                    "style": {
                        "name": "鏂囦綋椋庢牸",
                        "allow_custom": True,
                        "selected_option": "",
                        "custom_input": "",
                        "preset_options": [
                            {
                                "name": "poetry",
                                "value": "璇楁瓕",
                                "weight": 1.0,
                                "description": "闊靛緥浼樼編锛屾剰澧冩繁杩?,
                            },
                            {
                                "name": "prose",
                                "value": "鏁ｆ枃",
                                "weight": 1.0,
                                "description": "褰㈡暎绁炶仛锛屾儏鎰熺湡鎸?,
                            },
                            {
                                "name": "novel",
                                "value": "灏忚",
                                "weight": 1.0,
                                "description": "鎯呰妭涓板瘜锛屼汉鐗╅矞鏄?,
                            },
                            {
                                "name": "essay",
                                "value": "璁鏂?,
                                "weight": 1.0,
                                "description": "瑙傜偣鏄庣‘锛岃璇佷弗瀵?,
                            },
                            {
                                "name": "narrative",
                                "value": "鍙欎簨鏂?,
                                "weight": 1.0,
                                "description": "鏁呬簨鎬у己锛屽紩浜哄叆鑳?,
                            },
                            {
                                "name": "expository",
                                "value": "璇存槑鏂?,
                                "weight": 1.0,
                                "description": "鏉＄悊娓呮櫚锛岃В閲婅灏?,
                            },
                            {
                                "name": "academic",
                                "value": "瀛︽湳璁烘枃",
                                "weight": 1.0,
                                "description": "涓ヨ皑瑙勮寖锛岄€昏緫娓呮櫚",
                            },
                            {
                                "name": "news",
                                "value": "鏂伴椈鎶ラ亾",
                                "weight": 1.0,
                                "description": "瀹㈣鐪熷疄锛屾椂鏁堟€у己",
                            },
                            {
                                "name": "children",
                                "value": "鍎跨鏂囧",
                                "weight": 1.0,
                                "description": "澶╃湡鐑傛极锛屽瘬鏁欎簬涔?,
                            },
                            {
                                "name": "fantasy",
                                "value": "濂囧够鏂囧",
                                "weight": 1.0,
                                "description": "鎯宠薄涓板瘜锛岄瓟骞昏壊褰?,
                            },
                        ],
                    },
                    "culture": {
                        "name": "鏂囧寲瑙嗚",
                        "allow_custom": True,
                        "selected_option": "",
                        "custom_input": "",
                        "preset_options": [
                            {
                                "name": "eastern_philosophy",
                                "value": "涓滄柟鍝插",
                                "weight": 1.0,
                                "description": "閬撳鎬濇兂锛岀瀹楁櫤鎱?,
                            },
                            {
                                "name": "western_logic",
                                "value": "瑗挎柟鎬濊鲸",
                                "weight": 1.0,
                                "description": "鐞嗘€у垎鏋愶紝閫昏緫涓ュ瘑",
                            },
                            {
                                "name": "japanese_mono",
                                "value": "鏃ュ紡鐗╁搥",
                                "weight": 1.0,
                                "description": "鐬棿缇庡锛屾贰娣″搥鎰?,
                            },
                            {
                                "name": "french_romance",
                                "value": "娉曞紡娴极",
                                "weight": 1.0,
                                "description": "浼橀泤鎯呰皟锛岃壓鏈皵鎭?,
                            },
                            {
                                "name": "american_freedom",
                                "value": "缇庡紡鑷敱",
                                "weight": 1.0,
                                "description": "涓汉涓讳箟锛岃拷姹傝嚜鐢?,
                            },
                            {
                                "name": "chinese_tradition",
                                "value": "涓崕浼犵粺",
                                "weight": 1.0,
                                "description": "鍎掑鏂囧寲锛岀ぜ浠箣閭?,
                            },
                            {
                                "name": "european_classical",
                                "value": "娆ф床鍙ゅ吀",
                                "weight": 1.0,
                                "description": "鏂囪壓澶嶅叴锛屽彜鍏歌壓鏈?,
                            },
                            {
                                "name": "latin_american",
                                "value": "鎷夌編椋庢儏",
                                "weight": 1.0,
                                "description": "鐑儏濂旀斁锛岄瓟骞荤幇瀹?,
                            },
                            {
                                "name": "african_tribal",
                                "value": "闈炴床閮ㄨ惤",
                                "weight": 1.0,
                                "description": "鍘熷鍔涢噺锛屽浘鑵惧磭鎷?,
                            },
                            {
                                "name": "middle_eastern",
                                "value": "涓笢绁炵",
                                "weight": 1.0,
                                "description": "娌欐紶鏂囨槑锛屽畻鏁欒壊褰?,
                            },
                        ],
                    },
                    "time": {
                        "name": "鏃剁┖鑳屾櫙",
                        "allow_custom": True,
                        "selected_option": "",
                        "custom_input": "",
                        "preset_options": [
                            {
                                "name": "ancient_china",
                                "value": "鏄ョ鎴樺浗",
                                "weight": 1.0,
                                "description": "绀煎穿涔愬潖锛岀櫨瀹朵簤楦?,
                            },
                            {
                                "name": "tang_song",
                                "value": "鍞愬畫鐩涗笘",
                                "weight": 1.0,
                                "description": "鏂囧寲绻佽崳锛岃瘲璇嶉紟鐩?,
                            },
                            {
                                "name": "republic",
                                "value": "姘戝浗椋庝簯",
                                "weight": 1.0,
                                "description": "鏂版棫浜ゆ浛锛岄璧蜂簯娑?,
                            },
                            {
                                "name": "eighties",
                                "value": "80骞翠唬",
                                "weight": 1.0,
                                "description": "鏀归潻寮€鏀撅紝闈掓槬鐑",
                            },
                            {
                                "name": "cyberpunk",
                                "value": "璧涘崥鏈嬪厠2077",
                                "weight": 1.0,
                                "description": "绉戞妧鏈潵锛岄湏铏瑰弽涔屾墭閭?,
                            },
                            {
                                "name": "medieval",
                                "value": "涓笘绾?,
                                "weight": 1.0,
                                "description": "楠戝＋绮剧锛岀绉樹富涔?,
                            },
                            {
                                "name": "prehistoric",
                                "value": "鍙插墠鏃朵唬",
                                "weight": 1.0,
                                "description": "鍘熷绀句細锛屾椽鑽掍箣鍔?,
                            },
                            {
                                "name": "space_age",
                                "value": "澶┖绾厓",
                                "weight": 1.0,
                                "description": "鏄熼檯鏃呰锛屽畤瀹欐帰绱?,
                            },
                            {
                                "name": "victorian",
                                "value": "缁村鍒╀簹鏃朵唬",
                                "weight": 1.0,
                                "description": "宸ヤ笟闈╁懡锛岀ぞ浼氬彉闈?,
                            },
                            {
                                "name": "renaissance",
                                "value": "鏂囪壓澶嶅叴",
                                "weight": 1.0,
                                "description": "浜烘枃涓讳箟锛岃壓鏈鍏?,
                            },
                        ],
                    },
                    "personality": {
                        "name": "浜烘牸瑙掕壊",
                        "allow_custom": True,
                        "selected_option": "",
                        "custom_input": "",
                        "preset_options": [
                            {
                                "name": "libai",
                                "value": "鏉庣櫧",
                                "weight": 1.0,
                                "description": "娴极涓讳箟璇椾汉锛岃豹鏀句笉缇?,
                            },
                            {
                                "name": "luxun",
                                "value": "椴佽繀",
                                "weight": 1.0,
                                "description": "鐜颁唬鏂囧瀹讹紝娣卞埢鎵瑰垽",
                            },
                            {
                                "name": "confucius",
                                "value": "瀛斿瓙",
                                "weight": 1.0,
                                "description": "鎬濇兂瀹讹紝浠佺埍涔嬮亾",
                            },
                            {
                                "name": "dreamer_poet",
                                "value": "姊﹀璇椾汉",
                                "weight": 1.0,
                                "description": "鍠勪簬灏嗙幇瀹炰笌姊﹀浜ょ粐",
                            },
                            {
                                "name": "data_philosopher",
                                "value": "鏁版嵁鍝插瀹?,
                                "weight": 1.0,
                                "description": "鐢ㄦ暟鎹€濈淮瑙ｈ浜烘枃",
                            },
                            {
                                "name": "time_traveler",
                                "value": "鏃剁┖鏃呰€?,
                                "weight": 1.0,
                                "description": "绌挎鏃朵唬锛岀嫭鐗硅瑙?,
                            },
                            {
                                "name": "emotion_healer",
                                "value": "鎯呮劅娌绘剤甯?,
                                "weight": 1.0,
                                "description": "娓╂殩浜哄績锛屾姎鎱板績鐏?,
                            },
                            {
                                "name": "mystery_detective",
                                "value": "鎮枒渚︽帰",
                                "weight": 1.0,
                                "description": "閫昏緫鎺ㄧ悊锛屾彮绉樼湡鐩?,
                            },
                            {
                                "name": "innovator",
                                "value": "鍒涙柊鍏堥攱",
                                "weight": 1.0,
                                "description": "鍕囦簬鎺㈢储锛岀獊鐮翠紶缁?,
                            },
                            {
                                "name": "storyteller",
                                "value": "鏁呬簨澶х帇",
                                "weight": 1.0,
                                "description": "鐢熷姩鍙欒堪锛屽紩浜哄叆鑳?,
                            },
                            {
                                "name": "scientist",
                                "value": "绉戝瀹?,
                                "weight": 1.0,
                                "description": "鐞嗘€т弗璋紝鎺㈢储鐪熺悊",
                            },
                            {
                                "name": "artist",
                                "value": "鑹烘湳瀹?,
                                "weight": 1.0,
                                "description": "鎰熸€у垱閫狅紝缇庡杩芥眰",
                            },
                        ],
                    },
                    "emotion": {
                        "name": "鎯呮劅璋冩€?,
                        "allow_custom": True,
                        "selected_option": "",
                        "custom_input": "",
                        "preset_options": [
                            {
                                "name": "healing",
                                "value": "娌绘剤绯?,
                                "weight": 1.0,
                                "description": "娓╂殩浜哄績锛屾姎鎱板績鐏?,
                            },
                            {
                                "name": "suspense",
                                "value": "鎮枒鎯婃倸",
                                "weight": 1.0,
                                "description": "绱у紶鍒烘縺锛屾墸浜哄績寮?,
                            },
                            {
                                "name": "inspiring",
                                "value": "鐑鍔卞織",
                                "weight": 1.0,
                                "description": "婵€鎯呮編婀冿紝姝ｈ兘閲忔弧婊?,
                            },
                            {
                                "name": "philosophical",
                                "value": "娣卞害鍝叉€?,
                                "weight": 1.0,
                                "description": "鎬濊鲸娣卞埢锛屽惎鍙戞櫤鎱?,
                            },
                            {
                                "name": "humorous",
                                "value": "骞介粯璇欒皭",
                                "weight": 1.0,
                                "description": "杞绘澗鎰夊揩锛屽瓒ｆí鐢?,
                            },
                            {
                                "name": "melancholy",
                                "value": "蹇ч儊鎬€鏃?,
                                "weight": 1.0,
                                "description": "娣℃贰蹇т激锛屽洖蹇嗗娼?,
                            },
                            {
                                "name": "romantic",
                                "value": "娴极鐖辨儏",
                                "weight": 1.0,
                                "description": "鐢滆湝娓╅Θ锛屾儏鎰忕坏缁?,
                            },
                            {
                                "name": "mysterious",
                                "value": "绁炵鑾祴",
                                "weight": 1.0,
                                "description": "鎵戞湐杩风锛屽紩浜洪亹鎯?,
                            },
                            {
                                "name": "tragic",
                                "value": "鎮插墽鑹插僵",
                                "weight": 1.0,
                                "description": "鎮插．娣辨矇锛屽懡杩愭姉浜?,
                            },
                            {
                                "name": "epic",
                                "value": "鍙茶瘲姘旀",
                                "weight": 1.0,
                                "description": "瀹忓ぇ鍙欎簨锛岃嫳闆勪紶濂?,
                            },
                        ],
                    },
                    "format": {
                        "name": "琛ㄨ揪鏍煎紡",
                        "allow_custom": True,
                        "selected_option": "",
                        "custom_input": "",
                        "preset_options": [
                            {
                                "name": "diary",
                                "value": "鏃ヨ浣?,
                                "weight": 1.0,
                                "description": "绉佸瘑鐪熷疄锛屾儏鎰熸祦闇?,
                            },
                            {
                                "name": "dialogue",
                                "value": "瀵硅瘽浣?,
                                "weight": 1.0,
                                "description": "鐢熷姩娲绘臣锛屼簰鍔ㄦ€у己",
                            },
                            {
                                "name": "poetry",
                                "value": "璇楁瓕鏁ｆ枃",
                                "weight": 1.0,
                                "description": "闊靛緥浼樼編锛屾剰澧冩繁杩?,
                            },
                            {
                                "name": "script",
                                "value": "鍓ф湰褰㈠紡",
                                "weight": 1.0,
                                "description": "鎴忓墽鍐茬獊锛岀敾闈㈡劅寮?,
                            },
                            {
                                "name": "letter",
                                "value": "涔︿俊浣?,
                                "weight": 1.0,
                                "description": "鎯呯湡鎰忓垏锛屾椂鍏夌┛瓒?,
                            },
                            {
                                "name": "interview",
                                "value": "璁胯皥褰?,
                                "weight": 1.0,
                                "description": "闂瓟浜掑姩锛岀湡瀹炶嚜鐒?,
                            },
                            {
                                "name": "report",
                                "value": "璋冩煡鎶ュ憡",
                                "weight": 1.0,
                                "description": "鏁版嵁鏀拺锛屽瑙傚垎鏋?,
                            },
                            {
                                "name": "fable",
                                "value": "瀵撹█鏁呬簨",
                                "weight": 1.0,
                                "description": "瀵撴剰娣卞埢锛屽惎鍙戞€濊€?,
                            },
                            {
                                "name": "essay",
                                "value": "闅忕瑪鏉傝皥",
                                "weight": 1.0,
                                "description": "鑷敱鐏垫椿锛岃瑙ｇ嫭鐗?,
                            },
                            {
                                "name": "manual",
                                "value": "鎿嶄綔鎵嬪唽",
                                "weight": 1.0,
                                "description": "姝ラ娓呮櫚锛屽疄鐢ㄦ寚瀵?,
                            },
                        ],
                    },
                    "scene": {
                        "name": "鍦烘櫙鐜",
                        "allow_custom": True,
                        "selected_option": "",
                        "custom_input": "",
                        "preset_options": [
                            {
                                "name": "coffee_shop",
                                "value": "鍜栧暋棣?,
                                "weight": 1.0,
                                "description": "娓╅Θ鎯剰锛岄兘甯傛儏璋?,
                            },
                            {
                                "name": "midnight_subway",
                                "value": "娣卞鍦伴搧",
                                "weight": 1.0,
                                "description": "瀛ょ嫭鎬濊€冿紝鍩庡競澶滆壊",
                            },
                            {
                                "name": "rainy_bookstore",
                                "value": "闆ㄥ涔﹀簵",
                                "weight": 1.0,
                                "description": "鏂囪壓娴极锛岀煡璇嗘鍫?,
                            },
                            {
                                "name": "seaside_cabin",
                                "value": "娴疯竟灏忓眿",
                                "weight": 1.0,
                                "description": "鑷劧瀹侀潤锛屽績鐏垫爾鎭?,
                            },
                            {
                                "name": "bustling_city",
                                "value": "绻佸崕閮藉競",
                                "weight": 1.0,
                                "description": "鑺傚蹇€燂紝鏈洪亣鎸戞垬",
                            },
                            {
                                "name": "mountain_temple",
                                "value": "灞变腑鍙ゅ",
                                "weight": 1.0,
                                "description": "娓呭菇瀹侀潤锛岀鎰忔繁杩?,
                            },
                            {
                                "name": "university_campus",
                                "value": "澶у鏍″洯",
                                "weight": 1.0,
                                "description": "闈掓槬娲嬫孩锛屾眰鐭ユ皼鍥?,
                            },
                            {
                                "name": "futuristic_city",
                                "value": "鏈潵閮藉競",
                                "weight": 1.0,
                                "description": "绉戞妧鎰熷己锛岃秴鐜板疄",
                            },
                            {
                                "name": "forest",
                                "value": "绁炵妫灄",
                                "weight": 1.0,
                                "description": "鍘熷鑷劧锛屾帰闄╁閬?,
                            },
                            {
                                "name": "library",
                                "value": "鍙よ€佸浘涔﹂",
                                "weight": 1.0,
                                "description": "鐭ヨ瘑娴锋磱锛屾櫤鎱ф鍫?,
                            },
                        ],
                    },
                    "audience": {
                        "name": "鐩爣鍙椾紬",
                        "allow_custom": True,
                        "selected_option": "",
                        "custom_input": "",
                        "preset_options": [
                            {
                                "name": "gen_z",
                                "value": "Z涓栦唬",
                                "weight": 1.0,
                                "description": "骞磋交鏃跺皻锛岀綉缁滃師鐢?,
                            },
                            {
                                "name": "professionals",
                                "value": "鑱屽満绮捐嫳",
                                "weight": 1.0,
                                "description": "鐞嗘€у姟瀹烇紝鏁堢巼瀵煎悜",
                            },
                            {
                                "name": "seniors",
                                "value": "閾跺彂鏃?,
                                "weight": 1.0,
                                "description": "闃呭巻涓板瘜锛屾儏鎰熺粏鑵?,
                            },
                            {
                                "name": "students",
                                "value": "瀛︾敓鍏?,
                                "weight": 1.0,
                                "description": "闈掓槬娲诲姏锛屾眰鐭ユ寮?,
                            },
                            {
                                "name": "parents",
                                "value": "瀹濆缇や綋",
                                "weight": 1.0,
                                "description": "鍏崇埍瀹跺涵锛屽疄鐢ㄨ创蹇?,
                            },
                            {
                                "name": "entrepreneurs",
                                "value": "鍒涗笟鑰?,
                                "weight": 1.0,
                                "description": "鍐掗櫓绮剧锛屽垱鏂版剰璇?,
                            },
                            {
                                "name": "tech_workers",
                                "value": "鎶€鏈汉鍛?,
                                "weight": 1.0,
                                "description": "閫昏緫鎬濈淮锛岃拷姹傛晥鐜?,
                            },
                            {
                                "name": "artists",
                                "value": "鏂囪壓闈掑勾",
                                "weight": 1.0,
                                "description": "瀹＄編鐙壒锛屾儏鎰熶赴瀵?,
                            },
                            {
                                "name": "retirees",
                                "value": "閫€浼戜汉鍛?,
                                "weight": 1.0,
                                "description": "闂叉殗鏃跺厜锛岀敓娲绘劅鎮?,
                            },
                            {
                                "name": "travelers",
                                "value": "鏃呰鐖卞ソ鑰?,
                                "weight": 1.0,
                                "description": "鎺㈢储涓栫晫锛屼綋楠屼赴瀵?,
                            },
                        ],
                    },
                    "theme": {
                        "name": "涓婚鍐呭",
                        "allow_custom": True,
                        "selected_option": "",
                        "custom_input": "",
                        "preset_options": [
                            {
                                "name": "growth",
                                "value": "鎴愰暱铚曞彉",
                                "weight": 1.0,
                                "description": "闈掓槬鎴愰暱锛岃嚜鎴戝彂鐜?,
                            },
                            {
                                "name": "time_healing",
                                "value": "鏃堕棿娌绘剤",
                                "weight": 1.0,
                                "description": "宀佹湀濡傛瓕锛屼激鐥涙剤鍚?,
                            },
                            {
                                "name": "dream_pursuit",
                                "value": "姊︽兂杩藉",
                                "weight": 1.0,
                                "description": "鐞嗘兂涓讳箟锛屼笉鎳堝鏂?,
                            },
                            {
                                "name": "human_nature",
                                "value": "浜烘€ф帰绱?,
                                "weight": 1.0,
                                "description": "蹇冪悊娣卞害锛岄亾寰锋€濊鲸",
                            },
                            {
                                "name": "tech_reflection",
                                "value": "绉戞妧鍙嶆€?,
                                "weight": 1.0,
                                "description": "鎶€鏈繘姝ワ紝浜烘枃鍏虫€€",
                            },
                            {
                                "name": "environmental",
                                "value": "鐜繚鐞嗗康",
                                "weight": 1.0,
                                "description": "缁胯壊鐢熸€侊紝鍙寔缁彂灞?,
                            },
                            {
                                "name": "social_justice",
                                "value": "绀句細鍏",
                                "weight": 1.0,
                                "description": "鍏钩姝ｄ箟锛岀ぞ浼氳矗浠?,
                            },
                            {
                                "name": "cultural_heritage",
                                "value": "鏂囧寲浼犳壙",
                                "weight": 1.0,
                                "description": "浼犵粺寤剁画锛屾枃鍖栦繚鎶?,
                            },
                            {
                                "name": "love",
                                "value": "鐖辨儏鏁呬簨",
                                "weight": 1.0,
                                "description": "鎯呮劅绾犺憶锛屽績鐏靛叡楦?,
                            },
                            {
                                "name": "adventure",
                                "value": "鍐掗櫓鍘嗙▼",
                                "weight": 1.0,
                                "description": "鎸戞垬鏋侀檺锛屽媷寰€鐩村墠",
                            },
                        ],
                    },
                    "technique": {
                        "name": "琛ㄧ幇鎶€娉?,
                        "allow_custom": True,
                        "selected_option": "",
                        "custom_input": "",
                        "preset_options": [
                            {
                                "name": "first_person",
                                "value": "绗竴浜虹О",
                                "weight": 1.0,
                                "description": "浜茶韩浣撻獙锛屾儏鎰熺洿鎺?,
                            },
                            {
                                "name": "omniscient",
                                "value": "鍏ㄧ煡瑙嗚",
                                "weight": 1.0,
                                "description": "涓婂笣瑙嗚锛屾礊瀵熷叏灞€",
                            },
                            {
                                "name": "multiple",
                                "value": "澶氶噸鍙欒堪",
                                "weight": 1.0,
                                "description": "澶氳搴﹀睍鐜帮紝澶嶆潅绔嬩綋",
                            },
                            {
                                "name": "stream",
                                "value": "鎰忚瘑娴?,
                                "weight": 1.0,
                                "description": "鍐呭績鐙櫧锛屾€濈淮璺宠穬",
                            },
                            {
                                "name": "flashback",
                                "value": "鍊掑彊",
                                "weight": 1.0,
                                "description": "鏃剁┖浜ら敊锛屾偓蹇甸噸鐢?,
                            },
                            {
                                "name": "montage",
                                "value": "钂欏お濂?,
                                "weight": 1.0,
                                "description": "鐢婚潰鎷兼帴锛屾椂绌哄帇缂?,
                            },
                            {
                                "name": "symbolism",
                                "value": "璞″緛涓讳箟",
                                "weight": 1.0,
                                "description": "瀵撴剰娣卞埢锛屽惈钃勮〃杈?,
                            },
                            {
                                "name": "satire",
                                "value": "璁藉埡鎵嬫硶",
                                "weight": 1.0,
                                "description": "骞介粯鎵瑰垽锛岃緵杈ｈ鍒?,
                            },
                            {
                                "name": "metaphor",
                                "value": "闅愬柣璞″緛",
                                "weight": 1.0,
                                "description": "姣斿柣鏆楃ず锛屾剰鍛虫繁闀?,
                            },
                            {
                                "name": "contrast",
                                "value": "瀵规瘮鍙嶈‖",
                                "weight": 1.0,
                                "description": "椴滄槑瀵圭収锛岀獊鍑轰富棰?,
                            },
                        ],
                    },
                    "language": {
                        "name": "璇█椋庢牸",
                        "allow_custom": True,
                        "selected_option": "",
                        "custom_input": "",
                        "preset_options": [
                            {
                                "name": "classical",
                                "value": "鍙ゅ吀闆呰嚧",
                                "weight": 1.0,
                                "description": "鏂囪█闊靛懗锛屽吀闆呭簞閲?,
                            },
                            {
                                "name": "modern",
                                "value": "鐜颁唬鐧借瘽",
                                "weight": 1.0,
                                "description": "閫氫織鏄撴噦锛岃创杩戠敓娲?,
                            },
                            {
                                "name": "vernacular",
                                "value": "鏂硅█鍦熻",
                                "weight": 1.0,
                                "description": "鍦板煙鐗硅壊锛岀敓鍔ㄤ翰鍒?,
                            },
                            {
                                "name": "foreign",
                                "value": "澶栬娣锋潅",
                                "weight": 1.0,
                                "description": "澶氳铻嶅悎锛屽浗闄呰寖鍎?,
                            },
                            {
                                "name": "technical",
                                "value": "涓撲笟鏈",
                                "weight": 1.0,
                                "description": "琛屼笟璇嶆眹锛岀簿鍑嗚〃杈?,
                            },
                            {
                                "name": "slang",
                                "value": "缃戠粶娴佽",
                                "weight": 1.0,
                                "description": "娼祦鐢ㄨ锛屽勾杞绘椂灏?,
                            },
                            {
                                "name": "poetic",
                                "value": "璇楁剰璇█",
                                "weight": 1.0,
                                "description": "闊靛緥浼樼編锛屾剰澧冩繁杩?,
                            },
                            {
                                "name": "plain",
                                "value": "鏈寸礌骞冲疄",
                                "weight": 1.0,
                                "description": "绠€娲佹槑浜嗭紝鏈村疄鏃犲崕",
                            },
                        ],
                    },
                    "tone": {
                        "name": "璇皟璇皵",
                        "allow_custom": True,
                        "selected_option": "",
                        "custom_input": "",
                        "preset_options": [
                            {
                                "name": "serious",
                                "value": "涓ヨ們搴勯噸",
                                "weight": 1.0,
                                "description": "閮戦噸鍏朵簨锛屼笉瀹圭疆鐤?,
                            },
                            {
                                "name": "casual",
                                "value": "杞绘澗闅忔剰",
                                "weight": 1.0,
                                "description": "鑷劧浜插垏锛屼笉鎷樹竴鏍?,
                            },
                            {
                                "name": "sarcastic",
                                "value": "璁藉埡鎸栬嫤",
                                "weight": 1.0,
                                "description": "鍙嶈璁ヨ锛岃緵杈ｇ妧鍒?,
                            },
                            {
                                "name": "enthusiastic",
                                "value": "鐑儏娲嬫孩",
                                "weight": 1.0,
                                "description": "婵€鎯呮編婀冿紝鎰熸煋鍔涘己",
                            },
                            {
                                "name": "calm",
                                "value": "骞抽潤娓╁拰",
                                "weight": 1.0,
                                "description": "蹇冨钩姘斿拰锛屽〒濞撻亾鏉?,
                            },
                            {
                                "name": "urgent",
                                "value": "鎬ュ垏绱ц揩",
                                "weight": 1.0,
                                "description": "杩湪鐪夌潾锛屽埢涓嶅缂?,
                            },
                            {
                                "name": "mysterious",
                                "value": "绁炵鑾祴",
                                "weight": 1.0,
                                "description": "鎵戞湐杩风锛屽紩浜哄叆鑳?,
                            },
                            {
                                "name": "humorous",
                                "value": "骞介粯璇欒皭",
                                "weight": 1.0,
                                "description": "濡欒叮妯敓锛屼护浜哄彂绗?,
                            },
                        ],
                    },
                    "perspective": {
                        "name": "鍙欒堪瑙嗚",
                        "allow_custom": True,
                        "selected_option": "",
                        "custom_input": "",
                        "preset_options": [
                            {
                                "name": "first_person",
                                "value": "绗竴浜虹О",
                                "weight": 1.0,
                                "description": "浠ユ垜涓轰富锛屼翰韬粡鍘?,
                            },
                            {
                                "name": "second_person",
                                "value": "绗簩浜虹О",
                                "weight": 1.0,
                                "description": "鐩存帴瀵硅瘽锛岃韩涓村叾澧?,
                            },
                            {
                                "name": "third_person_limited",
                                "value": "绗笁浜虹О鏈夐檺",
                                "weight": 1.0,
                                "description": "鑱氱劍涓昏锛屾繁鍏ュ唴蹇?,
                            },
                            {
                                "name": "third_person_omniscient",
                                "value": "绗笁浜虹О鍏ㄧ煡",
                                "weight": 1.0,
                                "description": "鍏ㄧ煡鍏ㄨ兘锛屾礊瀵熶竴鍒?,
                            },
                            {
                                "name": "multiple_pov",
                                "value": "澶氳瑙掑垏鎹?,
                                "weight": 1.0,
                                "description": "涓嶅悓浜虹墿锛屼笉鍚岃瑙?,
                            },
                            {
                                "name": "observer",
                                "value": "鏃佽鑰呰瑙?,
                                "weight": 1.0,
                                "description": "瀹㈣璁板綍锛屽喎鐪兼梺瑙?,
                            },
                            {
                                "name": "participant",
                                "value": "鍙備笌鑰呰瑙?,
                                "weight": 1.0,
                                "description": "韬湪鍏朵腑锛屼富瑙傛劅鍙?,
                            },
                        ],
                    },
                    "structure": {
                        "name": "鏂囩珷缁撴瀯",
                        "allow_custom": True,
                        "selected_option": "",
                        "custom_input": "",
                        "preset_options": [
                            {
                                "name": "chronological",
                                "value": "鏃堕棿椤哄簭",
                                "weight": 1.0,
                                "description": "鎸夋椂闂村彂灞曪紝鑴夌粶娓呮櫚",
                            },
                            {
                                "name": "spatial",
                                "value": "绌洪棿椤哄簭",
                                "weight": 1.0,
                                "description": "鎸夌┖闂翠綅缃紝灞傛鍒嗘槑",
                            },
                            {
                                "name": "thematic",
                                "value": "涓婚鍒嗙被",
                                "weight": 1.0,
                                "description": "鎸変富棰樺垝鍒嗭紝閫昏緫涓ュ瘑",
                            },
                            {
                                "name": "problem_solution",
                                "value": "闂瑙ｅ喅",
                                "weight": 1.0,
                                "description": "鎻愬嚭闂锛屽垎鏋愯В鍐?,
                            },
                            {
                                "name": "cause_effect",
                                "value": "鍥犳灉鍏崇郴",
                                "weight": 1.0,
                                "description": "鍒嗘瀽鍘熷洜锛屾帰璁ㄧ粨鏋?,
                            },
                            {
                                "name": "compare_contrast",
                                "value": "瀵规瘮瀵圭収",
                                "weight": 1.0,
                                "description": "姣旇緝寮傚悓锛岀獊鍑虹壒鐐?,
                            },
                            {
                                "name": "circular",
                                "value": "棣栧熬鍛煎簲",
                                "weight": 1.0,
                                "description": "寮€澶寸粨灏撅紝閬ョ浉鍛煎簲",
                            },
                            {
                                "name": "layered",
                                "value": "灞傚眰閫掕繘",
                                "weight": 1.0,
                                "description": "鐢辨祬鍏ユ繁锛岄€愭娣卞叆",
                            },
                        ],
                    },
                    "rhythm": {
                        "name": "鑺傚闊靛緥",
                        "allow_custom": True,
                        "selected_option": "",
                        "custom_input": "",
                        "preset_options": [
                            {
                                "name": "fast",
                                "value": "蹇妭濂?,
                                "weight": 1.0,
                                "description": "绱у噾婵€鐑堬紝鎵ｄ汉蹇冨鸡",
                            },
                            {
                                "name": "slow",
                                "value": "鎱㈣妭濂?,
                                "weight": 1.0,
                                "description": "鑸掔紦鎮犳壃锛屽〒濞撻亾鏉?,
                            },
                            {
                                "name": "variable",
                                "value": "鍙樺寲澶氱",
                                "weight": 1.0,
                                "description": "寮犲紱鏈夊害锛岃捣浼忚穼瀹?,
                            },
                            {
                                "name": "steady",
                                "value": "骞崇ǔ鍧囧寑",
                                "weight": 1.0,
                                "description": "鑺傚涓€鑷达紝绋冲畾鎺ㄨ繘",
                            },
                            {
                                "name": "accelerating",
                                "value": "閫愭笎鍔犲揩",
                                "weight": 1.0,
                                "description": "灞傚眰鎺ㄨ繘锛岃秺鏉ヨ秺蹇?,
                            },
                            {
                                "name": "decelerating",
                                "value": "閫愭笎鏀剧紦",
                                "weight": 1.0,
                                "description": "娓愬叆浣冲锛屾參鎱㈠洖鍛?,
                            },
                            {
                                "name": "syncopated",
                                "value": "鍒囧垎鑺傚",
                                "weight": 1.0,
                                "description": "閿欒惤鏈夎嚧锛屽瘜鏈夊彉鍖?,
                            },
                        ],
                    },
                },  # 缁村害閫夐」閰嶇疆
            },
            # 椤甸潰璁捐閰嶇疆 - 榛樿涓嶅惎鐢?浣跨敤鍘熷HTML鏍峰紡
            "page_design": {
                "unified_brand_style": True,
                "use_original_styles": True,  # 榛樿true,涓嶅簲鐢ㄥ叏灞€鏍峰紡瑕嗙洊
                "container": {
                    "max_width": 750,
                    "margin_horizontal": 10,
                    "background_color": "#f8f9fa",
                },
                "card": {
                    "border_radius": 12,
                    "box_shadow": "0 4px 16px rgba(0,0,0,0.06)",
                    "padding": 24,
                    "background_color": "#ffffff",
                },
                "typography": {
                    "base_font_size": 16,
                    "line_height": 1.6,
                    "heading_scale": 1.5,
                    "text_color": "#333333",
                    "heading_color": "#333333",
                },
                "spacing": {"section_margin": 24, "element_margin": 16},
                "accent": {
                    "primary_color": "#3a7bd5",
                    "secondary_color": "#2563a8",
                    "highlight_bg": "#f0f7ff",
                },
            },
        }

        self.default_aiforge_config = {
            "locale": "zh",
            "max_rounds": 2,
            "max_tokens": 4096,
            "max_optimization_attempts": 3,
            "default_llm_provider": "openrouter",
            "llm": {
                "openrouter": {
                    "type": "openai",
                    "model": "deepseek/deepseek-chat-v3-0324:free",
                    "api_key": "",
                    "base_url": "https://openrouter.ai/api/v1",
                    "timeout": 60,
                    "max_tokens": 8192,
                },
                "grok": {
                    "type": "grok",
                    "model": "xai/grok-3",
                    "api_key": "",
                    "base_url": "https://api.x.ai/v1/",
                    "timeout": 60,
                    "max_tokens": 8192,
                },
                "qwen": {
                    "type": "openai",
                    "model": "qwen-plus",
                    "api_key": "",
                    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "timeout": 60,
                    "max_tokens": 8192,
                },
                "gemini": {
                    "type": "gemini",
                    "model": "gemini/gemini-2.5-flash",
                    "api_key": "",
                    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
                    "timeout": 60,
                    "max_tokens": 8192,
                },
                "ollama": {
                    "type": "ollama",
                    "model": "llama3",
                    "api_key": "",
                    "base_url": "http://localhost:11434",
                    "timeout": 60,
                    "max_tokens": 8192,
                },
                "deepseek": {
                    "type": "deepseek",
                    "model": "deepseek-chat",
                    "api_key": "",
                    "base_url": "https://api.deepseek.com",
                    "timeout": 60,
                    "max_tokens": 8192,
                },
                "claude": {
                    "type": "claude",
                    "model": "claude-4-sonnet",
                    "api_key": "",
                    "base_url": "https://api.anthropic.com/v1",
                    "timeout": 60,
                    "max_tokens": 4096,
                },
                "cohere": {
                    "type": "cohere",
                    "model": "command-r-plus",
                    "api_key": "",
                    "base_url": "https://api.cohere.ai/v1",
                    "timeout": 60,
                    "max_tokens": 4096,
                },
                "mistral": {
                    "type": "mistral",
                    "model": "mistral-large-latest",
                    "api_key": "",
                    "base_url": "https://api.mistral.ai/v1",
                    "timeout": 60,
                    "max_tokens": 4096,
                },
            },
            "cache": {
                "code": {
                    "enabled": True,
                    "max_modules": 20,
                    "failure_threshold": 0.8,
                    "max_age_days": 30,
                    "cleanup_interval": 10,
                    "semantic_threshold": 0.6,
                    "enable_semantic_matching": True,
                    "use_lightweight_semantic": False,
                    "enable_action_clustering": True,
                    "action_cluster_threshold": 0.75,
                },
            },
            "optimization": {
                "enabled": False,
                "aggressive_minify": True,
                "max_feedback_length": 200,
                "obfuscate_variables": True,
            },
            "security": {
                "execution_timeout": 60,
                "memory_limit_mb": 512,
                "cpu_time_limit": 60,
                "file_descriptor_limit": 64,
                "max_file_size_mb": 100,
                "max_processes": 10,
                "file_access": {
                    "user_specified_paths": True,
                    "default_allowed_paths": ["./data", "./output"],
                    "require_explicit_permission": True,
                    "max_allowed_paths": 10,
                },
                "network": {
                    "policy": "unrestricted",
                    "max_requests_per_minute": 60,
                    "max_concurrent_connections": 10,
                    "request_timeout": 30,
                    "allowed_protocols": ["http", "https"],
                    "allowed_ports": [80, 443, 8080, 8443],
                    "blocked_ports": [22, 23, 3389, 5432, 3306],
                    "generated_code": {
                        "force_block_modules": False,
                        "force_block_access": False,
                    },
                    "domain_filtering": {
                        "enabled": True,
                        "whitelist": [
                            "api.openai.com",
                            "api.deepseek.com",
                            "openrouter.ai",
                            "baidu.com",
                            "bing.com",
                            "so.com",
                            "sogou.com",
                            "api.x.ai",
                            "dashscope.aliyuncs.com",
                            "generativelanguage.googleapis.com",
                        ],
                        "blacklist": ["malicious-site.com"],
                        "task_overrides": {
                            "data_fetch": {
                                "mode": "extended",
                                "additional_domains": [
                                    "sina.com.cn",
                                    "163.com",
                                    "qq.com",
                                    "sohu.com",
                                    "xinhuanet.com",
                                    "people.com.cn",
                                    "chinanews.com",
                                    "thepaper.cn",
                                    "36kr.com",
                                    "ifeng.com",
                                    "cnbeta.com",
                                    "zol.com.cn",
                                    "csdn.net",
                                    "jianshu.com",
                                    "zhihu.com",
                                    "weibo.com",
                                    "douban.com",
                                    "bilibili.com",
                                    "youku.com",
                                    "iqiyi.com",
                                    "tencent.com",
                                    "alibaba.com",
                                    "jd.com",
                                    "tmall.com",
                                    "taobao.com",
                                ],
                            },
                        },
                    },
                },
            },
            "extensions": {
                "enabled": True,
                "auto_load": True,
                "extension_dir": "extensions",
                "registered": [
                    {
                        "name": "custom_executor",
                        "type": "executor",
                        "config": {},
                    },
                    {
                        "name": "custom_data_processor",
                        "type": "executor",
                        "module_path": "my_plugins.data_processor",
                        "class_name": "CustomDataProcessor",
                        "priority": 1,
                    },
                    {
                        "name": "domain_specific_executor",
                        "type": "executor",
                        "config_file": "plugins/domain_executor.toml",
                    },
                ],
            },
        }
        # 鑷畾涔夎瘽棰樺拰鏂囩珷鍙傝€冮摼鎺ワ紝鏍规嵁鏄惁涓虹┖鍒ゆ柇鏄惁鑷畾涔?        self.custom_topic = ""  # 鑷畾涔夎瘽棰橈紙瀛楃涓诧級
        self.urls = []  # 鍙傝€冮摼鎺ワ紙鍒楄〃锛?        self.reference_ratio = 0.0  # 鏂囩珷鍊熼壌姣斾緥[0-1]
        self.custom_template_category = ""  # 鑷畾涔夎瘽棰樻椂锛屾ā鏉垮垎绫?        self.custom_template = ""  # 鑷畾涔夎瘽棰樻椂锛屾ā鏉?
        self._license_edition = "basic"  # 榛樿鍩虹鐗?        self._license_custom_features = []

    @property
    def license_edition(self):
        """鑾峰彇鎺堟潈鐗堟湰绫诲瀷"""
        with self._lock:
            return getattr(self, "_license_edition", "basic")

    @property
    def license_custom_features(self):
        """鑾峰彇瀹氬埗鐗堝姛鑳藉垪琛?""
        with self._lock:
            return getattr(self, "_license_custom_features", [])

    def is_premium_or_higher(self):
        """鏄惁涓洪珮绾х増鎴栨洿楂樼増鏈?""
        return self.license_edition in ["premium", "custom"]

    def has_custom_feature(self, feature_name):
        """妫€鏌ユ槸鍚︽湁鐗瑰畾鐨勫畾鍒跺姛鑳?""
        return feature_name in self.license_custom_features

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @property
    def platforms(self):
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.config["platforms"]

    @property
    def wechat_credentials(self):
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.config["wechat"]["credentials"]

    def get_llm_model(self, config_key: str = "model", default: str = "") -> str:
        """
        鑾峰彇LLM妯″瀷鍚嶇О锛屽甫鏅鸿兘鍥為€€锛?        1. 浼樺厛浣跨敤褰撳墠鎻愪緵鍟嗛厤缃腑鎸囧畾鐨勮鑹茬储寮?(濡?designer_model_index)
        2. 濡傛灉瑙掕壊鏈缃垨绱㈠紩涓?-1锛屽垯鍥為€€鍒颁富妯″瀷 (model_index)
        3. 濡傛灉妯″瀷涓嶅湪鍙敤鍒楄〃涓紝杩涜妯＄硦鍖归厤鎴栦娇鐢ㄧ涓€涓彲鐢ㄦā鍨?        """
        with self._lock:
            api_config = self.config.get("api", {})
            api_type = api_config.get("api_type", "OpenRouter")
            provider_config = api_config.get(api_type, {})
            allowed_models = provider_config.get("model", [])

            # 1. 纭畾绱㈠紩閿槧灏?            index_key = f"{config_key}_index" if config_key != "model" else "model_index"
            model_index = int(provider_config.get(index_key, -1) or -1)

            # 濡傛灉鏄富妯″瀷璇锋眰锛屼笖娌℃湁 index锛岄粯璁や负 0
            if config_key == "model" and model_index == -1:
                model_index = int(provider_config.get("model_index", 0) or 0)

            # 2. 瑙ｆ瀽鐩爣妯″瀷鍚嶇О
            target_model = None
            if 0 <= model_index < len(allowed_models):
                target_model = allowed_models[model_index]

            # 3. 瑙掕壊妯″瀷鍥為€€閫昏緫锛氬鏋滄湭璁剧疆鎴栨棤鏁堬紝鍥為€€鍒颁富妯″瀷
            if not target_model and config_key != "model":
                return self.get_llm_model("model", default)

            # 4. 鍏滃簳瑙ｆ瀽锛堜粠鏍归厤缃幏鍙栵紝鍏煎鏃х増鏈垨纭紪鐮侊級
            if not target_model:
                target_model = api_config.get(config_key, default)

            # 5. 鍒楄〃鏍￠獙涓庢ā绯婂尮閰嶉€昏緫
            if not allowed_models:
                return target_model
            
            if target_model in allowed_models:
                return target_model
                
            # 妯＄硦鍖归厤
            for m in allowed_models:
                if target_model.lower() in m.lower():
                    return m
                    
            # 鏈€缁堜繚搴曪細浣跨敤褰撳墠鎻愪緵鍟嗙殑绗竴涓ā鍨?            return allowed_models[0] if allowed_models else target_model

    @property
    def api_type(self):
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.config["api"]["api_type"]

    @property
    def api_key_name(self):
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            api_type = self.config["api"]["api_type"]
            provider_config = self.config["api"][api_type]
            # 鑷畾涔堿PI鍙兘娌℃湁key瀛楁锛屼娇鐢ㄩ粯璁ゅ€?            return provider_config.get("key", "OPENAI_API_KEY")

    @property
    def api_key(self):
        """鑾峰彇褰撳墠閫変腑鐨?API Key (濡傛灉鏄 Key 瀛楃涓诧紝鍒欒В鏋愪负鍒楄〃鍚庡彇绱㈠紩)"""
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            
            api_type = self.config["api"]["api_type"]
            provider_config = self.config["api"][api_type]
            
            # 鑾峰彇鍘熷 key 鏁版嵁
            raw_key = provider_config.get("api_key", [])
            
            # 濡傛灉鏄垪琛ㄤ笖涓嶄负绌猴紝鍙栫储寮?            if isinstance(raw_key, list):
                if not raw_key: return ""
                key_index = int(provider_config.get("key_index", 0) or 0)
                if 0 <= key_index < len(raw_key):
                    return str(raw_key[key_index])
                return str(raw_key[0])
            
            # 濡傛灉鏄瓧绗︿覆锛屽皾璇曟寜鎹㈣绗﹀垎鍓诧紙澶?Key 鏀寔锛?            if isinstance(raw_key, str):
                keys = [k.strip() for k in raw_key.split('\n') if k.strip()]
                if not keys: return raw_key
                key_index = int(provider_config.get("key_index", 0) or 0)
                if 0 <= key_index < len(keys):
                    return keys[key_index]
                return keys[0]
                
            return str(raw_key)

    def get_api_keys(self, provider_type: str = None) -> list:
        """鑾峰彇鎸囧畾鎻愪緵鍟嗙殑鎵€鏈?API Keys 鍒楄〃"""
        with self._lock:
            if not self.config:
                return []
            
            target_type = provider_type or self.config["api"].get("api_type")
            if not target_type:
                return []
                
            provider_config = self.config["api"].get(target_type, {})
            raw_key = provider_config.get("api_key", [])
            
            if isinstance(raw_key, list):
                return [str(k) for k in raw_key if str(k).strip()]
            
            if isinstance(raw_key, str):
                return [k.strip() for k in raw_key.split('\n') if k.strip()]
                
            return [str(raw_key)] if raw_key else []

    @property
    def api_model(self):
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            model = self.config["api"][self.config["api"]["api_type"]]["model"]
            model_index = int(self.config["api"][self.config["api"]["api_type"]].get("model_index", 0) or 0)
            return model[model_index]

    @property
    def api_fallback_model(self):
        """鑾峰彇褰撳墠API鍘傚晢閰嶇疆鐨勫鐢ㄦā鍨嬶紝鏈缃椂杩斿洖 None"""
        with self._lock:
            if not self.config:
                return None
            api_type = self.config["api"].get("api_type")
            if not api_type:
                return None
            provider_config = self.config["api"].get(api_type, {})
            fallback_index = int(provider_config.get("fallback_model_index", -1) or -1)
            if fallback_index < 0:
                return None
            models = provider_config.get("model", [])
            if 0 <= fallback_index < len(models):
                return models[fallback_index]
            return None

    @property
    def api_vision_model(self):
        """鑾峰彇褰撳墠API鍘傚晢閰嶇疆鐨勮瑙夋ā鍨?""
        with self._lock:
            if not self.config:
                return ""
            
            api_type = self.config["api"].get("api_type")
            if not api_type:
                return ""
                
            provider_config = self.config["api"].get(api_type, {})
            vision_models = provider_config.get("vision_model", [])
            vision_index = int(provider_config.get("vision_model_index", 0) or 0)

            if vision_models and 0 <= vision_index < len(vision_models):
                return vision_models[vision_index]
            return ""

    @property
    def api_apibase(self):
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.config["api"][self.config["api"]["api_type"]]["api_base"]

    @property
    def api_provider(self):
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.config["api"][self.config["api"]["api_type"]].get("provider", "")

    @property
    def img_api_type(self):
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.config["img_api"]["api_type"]

    @property
    def img_api_key(self):
        """鑾峰彇褰撳墠鍥剧墖 API Key (鏀寔澶?Key 杞)"""
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            
            img_api = self.config.get("img_api", {})
            if not isinstance(img_api, dict):
                return ""
                
            api_type = img_api.get("api_type", "picsum")
            provider_config = img_api.get(api_type, {})
            
            # 鐗规畩澶勭悊 custom 绫诲瀷
            if api_type == "custom":
                if isinstance(provider_config, list):
                    custom_index = int(img_api.get("custom_index", 0) or 0)
                    if 0 <= custom_index < len(provider_config):
                        target = provider_config[custom_index]
                        raw_key = target.get("api_key", "") if isinstance(target, dict) else str(target)
                        return self._parse_first_key(raw_key)
                    return ""
                elif isinstance(provider_config, dict):
                    return self._parse_first_key(provider_config.get("api_key", ""))
                return ""

            # 澶勭悊鍏朵粬绫诲瀷
            raw_key = ""
            if isinstance(provider_config, dict):
                raw_key = provider_config.get("api_key", "")
            elif isinstance(provider_config, list) and len(provider_config) > 0:
                first = provider_config[0]
                raw_key = first.get("api_key", "") if isinstance(first, dict) else str(first)
            
            return self._parse_first_key(raw_key)

    def get_img_api_keys(self, provider_type: str = None) -> list:
        """鑾峰彇鍥剧墖鐢熸垚 API 鐨勬墍鏈?Keys 鍒楄〃"""
        with self._lock:
            img_api = self.config.get("img_api", {})
            target_type = provider_type or img_api.get("api_type", "picsum")
            provider_config = img_api.get(target_type, {})
            
            raw_key = ""
            if target_type == "custom" and isinstance(provider_config, list):
                custom_index = int(img_api.get("custom_index", 0) or 0)
                if 0 <= custom_index < len(provider_config):
                    target = provider_config[custom_index]
                    raw_key = target.get("api_key", "") if isinstance(target, dict) else str(target)
            elif isinstance(provider_config, dict):
                raw_key = provider_config.get("api_key", "")
            
            if isinstance(raw_key, list):
                return [str(k) for k in raw_key if str(k).strip()]
            if isinstance(raw_key, str):
                return [k.strip() for k in raw_key.split('\n') if k.strip()]
            return [str(raw_key)] if raw_key else []

    def _parse_first_key(self, raw_key: Any) -> str:
        """瑙ｆ瀽澶?Key 瀛楃涓蹭腑鐨勭涓€涓彲鐢?Key"""
        if isinstance(raw_key, list):
            return str(raw_key[0]) if raw_key else ""
        if isinstance(raw_key, str):
            keys = [k.strip() for k in raw_key.split('\n') if k.strip()]
            return keys[0] if keys else raw_key
        return str(raw_key) if raw_key else ""

    @property
    def img_api_model(self):
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)

            img_api = self.config.get("img_api", {})
            if not isinstance(img_api, dict):
                return ""

            api_type = img_api.get("api_type", "picsum")
            provider_config = img_api.get(api_type, {})

            if api_type == "custom":
                if isinstance(provider_config, list):
                    custom_index = int(img_api.get("custom_index", 0) or 0)
                    if 0 <= custom_index < len(provider_config):
                        target = provider_config[custom_index]
                        return target.get("model", "") if isinstance(target, dict) else str(target)
                    return ""
                elif isinstance(provider_config, dict):
                    return provider_config.get("model", "")
                return ""

            if isinstance(provider_config, dict):
                return provider_config.get("model", "")
            elif isinstance(provider_config, list) and len(provider_config) > 0:
                first = provider_config[0]
                return first.get("model", "") if isinstance(first, dict) else str(first)
                
            return ""

    @property
    def img_runtime_settings(self):
        with self._lock:
            default_settings = {
                "default_timeout_seconds": 60,
                "fast_mode_timeout_seconds": 45,
                "article_image_count": 3,
                "fast_mode_prompt_count": 3,
                "fast_mode_prompt_excerpt_length": 120,
                "allow_placeholder_fallback": True,
            }
            if not self.config:
                return default_settings

            img_api = self.config.get("img_api", {})
            runtime_settings = img_api.get("settings", {}) if isinstance(img_api, dict) else {}
            if not isinstance(runtime_settings, dict):
                return default_settings

            merged = dict(default_settings)
            merged.update(runtime_settings)
            return merged

    @property
    def use_template(self):
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.config["use_template"]

    @property
    def use_dynamic_template(self):
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.config.get("use_dynamic_template", True)

    @property
    def template_category(self):
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.config["template_category"]

    @property
    def template(self):
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.config["template"]

    @property
    def use_compress(self):
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.config["use_compress"]

    @property
    def min_article_len(self):
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.config["min_article_len"]

    @property
    def max_article_len(self):
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.config["max_article_len"]

    @property
    def v15_config(self):
        """V15.0 閲忓瓙浼樺寲閰嶇疆"""
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.config.get("v15_quantum_optimization", {
                "enabled": True,
                "enable_smart_batching": True,
                "enable_semantic_cache": True,
                "enable_adaptive_routing": True,
                "cache_similarity_threshold": 0.88,
                "batch_window_ms": 50,
                "max_batch_size": 20,
            })

    @property
    def article_format(self):
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.config.get("article_format", "MARKDOWN")

    @property
    def auto_delete_published(self):
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.config.get("auto_delete_published", False)

    @property
    def auto_publish(self):
        """鏄惁鍚敤鑷姩鍙戝竷鍔熻兘 (V18 Fix)"""
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            # 鍏煎澶勭悊锛氫紭鍏堜粠鏍硅鍙栵紝鏃犲垯榛樿涓?False
            return self.config.get("auto_publish", False)

    @property
    def swarm_mode_enabled(self) -> bool:
        """鏄惁鍚敤 Agent 铚傜兢骞跺彂妯″紡"""
        with self._lock:
            return self.config.get("swarm_settings", {}).get("swarm_mode_enabled", False)

    @property
    def serial_mode_forced(self) -> bool:
        """鏄惁寮哄埗涓茶妯″紡(骞跺彂=1)"""
        with self._lock:
            return self.config.get("swarm_settings", {}).get("serial_mode_forced", True)

    @property
    def api_concurrency(self) -> int:
        """鑾峰彇瀹為檯 API 骞跺彂鏁?""
        with self._lock:
            if self.serial_mode_forced:
                return 1
            return self.config.get("swarm_settings", {}).get("max_concurrency", 5)

    @property
    def format_publish(self):
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.config["format_publish"]

    @property
    def proxy(self):
        """鑾峰彇鍏ㄥ眬浠ｇ悊璁剧疆"""
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.config.get("proxy", "")

    @property
    def publish_platform(self):
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.config["publish_platform"]

    @property
    def creative_config(self):
        """鑾峰彇缁村害鍖栧垱鎰忛厤缃?""
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.config.get("dimensional_creative", {})

    @property
    def dimensional_creative_config(self):
        """缁村害鍖栧垱鎰忛厤缃?""
        with self._lock:
            return self.creative_config

    @property
    def smart_recommendation_config(self):
        """鏅鸿兘鎺ㄨ崘閰嶇疆"""
        with self._lock:
            return self.creative_config.get("smart_recommendation", {})

    @property
    def api_list(self):
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)

            api_keys_list = list(self.config["api"].keys())
            if "api_type" in api_keys_list:
                api_keys_list.remove("api_type")

            return api_keys_list

    @property
    def api_list_display(self):
        """杩斿洖鐢ㄤ簬鐣岄潰鏄剧ず鐨凙PI绫诲瀷鍒楄〃"""
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)

            api_keys_list = list(self.config["api"].keys())
            if "api_type" in api_keys_list:
                api_keys_list.remove("api_type")

            # 杞崲涓烘樉绀哄悕绉?            display_list = []
            for api_type in api_keys_list:
                if api_type == "SiliconFlow":
                    display_list.append("纭呭熀娴佸姩")
                else:
                    display_list.append(api_type)

            return display_list

    # aiforge 閰嶇疆
    @property
    def aiforge_default_llm_provider(self):
        with self._lock:
            if not self.aiforge_config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.aiforge_config["default_llm_provider"]

    @property
    def aiforge_api_key(self):
        with self._lock:
            if not self.aiforge_config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.aiforge_config["llm"][self.aiforge_config["default_llm_provider"]][
                "api_key"
            ]

    def _bootstrap_release_config_file(self, file_name: str, config_path: str) -> None:
        """瀹夎鐗堥娆″惎鍔細浠呬粠鍑哄巶璧勬簮鍒濆鍖栫敤鎴风洰褰曪紝涓斿啀娆¤劚鏁忋€?""
        res_config_path = utils.get_res_path(f"config/{file_name}")
        if not os.path.exists(res_config_path):
            return

        utils.mkdir(os.path.dirname(config_path))

        if file_name == "config.yaml":
            try:
                with open(res_config_path, "r", encoding="utf-8") as f:
                    payload = yaml.safe_load(f) or {}
                payload = self._strip_secrets(payload)
                with open(config_path, "w", encoding="utf-8") as f:
                    yaml.dump(
                        payload,
                        f,
                        Dumper=IndentedDumper,
                        allow_unicode=True,
                        sort_keys=False,
                        default_flow_style=False,
                        indent=2,
                    )
            except Exception as e:
                log.print_log(f"[Config] 鍒濆鍖栧嚭鍘?config.yaml 澶辫触: {e}", "warning")
            return

        utils.copy_file(res_config_path, config_path)

    def _bootstrap_release_secrets_template(self) -> None:
        """瀹夎鐗堬細浠呭湪鐢ㄦ埛鐩綍鏃犲瘑閽ユ枃浠舵椂鍐欏叆绌烘ā鏉匡紝缁濅笉澶嶅埗寮€鍙戞満 secrets銆?""
        secrets_dir = os.path.join(str(PathManager.get_app_data_dir()), "secrets")
        secrets_path = os.path.join(secrets_dir, "api_keys.yaml")
        if os.path.exists(secrets_path):
            return

        utils.mkdir(secrets_dir)
        res_secrets = utils.get_res_path("secrets/api_keys.yaml")
        if os.path.exists(res_secrets):
            utils.copy_file(res_secrets, secrets_path)
            return

        empty_template = (
            "# AIWriteX 瀵嗛挜閰嶇疆锛堣鑷濉啓锛塡n\nwechat:\n  credentials: []\n\napi: {}\n\nimg_api: {}\n"
        )
        try:
            with open(secrets_path, "w", encoding="utf-8") as f:
                f.write(empty_template)
        except Exception as e:
            log.print_log(f"[Config] 鍒濆鍖?secrets 妯℃澘澶辫触: {e}", "warning")

    def __get_config_path(self, file_name="config.yaml"):
        """鑾峰彇閰嶇疆鏂囦欢璺緞骞剁‘淇濇枃浠跺瓨鍦?""

        config_path = str(PathManager.get_config_path(file_name))

        if utils.get_is_release_ver():
            if not os.path.exists(config_path):
                self._bootstrap_release_config_file(file_name, config_path)
            if file_name == "config.yaml":
                self._bootstrap_release_secrets_template()

        return config_path

    def get_sendall_by_appid(self, target_appid):
        for cred in self.config["wechat"]["credentials"]:
            if cred["appid"] == target_appid:
                return cred["sendall"]
        return False

    def get_call_sendall_by_appid(self, target_appid):
        for cred in self.config["wechat"]["credentials"]:
            if cred["appid"] == target_appid:
                return cred["call_sendall"]
        return False

    def get_draft_only_by_appid(self, target_appid):
        for cred in self.config["wechat"]["credentials"]:
            if cred["appid"] == target_appid:
                return cred.get("draft_only", False)
        return False

    def get_tagid_by_appid(self, target_appid):
        for cred in self.config["wechat"]["credentials"]:
            if cred["appid"] == target_appid:
                return cred["tag_id"]
        return False

    def load_config(self):
        """鍔犺浇閰嶇疆锛屼粠 config.yaml 鎴栭粯璁ら厤缃紝涓嶉獙璇?""
        with self._lock:
            ret = True
            if os.path.exists(self.config_path):
                try:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        self.config = yaml.safe_load(f)
                        if not self.config:
                            self.config = self.default_config
                except Exception as e:
                    self.error_message = f"鍔犺浇 config.yaml 澶辫触: {e}"
                    log.print_log(self.error_message, "error")
                    self.config = self.default_config
                    ret = False
            else:
                self.config = self.default_config

            if os.path.exists(self.config_aiforge_path):
                try:
                    with open(self.config_aiforge_path, "r", encoding="utf-8") as f:
                        self.aiforge_config = tomlkit.parse(f.read())
                        if not self.aiforge_config:
                            self.aiforge_config = self.default_aiforge_config
                except Exception as e:
                    self.error_message = f"鍔犺浇 aiforge.toml 澶辫触: {e}"
                    log.print_log(self.error_message, "error")
                    self.aiforge_config = self.default_aiforge_config
                    ret = False
            else:
                self.aiforge_config = self.default_aiforge_config
            # 鈹€鈹€ 馃攼 鐜鍙橀噺鍔犺浇 (浼樺厛绾ф渶楂? 鈹€鈹€
            self._load_env_variables()
            # 鈹€鈹€ 馃攼 鑷姩鍔犺浇 secrets/api_keys.yaml 瀵嗛挜瑕嗙洊 鈹€鈹€
            self._load_secrets()

            return ret

    def _load_env_variables(self):
        """浠庣幆澧冨彉閲忓姞杞?API 瀵嗛挜锛堜紭鍏堢骇鏈€楂橈級"""
        import os
        
        # 鏄犲皠鐜鍙橀噺鍚嶅埌閰嶇疆璺緞
        env_mappings = {
            # LLM API Keys
            "OPENAI_API_KEY": ("api", "OpenAI", "api_key"),
            "DEEPSEEK_API_KEY": ("api", "Deepseek", "api_key"),
            "QWEN_API_KEY": ("api", "Qwen", "api_key"),
            "GEMINI_API_KEY": ("api", "Gemini", "api_key"),
            "OPENROUTER_API_KEY": ("api", "OpenRouter", "api_key"),
            "SILICONFLOW_API_KEY": ("api", "SiliconFlow", "api_key"),
            "XAI_API_KEY": ("api", "XAI", "api_key"),
            "IFLOW_API_KEY": ("api", "蹇冩祦", "api_key"),
            # Image API Keys
            "ALI_API_KEY": ("img_api", "ali", "api_key"),
            "MODELSCOPE_API_KEY": ("img_api", "modelscope", "api_key"),
            "AGNES_API_KEY": ("img_api", "agnes", "api_key"),
            # WeChat
            "WECHAT_APPID": ("wechat", "credentials", 0, "appid"),
            "WECHAT_APPSECRET": ("wechat", "credentials", 0, "appsecret"),
        }
        
        loaded = []
        for env_var, path in env_mappings.items():
            value = os.environ.get(env_var)
            if value:
                try:
                    # 鍔ㄦ€佽缃祵濂楅厤缃?                    target = self.config
                    for key in path[:-1]:
                        if key not in target:
                            target[key] = {}
                        target = target[key]
                    
                    # 鏈€鍚庝竴涓?key 鏄疄闄呰璁剧疆鐨?                    last_key = path[-1]
                    if isinstance(last_key, int):
                        # 澶勭悊鍒楄〃绱㈠紩
                        if last_key < len(target):
                            target[last_key]["appid" if "appid" in env_var else "appsecret"] = value
                    else:
                        target[last_key] = value
                    
                    loaded.append(env_var)
                except Exception:
                    pass
        
        if loaded:
            log.print_log(f"[Config] 馃攼 浠庣幆澧冨彉閲忓姞杞戒簡 {len(loaded)} 涓瘑閽? {', '.join(loaded)}", "info")

    def _load_secrets(self):
        """浠?secrets/api_keys.yaml 璇诲彇瀵嗛挜骞跺悎骞跺埌杩愯鏃堕厤缃紙涓嶄慨鏀?config.yaml 鍘熸枃浠讹級"""
        try:
            secrets_path = os.path.join(str(PathManager.get_app_data_dir()), "secrets", "api_keys.yaml")
            if not os.path.exists(secrets_path):
                return

            with open(secrets_path, "r", encoding="utf-8") as f:
                secrets = yaml.safe_load(f)

            if not secrets or not isinstance(secrets, dict):
                return

            # 鍚堝苟寰俊鍑嵁
            if "wechat" in secrets and "credentials" in secrets["wechat"]:
                # 纭繚config涓湁credentials鍒楄〃
                if "wechat" not in self.config:
                    self.config["wechat"] = {}
                if "credentials" not in self.config["wechat"]:
                    self.config["wechat"]["credentials"] = []
                
                # 濡傛灉config涓殑credentials涓虹┖锛岀洿鎺ヤ娇鐢╯ecrets涓殑
                if not self.config["wechat"]["credentials"]:
                    self.config["wechat"]["credentials"] = secrets["wechat"]["credentials"]
                else:
                    # 鍚﹀垯鍚堝苟鍒扮幇鏈夊嚟鎹?                    for i, sec_cred in enumerate(secrets["wechat"]["credentials"]):
                        if i < len(self.config["wechat"]["credentials"]):
                            cred = self.config["wechat"]["credentials"][i]
                            if sec_cred.get("appid"):
                                cred["appid"] = sec_cred["appid"]
                            if sec_cred.get("appsecret"):
                                cred["appsecret"] = sec_cred["appsecret"]
                        else:
                            # 娣诲姞鏂扮殑鍑嵁
                            self.config["wechat"]["credentials"].append(sec_cred)

            # 鍚堝苟 LLM API 瀵嗛挜
            if "api" in secrets:
                self._merge_llm_api_secrets_from_file(secrets["api"])

            # 鍚堝苟鍥剧墖 API 瀵嗛挜
            if "img_api" in secrets:
                for provider, provider_secrets in secrets["img_api"].items():
                    if provider in self.config.get("img_api", {}):
                        # 鐗规畩澶勭悊 custom (鍙兘鏄垪琛?
                        if provider == "custom" and isinstance(self.config["img_api"][provider], list):
                            if isinstance(provider_secrets, list):
                                # 濡傛灉 secrets 涓篃鏄垪琛紝鎸夌储寮曞榻愯鐩?                                for i, sec_item in enumerate(provider_secrets):
                                    if i < len(self.config["img_api"][provider]):
                                        target = self.config["img_api"][provider][i]
                                        if isinstance(target, dict) and isinstance(sec_item, dict):
                                            for k, v in sec_item.items():
                                                if v: target[k] = v
                            elif isinstance(provider_secrets, dict):
                                # 濡傛灉 secrets 涓槸瀛楀吀锛屽皾璇曡鐩栧綋鍓?custom_index 鎸囧悜鐨勯」鐩?                                custom_index = int(self.config.get("img_api", {}).get("custom_index", 0) or 0)
                                if 0 <= custom_index < len(self.config["img_api"][provider]):
                                    target = self.config["img_api"][provider][custom_index]
                                    if isinstance(target, dict):
                                        for k, v in provider_secrets.items():
                                            if v: target[k] = v
                        
                        # 甯歌瀛楀吀澶勭悊
                        elif isinstance(provider_secrets, dict):
                            if isinstance(self.config["img_api"][provider], dict):
                                for k, v in provider_secrets.items():
                                    if v: self.config["img_api"][provider][k] = v

            log.print_log("[Config] 馃攼 宸蹭粠 secrets/api_keys.yaml 鍔犺浇瀵嗛挜瑕嗙洊", "info")
        except Exception as e:
            log.print_log(f"[Config] secrets 鍔犺浇澶辫触(闈炶嚧鍛?: {e}", "warning")

    def _merge_llm_api_secrets_from_file(self, api_secrets: dict) -> None:
        """灏?secrets 涓殑 LLM 瀵嗛挜鍚堝苟鍥炶繍琛屾椂閰嶇疆锛堝惈 api.custom 鍒楄〃锛夈€?""
        if not api_secrets or not isinstance(api_secrets, dict):
            return
        api_root = self.config.setdefault("api", {})

        # 鑷畾涔?API 鍒楄〃锛堝墠绔富瑕佹妸 Key 瀛樺湪 api.custom锛?        custom_secrets = api_secrets.get("custom")
        if isinstance(custom_secrets, list):
            custom_list = api_root.setdefault("custom", [])
            for i, sec in enumerate(custom_secrets):
                if not isinstance(sec, dict) or not sec.get("api_key"):
                    continue
                pk = sec.get("provider_key") or ""
                target = None
                if pk:
                    for item in custom_list:
                        if isinstance(item, dict) and item.get("provider_key") == pk:
                            target = item
                            break
                    if pk in api_root and isinstance(api_root.get(pk), dict):
                        api_root[pk]["api_key"] = sec["api_key"]
                if target is None and i < len(custom_list) and isinstance(custom_list[i], dict):
                    target = custom_list[i]
                if target is not None:
                    target["api_key"] = sec["api_key"]

        reserved = {"api_type", "deleted_providers", "custom"}
        for provider, provider_secrets in api_secrets.items():
            if provider in reserved:
                continue
            if provider not in api_root or not isinstance(api_root.get(provider), dict):
                continue
            if isinstance(provider_secrets, dict) and provider_secrets.get("api_key"):
                api_root[provider]["api_key"] = provider_secrets["api_key"]

    def _strip_secrets(self, config: Dict[Any, Any]) -> Dict[Any, Any]:
        """閫掑綊鍓ョ閰嶇疆涓殑鎵€鏈夋晱鎰熷瘑閽ワ紝闃叉娉勬紡鍒?config.yaml"""
        import copy
        sanitized = copy.deepcopy(config)
        
        # 瀹氫箟闇€瑕佽灞忚斀鐨勬晱鎰熷瓧娈靛悕
        SECRET_FIELDS = {"api_key", "appsecret", "appid", "key_index"}
        
        def _recurse_strip(obj):
            if isinstance(obj, dict):
                # 閬嶅巻瀛楀吀
                keys_to_reset = []
                for k, v in obj.items():
                    if k in SECRET_FIELDS:
                        # 瀵逛簬 api_key (閫氬父鏄垪琛ㄦ垨瀛楃涓?锛屽皾璇曟牴鎹粯璁ゅ€奸噸缃?                        if k == "api_key":
                            obj[k] = [] if isinstance(v, list) else ""
                        else:
                            obj[k] = ""
                    else:
                        _recurse_strip(v)
            elif isinstance(obj, list):
                for item in obj:
                    _recurse_strip(item)
                    
        _recurse_strip(sanitized)
        return sanitized

    def _save_secrets_to_file(self, config: Dict[Any, Any]) -> bool:
        """浠庨厤缃腑鎻愬彇鏁忔劅淇℃伅骞朵繚瀛樺埌 secrets/api_keys.yaml"""
        secrets_path = os.path.join(str(PathManager.get_app_data_dir()), "secrets", "api_keys.yaml")
        
        # 纭繚鐩綍瀛樺湪
        secrets_dir = os.path.dirname(secrets_path)
        if not os.path.exists(secrets_dir):
            os.makedirs(secrets_dir, exist_ok=True)
        
        # 璇诲彇鐜版湁鐨?secrets 鏂囦欢
        existing_secrets = {}
        if os.path.exists(secrets_path):
            try:
                with open(secrets_path, "r", encoding="utf-8") as f:
                    existing_secrets = yaml.safe_load(f) or {}
            except Exception:
                pass
        
        # 鏋勫缓鏂扮殑 secrets 缁撴瀯
        new_secrets = {}
        
        # 鎻愬彇寰俊鍑嵁
        if "wechat" in config and "credentials" in config["wechat"]:
            new_secrets["wechat"] = {"credentials": []}
            for cred in config["wechat"]["credentials"]:
                if cred.get("appid") or cred.get("appsecret"):
                    new_secrets["wechat"]["credentials"].append({
                        "appid": cred.get("appid", ""),
                        "appsecret": cred.get("appsecret", "")
                    })
        
        # 鎻愬彇 API 瀵嗛挜
        if "api" in config:
            new_secrets["api"] = {}
            api_block = config["api"]
            reserved = {"api_type", "deleted_providers", "custom"}
            for provider, provider_config in api_block.items():
                if provider in reserved:
                    continue
                if isinstance(provider_config, dict) and provider_config.get("api_key"):
                    new_secrets["api"][provider] = {"api_key": provider_config["api_key"]}

            custom_list = api_block.get("custom")
            if isinstance(custom_list, list):
                custom_secrets = []
                for item in custom_list:
                    if not isinstance(item, dict):
                        continue
                    keys = item.get("api_key")
                    if not keys or (isinstance(keys, list) and not any(keys)):
                        continue
                    sec_item = {"api_key": keys}
                    if item.get("provider_key"):
                        sec_item["provider_key"] = item["provider_key"]
                    if item.get("name"):
                        sec_item["name"] = item["name"]
                    custom_secrets.append(sec_item)
                if custom_secrets:
                    new_secrets["api"]["custom"] = custom_secrets
        
        # 鎻愬彇鍥剧墖 API 瀵嗛挜
        if "img_api" in config:
            new_secrets["img_api"] = {}
            for provider, provider_config in config["img_api"].items():
                if isinstance(provider_config, dict):
                    if provider in ("ali", "modelscope", "agnes") and provider_config.get("api_key"):
                        if provider_config["api_key"]:
                            new_secrets["img_api"][provider] = {"api_key": provider_config["api_key"]}
                    elif provider == "custom" and isinstance(provider_config, list):
                        # custom 鏄垪琛?                        custom_with_keys = []
                        for item in provider_config:
                            if isinstance(item, dict) and item.get("api_key"):
                                custom_with_keys.append({"api_key": item["api_key"]})
                        if custom_with_keys:
                            new_secrets["img_api"]["custom"] = custom_with_keys
        
        # 鍚堝苟: 淇濈暀鐜版湁 secrets 涓笉鍦ㄦ柊閰嶇疆涓殑鍐呭
        if "api" in new_secrets and isinstance(existing_secrets.get("api"), dict):
            ex_api = existing_secrets["api"]
            if "custom" not in new_secrets["api"] and ex_api.get("custom"):
                new_secrets["api"]["custom"] = ex_api["custom"]
            for prov, prov_sec in ex_api.items():
                if prov not in new_secrets["api"] and prov not in ("custom",):
                    new_secrets["api"][prov] = prov_sec

        for key in ["wechat", "api", "img_api"]:
            if key not in new_secrets:
                new_secrets[key] = existing_secrets.get(key, {})
            elif key in existing_secrets:
                # 娣卞害鍚堝苟
                if key == "wechat" and "credentials" in existing_secrets.get("wechat", {}):
                    # 淇濈暀娌℃湁鍦ㄦ柊閰嶇疆涓嚭鐜扮殑鍑嵁
                    existing_creds = existing_secrets["wechat"]["credentials"]
                    new_creds = new_secrets.get("wechat", {}).get("credentials", [])
                    new_appids = {c.get("appid") for c in new_creds if c.get("appid")}
                    for ec in existing_creds:
                        if ec.get("appid") and ec["appid"] not in new_appids:
                            if "credentials" not in new_secrets["wechat"]:
                                new_secrets["wechat"]["credentials"] = []
                            new_secrets["wechat"]["credentials"].append(ec)
        
        try:
            # 鐢熸垚甯︽敞閲婄殑鏂囦欢澶?            header = """# ============================================
# AIWriteX 鐪熷疄瀵嗛挜閰嶇疆
# 鈿狅笍 姝ゆ枃浠跺凡琚?.gitignore 淇濇姢锛屼笉浼氫笂浼?Git
# ============================================

"""
            with open(secrets_path, "w", encoding="utf-8") as f:
                f.write(header)
                yaml.dump(new_secrets, f, Dumper=IndentedDumper, allow_unicode=True, sort_keys=False, default_flow_style=False, indent=2)
            log.print_log("[Config] 馃攼 鏁忔劅淇℃伅宸蹭繚瀛樺埌 secrets/api_keys.yaml", "info")
            return True
        except Exception as e:
            log.print_log(f"[Config] 馃攼 淇濆瓨 secrets 澶辫触: {e}", "warning")
            return False

    def save_config(self, config, aiforge_config=None):
        """淇濆瓨閰嶇疆鍒?config.yaml锛岃嚜鍔ㄥ墺绂绘晱鎰熷瘑閽ワ紝涓嶉獙璇?""
        with self._lock:
            ret = True
            self.config = config
            
            # --- 馃攼 绗竴姝? 淇濆瓨鏁忔劅淇℃伅鍒?secrets 鏂囦欢 ---
            self._save_secrets_to_file(config)
            
            # --- 馃攼 绗簩姝? 鍓ョ鏁忔劅淇℃伅鍚庝繚瀛樺埌 config.yaml ---
            save_payload = self._strip_secrets(config)
            
            try:
                with open(self.config_path, "w", encoding="utf-8") as f:
                    yaml.dump(
                        save_payload,
                        f,
                        Dumper=IndentedDumper,
                        allow_unicode=True,
                        sort_keys=False,
                        default_flow_style=False,
                        indent=2,
                    )
            except Exception as e:
                self.error_message = f"淇濆瓨 config.yaml 澶辫触: {e}"
                log.print_log(self.error_message, "error")
                ret = False

            # 濡傛灉浼犻€掍簡
            if aiforge_config is not None:
                self.aiforge_config = aiforge_config
                try:
                    with open(self.config_aiforge_path, "w", encoding="utf-8") as f:
                        f.write(tomlkit.dumps(self.aiforge_config))

                except Exception as e:
                    self.error_message = f"淇濆瓨 aiforge.toml 澶辫触: {e}"
                    log.print_log(self.error_message, "error")
                    ret = False

            return ret

    def save_dimensional_creative_config(self, dimensional_config):
        """淇濆瓨缁村害鍖栧垱鎰忛厤缃埌鍗曠嫭鐨勬枃浠?""
        with self._lock:
            ret = True
            try:
                # 鍒涘缓鍖呭惈缁村害閫夐」鐨勫畬鏁撮厤缃?                full_config = {"dimension_options": dimensional_config}

                with open(self.config_dimensional_path, "w", encoding="utf-8") as f:
                    yaml.dump(
                        full_config,
                        f,
                        Dumper=IndentedDumper,
                        allow_unicode=True,
                        sort_keys=False,
                        default_flow_style=False,
                        indent=2,
                    )
            except Exception as e:
                self.error_message = f"淇濆瓨 dimensional_creative_config.yaml 澶辫触: {e}"
                log.print_log(self.error_message, "error")
                ret = False

            return ret

    def get_config(self):
        """鑾峰彇閰嶇疆锛屼笉楠岃瘉"""
        with self._lock:
            if not self.config:
                raise ValueError("閰嶇疆鏈姞杞?)
            return self.config

    def validate_config(self):
        """楠岃瘉閰嶇疆,浠呭湪 CrewAI 鎵ц鏃惰皟鐢?""
        try:
            # 鑾峰彇 API 閰嶇疆
            api_type = self.api_type
            api_config = self.config["api"][api_type]

            # 妫€鏌?api_key 鍒楄〃
            api_keys = api_config.get("api_key", [])
            if not api_keys or not any(api_keys):
                self.error_message = f"鏈厤缃瓵PI KEY锛岃鎵撳紑閰嶇疆濉啓{api_type}鐨刟pi_key"
                return False

            # 妫€鏌?key_index 鏄惁鏈夋晥
            key_index = int(api_config.get("key_index", 0) or 0)
            if key_index >= len(api_keys):
                self.error_message = f"{api_type}鐨刱ey_index({key_index})瓒呭嚭鑼冨洿锛宎pi_key鍒楄〃鍙湁{len(api_keys)}涓厓绱?  # noqa 501
                return False

            # 妫€鏌ラ€変腑鐨?api_key 鏄惁涓虹┖
            if not api_keys[key_index]:
                self.error_message = f"鏈厤缃瓵PI KEY锛岃鎵撳紑閰嶇疆濉啓{api_type}鐨刟pi_key"
                return False

            # 妫€鏌?model 鍒楄〃
            models = api_config.get("model", [])
            if not models:
                self.error_message = f"鏈厤缃甅odel锛岃鎵撳紑閰嶇疆濉啓{api_type}鐨刴odel"
                return False

            # 妫€鏌?model_index 鏄惁鏈夋晥
            model_index = int(api_config.get("model_index", 0) or 0)
            if model_index >= len(models):
                self.error_message = f"{api_type}鐨刴odel_index({model_index})瓒呭嚭鑼冨洿锛宮odel鍒楄〃鍙湁{len(models)}涓厓绱?  # noqa 501
                return False

            # 妫€鏌ラ€変腑鐨?model 鏄惁涓虹┖
            if not models[model_index]:
                self.error_message = f"鏈厤缃甅odel锛岃鎵撳紑閰嶇疆濉啓{api_type}鐨刴odel"
                return False

            # 妫€鏌ュ浘鐗囩敓鎴愰厤缃?            if self.img_api_type != "picsum":
                img_api_config = self.config.get("img_api", {}).get(self.img_api_type, {})
                
                

                # ComfyUI涓嶉渶瑕乤pi_key锛屽彧闇€瑕乤pi_base
                if self.img_api_type == "comfyui":
                    api_base = img_api_config.get("api_base", "")
                    if not api_base:
                        self.error_message = "鏈厤缃瓹omfyUI鐨凙PI鍦板潃锛岃鎵撳紑閰嶇疆濉啓"
                        return False
                else:
                    # 鍏煎澶勭悊锛氬鏋滄槸 custom 涓旈厤缃槸鍒楄〃锛屾彁鍙栧綋鍓嶉€変腑鐨勯」
                    if self.img_api_type == "custom" and isinstance(img_api_config, list):
                        img_api = self.config.get("img_api", {})
                        custom_index = int(img_api.get("custom_index", 0) or 0)
                        if 0 <= custom_index < len(img_api_config):
                            img_api_config = img_api_config[custom_index]
                        else:
                            self.error_message = "鏈厤缃嚜瀹氫箟鍥剧墖API锛屾垨閫夋嫨鐨勭储寮曟棤鏁?
                            return False

                    if not isinstance(img_api_config, dict):
                        self.error_message = f"鍥剧墖鐢熸垚閰嶇疆鏍煎紡閿欒: {self.img_api_type} 搴斾负瀛楀吀"
                        return False

                    # 鍏朵粬API锛堝ali, custom锛夐渶瑕乤pi_key
                    raw_api_key = img_api_config.get("api_key", "")

                    # 缁熶竴澶勭悊锛氬鏋滄槸鍒楄〃锛屽彇绱㈠紩锛涘鏋滄槸瀛楃涓诧紝鐩存帴妫€鏌?                    if isinstance(raw_api_key, list):
                        img_key_index = int(img_api_config.get("key_index", 0) or 0)
                        if not raw_api_key or img_key_index >= len(raw_api_key) or not raw_api_key[img_key_index]:
                            self.error_message = f"鏈厤缃浘鐗囩敓鎴愭ā鍨嬬殑API KEY锛岃鎵撳紑閰嶇疆濉啓{self.img_api_type}鐨刟pi_key"
                            return False
                    elif not raw_api_key:
                        self.error_message = f"鏈厤缃浘鐗囩敓鎴愭ā鍨嬬殑API KEY锛岃鎵撳紑閰嶇疆濉啓{self.img_api_type}鐨刟pi_key"
                        return False

                    raw_model = img_api_config.get("model", "")
                    if isinstance(raw_model, list):
                        img_model_index = int(img_api_config.get("model_index", 0) or 0)
                        if not raw_model or img_model_index >= len(raw_model) or not raw_model[img_model_index]:
                            self.error_message = f"鏈厤缃浘鐗囩敓鎴愮殑妯″瀷锛岃鎵撳紑閰嶇疆濉啓{self.img_api_type}鐨刴odel"
                            return False
                    elif not raw_model:
                        self.error_message = f"鏈厤缃浘鐗囩敓鎴愮殑妯″瀷锛岃鎵撳紑閰嶇疆濉啓{self.img_api_type}鐨刴odel"
                        return False

            # 妫€鏌ヨ嚜鍔ㄥ彂甯冮厤缃?            if self.auto_publish:
                valid_cred = any(
                    cred["appid"] and cred["appsecret"] for cred in self.wechat_credentials
                )
                if not valid_cred:
                    self.error_message = "銆愯嚜鍔ㄥ彂甯冦€戞椂锛岄渶閰嶇疆寰俊鍏紬鍙穉ppid鍜宎ppsecret"
                    return False

            # 妫€鏌?AIForge / LLM 閰嶇疆锛堝悓鏃舵鏌?aiforge.toml 鍜?config.yaml 鐨勫ぇ妯″瀷API锛?            has_valid_api_key = False

            # 1. 鍏堟鏌?aiforge.toml 鑷韩鐨勯厤缃?            if self.aiforge_config and self.aiforge_config.get("llm"):
                for provider_name, provider_config in self.aiforge_config["llm"].items():
                    if provider_config.get("api_key"):
                        has_valid_api_key = True
                        break

            # 2. 濡傛灉 aiforge.toml 娌℃湁鏈夋晥閰嶇疆锛屽洖閫€妫€鏌?config.yaml 鐨勫ぇ妯″瀷API
            if not has_valid_api_key and self.config.get("api"):
                api_config = self.config["api"]
                # 妫€鏌ヨ嚜瀹氫箟API
                if api_config.get("custom"):
                    for custom_api in api_config["custom"]:
                        if custom_api.get("api_key") or custom_api.get("api_base"):
                            has_valid_api_key = True
                            break
                # 妫€鏌ラ璁惧巶鍟?                for provider_name in ["openai", "deepseek", "qwen", "claude", "gemini", "grok"]:
                    if api_config.get(provider_name, {}).get("api_keys", [""])[0]:
                        has_valid_api_key = True
                        break

            if not has_valid_api_key:
                log.print_log("AIForge鏈厤缃湁鏁堢殑llm鎻愪緵鍟嗙殑api_key锛屽皢涓嶄娇鐢ㄦ悳绱㈠姛鑳?)

            return True

        except Exception as e:
            self.error_message = f"閰嶇疆楠岃瘉澶辫触: {e}"
            return False

    def reload_config(self):
        """閲嶆柊鍔犺浇閰嶇疆鏂囦欢"""
        with self._lock:
            log.print_log("閲嶆柊鍔犺浇閰嶇疆鏂囦欢...", "info")
            return self.load_config()

    def merge_with_user_config(self, user_config: dict) -> dict:
        """
        鏅鸿兘鍚堝苟鐢ㄦ埛閰嶇疆锛氫互榛樿閰嶇疆涓哄熀纭€锛屼繚鐣欑敤鎴峰凡閰嶇疆鐨勬湁鏁堝€?        杩欐槸閰嶇疆澶勭悊鐨勬牳蹇冮€昏緫锛屾浛浠ｅ鏉傜殑鐗堟湰杩佺Щ
        """
        import copy

        # 浠ラ粯璁ら厤缃负鍩虹
        merged_config = copy.deepcopy(self.default_config)

        if not user_config:
            return merged_config

        preserved_count = 0

        # 閫掑綊鍚堝苟鍑芥暟
        def merge_dict(default_dict: dict, user_dict: dict, path: str = "") -> int:
            nonlocal preserved_count
            count = 0

            for key, user_value in user_dict.items():
                current_path = f"{path}.{key}" if path else key

                # 濡傛灉榛樿閰嶇疆涓笉瀛樺湪璇ラ敭锛岃烦杩囷紙搴熷純鐨勯厤缃級
                if key not in default_dict:
                    continue

                default_value = default_dict[key]

                # 瀵逛簬瀛楀吀绫诲瀷锛岄€掑綊鍚堝苟
                if isinstance(default_value, dict) and isinstance(user_value, dict):
                    count += merge_dict(default_value, user_value, current_path)

                # 瀵逛簬闈炵┖鐨勬湁鎰忎箟鍊硷紝淇濈暀鐢ㄦ埛閰嶇疆
                elif self._is_meaningful_value(user_value, default_value):
                    default_dict[key] = user_value
                    count += 1

            return count

        preserved_count = merge_dict(merged_config, user_config)

        # 鈿?鎸佷箙鍖栧垹闄わ細鐢ㄦ埛涓诲姩鍒犻櫎鐨勬彁渚涘晢涓嶅啀琚?default_config 杩樺師
        deleted_api_providers = user_config.get("api", {}).get("deleted_providers", [])
        if deleted_api_providers and "api" in merged_config:
            for provider_key in deleted_api_providers:
                if provider_key in merged_config["api"] and provider_key != "api_type":
                    del merged_config["api"][provider_key]
            # 淇濈暀榛戝悕鍗曞埌鍚堝苟缁撴灉涓紝纭繚涓嬫淇濆瓨鏃朵粛鐒跺瓨鍦?            merged_config["api"]["deleted_providers"] = deleted_api_providers

        return merged_config

    def _is_meaningful_value(self, user_value, default_value) -> bool:
        """鍒ゆ柇鐢ㄦ埛鍊兼槸鍚︽湁鎰忎箟锛堝€煎緱淇濈暀锛?""
        # 瀵逛簬瀛楃涓诧紝涓嶄繚鐣欑┖瀛楃涓?        if isinstance(user_value, str):
            return user_value.strip() != ""

        # 瀵逛簬鍒楄〃锛屼笉淇濈暀绌哄垪琛ㄦ垨鍙湁绌哄瓧绗︿覆鐨勫垪琛?        if isinstance(user_value, list):
            if not user_value:
                return False
            # 妫€鏌ユ槸鍚︽墍鏈夊厓绱犻兘鏄┖瀛楃涓?            if all(isinstance(item, str) and item.strip() == "" for item in user_value):
                return False
            return True

        # 瀵逛簬甯冨皵鍊硷紝鍙湁涓庨粯璁ゅ€间笉鍚屾椂鎵嶄繚鐣?        if isinstance(user_value, bool):
            return user_value != default_value

        # 瀵逛簬鏁板瓧锛屽彧鏈変笌榛樿鍊间笉鍚屾椂鎵嶄繚鐣?        if isinstance(user_value, (int, float)):
            return user_value != default_value

        # 鍏朵粬绫诲瀷锛岄粯璁や繚鐣?        return True

    def smart_update_config(self):
        """
        鏅鸿兘鏇存柊閰嶇疆锛氭浛浠ｅ鏉傜殑鐗堟湰杩佺Щ閫昏緫
        浣跨敤鏈€鏂伴粯璁ら厤缃?+ 淇濈暀鐢ㄦ埛閰嶇疆鍊肩殑鏂瑰紡
        """
        with self._lock:
            try:
                user_config = None

                # 璇诲彇鐢ㄦ埛閰嶇疆锛堝鏋滃瓨鍦級
                if os.path.exists(self.config_path):
                    try:
                        with open(self.config_path, "r", encoding="utf-8") as f:
                            user_config = yaml.safe_load(f)
                    except Exception as e:
                        log.print_log(f"璇诲彇鐢ㄦ埛閰嶇疆澶辫触: {e}", "warning")
                        user_config = None

                # 鍚堝苟閰嶇疆锛堢増鏈彿鑷姩鏇存柊涓烘渶鏂帮級
                merged_config = self.merge_with_user_config(user_config or {})

                # 淇濆瓨鍚堝苟鍚庣殑閰嶇疆
                with open(self.config_path, "w", encoding="utf-8") as f:
                    yaml.dump(
                        merged_config,
                        f,
                        Dumper=IndentedDumper,
                        allow_unicode=True,
                        sort_keys=False,
                        default_flow_style=False,
                        indent=2,
                    )

                # 鏇存柊鍐呭瓨涓殑閰嶇疆
                self.config = merged_config

                log.print_log("閰嶇疆鏁版嵁鍔犺浇鎴愬姛", "success")
                return True

            except Exception as e:
                log.print_log(f"閰嶇疆鏁版嵁鍔犺浇澶辫触: {e}", "error")
                return False

    def migrate_config_if_needed(self):
        """
        鏅鸿兘閰嶇疆鏇存柊锛氭浛浠ｅ鏉傜殑鐗堟湰杩佺Щ閫昏緫
        鎬绘槸浣跨敤鏈€鏂伴粯璁ら厤缃?+ 淇濈暀鐢ㄦ埛閰嶇疆鍊?        """
        try:
            return self.smart_update_config()
        except Exception:
            # 澶辫触鏃朵娇鐢ㄩ粯璁ら厤缃?            try:
                # 鐩存帴浣跨敤榛樿閰嶇疆閲嶅啓锛堢増鏈彿宸叉槸鏈€鏂帮級
                config_path = str(PathManager.get_config_path("config.yaml"))
                with open(config_path, "w", encoding="utf-8") as f:
                    yaml.dump(
                        self.default_config,
                        f,
                        allow_unicode=True,
                        sort_keys=False,
                        default_flow_style=False,
                        indent=2,
                    )

                self.config = self.default_config.copy()
                return True

            except Exception:
                return False

