# -*- coding: utf-8 -*-

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel


class TopicStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    APPROVED = "approved"


class Topic(SQLModel, table=True):
    __tablename__ = "topics"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    title: str = Field(index=True, nullable=False)
    category: str = Field(default="unknown", index=True)
    source_platform: str = Field(default="unknown", index=True)
    hot_score: int = Field(default=0)
    status: TopicStatus = Field(default=TopicStatus.PENDING)
    semantic_hash: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    articles: List["Article"] = Relationship(back_populates="topic")

    def to_dict(self) -> dict:
        return self.model_dump()


class Article(SQLModel, table=True):
    __tablename__ = "articles"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    topic_id: Optional[UUID] = Field(default=None, foreign_key="topics.id")
    title: str = Field(default="", index=True)
    category: str = Field(default="unknown", index=True)
    platform: str = Field(default="wechat", index=True)
    status: str = Field(default="draft", index=True)
    source_url: Optional[str] = Field(default=None)
    content: str = Field(nullable=False)
    format: str = Field(default="Markdown")
    version: int = Field(default=1)
    ai_probability: Optional[float] = Field(default=None)
    continuity_score: Optional[float] = Field(default=None)
    human_rating: Optional[int] = Field(default=None, nullable=True)
    is_published: bool = Field(default=False)
    published_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    topic: Optional[Topic] = Relationship(back_populates="articles")

    def to_dict(self) -> dict:
        return self.model_dump()


class AgentMemory(SQLModel, table=True):
    __tablename__ = "agent_memories"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    agent_role: str = Field(default="unknown", index=True)
    memory_text: str = Field(default="")
    agent_id: str = Field(default="unknown", index=True)
    memory_type: str = Field(default="fact", index=True)
    content: str = Field(default="")
    vector_embedding: Optional[str] = Field(default=None)
    metadata_json: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return self.model_dump()


class SystemSetting(SQLModel, table=True):
    __tablename__ = "system_settings"

    key: str = Field(primary_key=True)
    value: str
    updated_at: datetime = Field(default_factory=datetime.now)


class ScheduledTask(SQLModel, table=True):
    __tablename__ = "scheduled_tasks"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    topic: str = Field(index=True)
    platform: str = Field(default="wechat")
    execution_time: datetime
    status: str = Field(default="enabled")
    is_recurring: bool = Field(default=False)
    interval_hours: int = Field(default=0)
    article_count: int = Field(default=1)
    use_ai_beautify: bool = Field(default=True)
    collection_mode: bool = Field(default=False)
    last_run_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @staticmethod
    def get_by_id(task_id: str) -> Optional["ScheduledTask"]:
        from src.ai_write_x.database.db_manager import get_session
        from uuid import UUID

        try:
            tid = UUID(task_id) if isinstance(task_id, str) else task_id
            with get_session() as session:
                return session.get(ScheduledTask, tid)
        except Exception:
            return None

    def save(self):
        from src.ai_write_x.database.db_manager import get_session

        with get_session() as session:
            session.add(self)
            session.commit()
            session.refresh(self)


class TaskLog(SQLModel, table=True):
    __tablename__ = "task_logs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    task_id: UUID = Field(index=True)
    status: str
    message: str
    run_time: datetime = Field(default_factory=datetime.now)
    article_id: Optional[str] = Field(default=None)

    @staticmethod
    def get_by_id(log_id: str) -> Optional["TaskLog"]:
        from src.ai_write_x.database.db_manager import get_session
        from uuid import UUID

        try:
            lid = UUID(log_id) if isinstance(log_id, str) else log_id
            with get_session() as session:
                return session.get(TaskLog, lid)
        except Exception:
            return None


class VisualAsset(SQLModel, table=True):
    __tablename__ = "visual_assets"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    article: str = Field(index=True)
    prompt: str
    image_path: str
    asset_type: str = Field(default="illustration")
    meta_data_json: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now)


class SystemEntropy(SQLModel, table=True):
    __tablename__ = "system_entropy"

    id: Optional[int] = Field(default=None, primary_key=True)
    entropy_value: float
    reasoning_load: float
    active_agents: int
    timestamp: datetime = Field(default_factory=datetime.now)


class ArticleAesthetic(SQLModel, table=True):
    __tablename__ = "article_aesthetics"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    article_id: Optional[UUID] = Field(default=None, foreign_key="articles.id", index=True)
    article_path: Optional[str] = Field(default=None, index=True)
    template_id: Optional[str] = Field(default=None, index=True)
    positive_tags: str = Field(default="[]")
    negative_tags: str = Field(default="[]")
    rating: int = Field(default=5)
    comment: Optional[str] = Field(default=None)
    design_dna: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now)
