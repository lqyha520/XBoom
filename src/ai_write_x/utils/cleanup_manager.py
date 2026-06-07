# -*- coding: UTF-8 -*-
"""内存清理管理器 - 定期清理临时文件和日志"""

import os
import time
from pathlib import Path
from typing import List
from src.ai_write_x.utils.path_manager import PathManager


class CleanupManager:
    """内存和磁盘清理管理器"""
    
    def __init__(self):
        self.temp_dir = PathManager.get_app_data_dir() / "temp"
        self.log_dir = PathManager.get_root_dir() / "logs"
        
        # 清理策略
        self.temp_file_max_age = 3600 * 24  # 临时文件保留1天
        self.log_file_max_age = 3600 * 24 * 7  # 日志保留7天
        self.log_file_max_size = 10 * 1024 * 1024  # 单个日志文件最大10MB
    
    def clean_temp_files(self) -> int:
        """清理临时文件"""
        if not self.temp_dir.exists():
            return 0
        
        cleaned = 0
        cutoff_time = time.time() - self.temp_file_max_age
        
        for file in self.temp_dir.rglob("*"):
            if file.is_file():
                try:
                    if file.stat().st_mtime < cutoff_time:
                        file.unlink()
                        cleaned += 1
                except Exception as e:
                    print(f"[Cleanup] 清理临时文件失败 {file}: {e}")
        
        return cleaned
    
    def clean_old_logs(self) -> int:
        """清理旧日志"""
        if not self.log_dir.exists():
            return 0
        
        cleaned = 0
        cutoff_time = time.time() - self.log_file_max_age
        
        for log_file in self.log_dir.glob("*.log"):
            try:
                # 删除过期日志
                if log_file.stat().st_mtime < cutoff_time:
                    log_file.unlink()
                    cleaned += 1
                # 或者截断过大的日志
                elif log_file.stat().st_size > self.log_file_max_size:
                    self._truncate_log(log_file)
                    cleaned += 1
            except Exception as e:
                print(f"[Cleanup] 清理日志失败 {log_file}: {e}")
        
        return cleaned
    
    def _truncate_log(self, log_file: Path):
        """截断日志文件（保留最后1MB）"""
        try:
            with open(log_file, 'rb') as f:
                f.seek(-1024 * 1024, 2)  # 从文件末尾向前1MB
                content = f.read()
            
            with open(log_file, 'wb') as f:
                f.write(b"[Log truncated due to size limit]\n")
                f.write(content)
        except:
            pass
    
    def clean_cache_images(self, max_age_days: int = 7) -> int:
        """清理缓存图片"""
        image_dir = PathManager.get_image_dir()
        if not image_dir.exists():
            return 0
        
        cleaned = 0
        cutoff_time = time.time() - (max_age_days * 86400)
        
        for image_file in image_dir.glob("comfyui_*.png"):
            try:
                if image_file.stat().st_mtime < cutoff_time:
                    image_file.unlink()
                    cleaned += 1
            except Exception as e:
                print(f"[Cleanup] 清理图片失败 {image_file}: {e}")
        
        return cleaned
    
    def get_disk_usage(self) -> dict:
        """获取磁盘使用情况"""
        stats = {}
        
        # 临时文件
        if self.temp_dir.exists():
            size = sum(f.stat().st_size for f in self.temp_dir.rglob("*") if f.is_file())
            stats['temp'] = size
        
        # 日志文件
        if self.log_dir.exists():
            size = sum(f.stat().st_size for f in self.log_dir.glob("*.log"))
            stats['logs'] = size
        
        # 图片文件
        image_dir = PathManager.get_image_dir()
        if image_dir.exists():
            size = sum(f.stat().st_size for f in image_dir.glob("*.png"))
            stats['images'] = size
        
        return stats
    
    def full_cleanup(self) -> dict:
        """执行完整清理"""
        results = {
            "temp_files": self.clean_temp_files(),
            "old_logs": self.clean_old_logs(),
            "cache_images": self.clean_cache_images()
        }
        
        # 清理缓存管理器
        try:
            from src.ai_write_x.utils.cache_manager import cache_manager
            cache_manager.clean_expired_cache()
        except:
            pass
        
        # 清理草稿管理器
        try:
            from src.ai_write_x.utils.draft_manager import draft_manager
            draft_manager.clean_old_drafts(7)
        except:
            pass
        
        return results


# 全局清理管理器实例
cleanup_manager = CleanupManager()
