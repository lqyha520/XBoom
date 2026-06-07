# -*- coding: UTF-8 -*-
"""缓存管理器 - 热搜数据和图片提示词缓存"""

import time
import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any
from src.ai_write_x.utils.path_manager import PathManager


class CacheManager:
    """缓存管理器"""
    
    def __init__(self):
        self.cache_dir = PathManager.get_app_data_dir() / "cache"
        self.cache_dir.mkdir(exist_ok=True, parents=True)
        
        self.hotspot_cache_file = self.cache_dir / "hotspot_cache.json"
        self.image_prompt_cache_file = self.cache_dir / "image_prompt_cache.json"
        
        # 缓存过期时间
        self.hotspot_ttl = 1800  # 热搜缓存30分钟
        self.image_prompt_ttl = 86400 * 7  # 图片缓存7天
        
        self._hotspot_cache = self._load_cache(self.hotspot_cache_file)
        self._image_cache = self._load_cache(self.image_prompt_cache_file)
    
    def _load_cache(self, cache_file: Path) -> Dict:
        """加载缓存文件"""
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_cache(self, cache_file: Path, data: Dict):
        """保存缓存文件"""
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Cache] 保存缓存失败: {e}")
    
    def _is_expired(self, timestamp: float, ttl: int) -> bool:
        """检查缓存是否过期"""
        return time.time() - timestamp > ttl
    
    # ========== 热搜缓存 ==========
    
    def get_hotspot_cache(self, source: str) -> Optional[Any]:
        """获取热搜缓存"""
        key = f"hotspot_{source}"
        if key in self._hotspot_cache:
            cache_data = self._hotspot_cache[key]
            if not self._is_expired(cache_data['timestamp'], self.hotspot_ttl):
                return cache_data['data']
        return None
    
    def set_hotspot_cache(self, source: str, data: Any):
        """设置热搜缓存"""
        key = f"hotspot_{source}"
        self._hotspot_cache[key] = {
            'timestamp': time.time(),
            'data': data
        }
        self._save_cache(self.hotspot_cache_file, self._hotspot_cache)
    
    # ========== 图片提示词缓存 ==========
    
    def get_image_cache(self, prompt: str) -> Optional[str]:
        """获取图片缓存路径"""
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
        if prompt_hash in self._image_cache:
            cache_data = self._image_cache[prompt_hash]
            if not self._is_expired(cache_data['timestamp'], self.image_prompt_ttl):
                image_path = cache_data['path']
                # 检查文件是否存在
                if Path(image_path).exists():
                    return image_path
        return None
    
    def set_image_cache(self, prompt: str, image_path: str):
        """设置图片缓存"""
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
        self._image_cache[prompt_hash] = {
            'timestamp': time.time(),
            'path': image_path,
            'prompt': prompt[:100]  # 保存前100字符用于调试
        }
        self._save_cache(self.image_prompt_cache_file, self._image_cache)
    
    # ========== 清理缓存 ==========
    
    def clean_expired_cache(self):
        """清理过期缓存"""
        # 清理热搜缓存
        expired_keys = []
        for key, cache_data in self._hotspot_cache.items():
            if self._is_expired(cache_data['timestamp'], self.hotspot_ttl):
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._hotspot_cache[key]
        
        if expired_keys:
            self._save_cache(self.hotspot_cache_file, self._hotspot_cache)
        
        # 清理图片缓存
        expired_keys = []
        for key, cache_data in self._image_cache.items():
            if self._is_expired(cache_data['timestamp'], self.image_prompt_ttl):
                expired_keys.append(key)
                # 删除缓存的图片文件
                try:
                    Path(cache_data['path']).unlink(missing_ok=True)
                except:
                    pass
        
        for key in expired_keys:
            del self._image_cache[key]
        
        if expired_keys:
            self._save_cache(self.image_prompt_cache_file, self._image_cache)
        
        return len(expired_keys)
    
    def get_cache_stats(self) -> Dict:
        """获取缓存统计"""
        return {
            "hotspot_count": len(self._hotspot_cache),
            "image_count": len(self._image_cache),
            "cache_dir": str(self.cache_dir)
        }


# 全局缓存管理器实例
cache_manager = CacheManager()
