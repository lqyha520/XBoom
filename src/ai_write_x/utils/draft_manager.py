# -*- coding: UTF-8 -*-
"""自动草稿保存 - 防止生成失败时内容丢失"""

import time
import json
from pathlib import Path
from typing import Optional, Dict
from src.ai_write_x.utils.path_manager import PathManager


class DraftManager:
    """草稿管理器"""
    
    def __init__(self):
        self.draft_dir = PathManager.get_app_data_dir() / "drafts"
        self.draft_dir.mkdir(exist_ok=True, parents=True)
        self._auto_save_enabled = True
    
    def save_draft(self, session_id: str, data: Dict):
        """保存草稿"""
        if not self._auto_save_enabled:
            return
        
        draft_file = self.draft_dir / f"{session_id}.json"
        try:
            draft_data = {
                "timestamp": time.time(),
                "session_id": session_id,
                "data": data
            }
            with open(draft_file, 'w', encoding='utf-8') as f:
                json.dump(draft_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Draft] 保存草稿失败: {e}")
    
    def load_draft(self, session_id: str) -> Optional[Dict]:
        """加载草稿"""
        draft_file = self.draft_dir / f"{session_id}.json"
        if draft_file.exists():
            try:
                with open(draft_file, 'r', encoding='utf-8') as f:
                    draft_data = json.load(f)
                    return draft_data.get('data')
            except:
                return None
        return None
    
    def delete_draft(self, session_id: str):
        """删除草稿"""
        draft_file = self.draft_dir / f"{session_id}.json"
        draft_file.unlink(missing_ok=True)
    
    def list_drafts(self) -> list:
        """列出所有草稿"""
        drafts = []
        for draft_file in self.draft_dir.glob("*.json"):
            try:
                with open(draft_file, 'r', encoding='utf-8') as f:
                    draft_data = json.load(f)
                    drafts.append({
                        "session_id": draft_data.get('session_id'),
                        "timestamp": draft_data.get('timestamp'),
                        "preview": str(draft_data.get('data', {}))[:100]
                    })
            except:
                pass
        return sorted(drafts, key=lambda x: x['timestamp'], reverse=True)
    
    def clean_old_drafts(self, days: int = 7):
        """清理旧草稿（超过指定天数）"""
        cutoff_time = time.time() - (days * 86400)
        cleaned = 0
        
        for draft_file in self.draft_dir.glob("*.json"):
            try:
                with open(draft_file, 'r', encoding='utf-8') as f:
                    draft_data = json.load(f)
                    if draft_data.get('timestamp', 0) < cutoff_time:
                        draft_file.unlink()
                        cleaned += 1
            except:
                pass
        
        return cleaned


# 全局草稿管理器实例
draft_manager = DraftManager()
