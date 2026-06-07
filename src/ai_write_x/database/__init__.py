# -*- coding: UTF-8 -*-
"""
AIWriteX 数据库模块
统一数据库访问层

特性:
- SQLModel关系级联操作
- 连接池管理
- 自动迁移系统
"""

import os
import asyncio
from sqlmodel import SQLModel, create_engine, Session, select
from sqlalchemy.pool import StaticPool
from typing import List, Optional, Callable
from datetime import datetime

# Database path - 使用V13+路径（确保使用绝对路径，兼容打包模式）
from src.ai_write_x.utils.path_manager import PathManager
app_data_dir = PathManager.get_app_data_dir()
DB_PATH = os.path.join(str(app_data_dir), "data", "aiwritex_v6.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Create engine with connection pool
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    pool_pre_ping=True,
    pool_recycle=3600,
)


class ConnectionPool:
    """
    数据库连接池管理器
    
    特性:
    - 连接复用
    - 自动重连
    - 健康检查
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._engine = engine
        self._health_check_interval = 300  # 5分钟
        self._last_health_check = datetime.now()
    
    def get_connection(self):
        """获取连接"""
        return self._engine.connect()
    
    def get_session(self):
        """获取会话"""
        return Session(self._engine)
    
    async def health_check(self) -> bool:
        """健康检查"""
        now = datetime.now()
        if (now - self._last_health_check).total_seconds() < self._health_check_interval:
            return True
        
        try:
            with self.get_connection() as conn:
                conn.execute("SELECT 1")
            self._last_health_check = now
            return True
        except Exception:
            return False
    
    def close_all(self):
        """关闭所有连接"""
        self._engine.dispose()


class MigrationManager:
    """
    数据库自动迁移系统
    
    特性:
    - 增量迁移
    - 版本追踪
    - 回滚支持
    """
    
    def __init__(self, engine):
        self.engine = engine
        self._ensure_migrations_table()
    
    def _ensure_migrations_table(self):
        """确保迁移记录表存在"""
        from sqlalchemy import text
        
        with self.engine.connect() as conn:
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version VARCHAR PRIMARY KEY,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        description TEXT
                    )
                """))
                conn.commit()
            except Exception:
                pass
    
    def get_applied_migrations(self) -> List[str]:
        """获取已应用的迁移"""
        from sqlalchemy import text
        
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT version FROM schema_migrations"))
            return [row[0] for row in result]
    
    def apply_migration(
        self,
        version: str,
        description: str,
        sql_statements: List[str]
    ):
        """应用迁移"""
        from sqlalchemy import text
        
        applied = self.get_applied_migrations()
        
        if version in applied:
            return  # 已迁移
        
        with self.engine.connect() as conn:
            try:
                for stmt in sql_statements:
                    try:
                        conn.execute(text(stmt))
                    except Exception:
                        # 忽略列已存在等错误
                        pass
                
                conn.execute(text(
                    "INSERT INTO schema_migrations (version, description) VALUES (:v, :d)"
                ), {"v": version, "d": description})
                
                conn.commit()
                print(f"[迁移] 已应用: {version} - {description}")
                
            except Exception as e:
                conn.rollback()
                print(f"[迁移] 失败: {version} - {e}")
                raise
    
    def run_migrations(self):
        """运行所有迁移"""
        migrations = [
            {
                "version": "v13.0",
                "description": "添加语义哈希和质量指纹",
                "statements": [
                    "ALTER TABLE topics ADD COLUMN semantic_hash VARCHAR",
                    "ALTER TABLE articles ADD COLUMN ai_probability FLOAT",
                    "ALTER TABLE articles ADD_column continuity_score FLOAT",
                    "ALTER TABLE articles ADD COLUMN human_rating INTEGER",
                    "ALTER TABLE agent_memories ADD COLUMN metadata_json VARCHAR",
                ]
            },
            {
                "version": "v14.0",
                "description": "添加系统熵和美学评分",
                "statements": [
                    "CREATE TABLE IF NOT EXISTS system_entropy (id VARCHAR PRIMARY KEY, value FLOAT, calculated_at TIMESTAMP)",
                    "CREATE TABLE IF NOT EXISTS article_aesthetic (id VARCHAR PRIMARY KEY, article_id VARCHAR, aesthetic_score FLOAT, details TEXT)",
                ]
            },
            {
                "version": "v18.0",
                "description": "蜂群系统相关表",
                "statements": [
                    "CREATE TABLE IF NOT EXISTS swarm_state (id VARCHAR PRIMARY KEY, state_json TEXT, updated_at TIMESTAMP)",
                    "CREATE TABLE IF NOT EXISTS pheromone_space (id VARCHAR PRIMARY KEY, agent_id VARCHAR, pheromone_type VARCHAR, strength FLOAT)",
                ]
            },
            {
                "version": "v1.0.1-scheduler",
                "description": "定时任务 last_run_at 字段",
                "statements": [
                    "ALTER TABLE scheduled_tasks ADD COLUMN last_run_at TIMESTAMP",
                ],
            },
            {
                "version": "v1.2.2-collection-mode",
                "description": "定时任务合集模式字段",
                "statements": [
                    "ALTER TABLE scheduled_tasks ADD COLUMN collection_mode BOOLEAN DEFAULT 0",
                ],
            },
            {
                "version": "v1.2.14-model-compat",
                "description": "Add model compatibility columns used by repositories",
                "statements": [
                    "ALTER TABLE topics ADD COLUMN category VARCHAR DEFAULT 'unknown'",
                    "ALTER TABLE articles ADD COLUMN title VARCHAR DEFAULT ''",
                    "ALTER TABLE articles ADD COLUMN category VARCHAR DEFAULT 'unknown'",
                    "ALTER TABLE articles ADD COLUMN platform VARCHAR DEFAULT 'wechat'",
                    "ALTER TABLE articles ADD COLUMN status VARCHAR DEFAULT 'draft'",
                    "ALTER TABLE articles ADD COLUMN source_url VARCHAR",
                    "ALTER TABLE articles ADD COLUMN is_published BOOLEAN DEFAULT 0",
                    "ALTER TABLE articles ADD COLUMN published_at TIMESTAMP",
                    "ALTER TABLE articles ADD COLUMN updated_at TIMESTAMP",
                    "ALTER TABLE agent_memories ADD COLUMN agent_id VARCHAR DEFAULT 'unknown'",
                    "ALTER TABLE agent_memories ADD COLUMN memory_type VARCHAR DEFAULT 'fact'",
                    "ALTER TABLE agent_memories ADD COLUMN content VARCHAR DEFAULT ''",
                ],
            },
        ]
        
        for migration in migrations:
            self.apply_migration(
                migration["version"],
                migration["description"],
                migration["statements"]
            )


def init_db():
    """Initialize the database and create tables."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    # 创建表
    SQLModel.metadata.create_all(engine)
    
    # 运行迁移
    migration_manager = MigrationManager(engine)
    migration_manager.run_migrations()

def get_session():
    """Get a new database session."""
    return Session(engine)

# 先导入模型（无依赖）
from .models import Topic, Article, AgentMemory, SystemSetting, TopicStatus, ScheduledTask, TaskLog, VisualAsset, SystemEntropy, ArticleAesthetic

# 仓储层
from .repository import (
    BaseRepository,
    TopicRepository,
    ArticleRepository,
    MemoryRepository,
)

# V13.0 兼容性补丁: SQLModel 使用 engine 替代 Peewee 的 db
db = engine 

# 统一的数据库管理器
from .db_manager import DBManager

db_manager = DBManager()

# 统一的仓储实例
topic_repo = TopicRepository()
article_repo = ArticleRepository()
memory_repo = MemoryRepository()

__all__ = [
    # 初始化和连接
    "init_db",
    "db",
    "get_session",
    "engine",
    
    # 连接池管理
    "ConnectionPool",
    "MigrationManager",
    
    # 数据库管理器
    "DBManager",
    "db_manager",
    
    # 仓储层
    "BaseRepository",
    "TopicRepository",
    "ArticleRepository",
    "MemoryRepository",
    "topic_repo",
    "article_repo",
    "memory_repo",
    
    # 模型
    "Topic",
    "Article",
    "AgentMemory",
    "SystemSetting",
    "TopicStatus",
    "ScheduledTask",
    "TaskLog",
    "VisualAsset",
    "SystemEntropy",
    "ArticleAesthetic",
]
