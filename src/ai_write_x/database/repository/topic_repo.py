# -*- coding: UTF-8 -*-
"""
主题仓储 - Topic Repository
提供主题相关的数据库操作。
"""

from contextlib import contextmanager
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlmodel import select, desc

from src.ai_write_x.database import Topic, TopicStatus, get_session
from src.ai_write_x.database.repository.base import BaseRepository, _SessionAdapter
from src.ai_write_x.core.exceptions import DatabaseError, RecordNotFoundError
from src.ai_write_x.utils import log


class TopicRepository(BaseRepository[Topic]):
    """Topic repository."""

    @property
    def model(self) -> type[Topic]:
        return Topic

    @contextmanager
    def _get_session(self):
        session = _SessionAdapter(get_session())
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_by_category(self, category: str, limit: int = 20) -> List[Topic]:
        with self._get_session() as session:
            query = session.query(Topic)
            if hasattr(query, "filter"):
                result = query.filter(Topic.category == category)
                if hasattr(result, "limit"):
                    result = result.limit(limit)
                if hasattr(result, "all"):
                    return list(result.all())
                return list(result)
            return list(session.exec(select(Topic).where(Topic.category == category).limit(limit)).all())

    def _topic_to_dict(self, topic: Topic) -> Dict[str, Any]:
        if topic is None:
            return {}
        return topic.model_dump()

    def _dict_to_topic(self, data: Dict[str, Any]) -> Topic:
        if "status" in data and isinstance(data["status"], str):
            try:
                data = dict(data)
                data["status"] = TopicStatus(data["status"])
            except ValueError:
                data["status"] = TopicStatus.PENDING
        return Topic(**data)

    def create_topic(self, title: str, source_platform: str = "unknown", hot_score: int = 0, **kwargs) -> Topic:
        try:
            with self._get_session() as session:
                existing = session.exec(select(Topic).where(Topic.title == title)).first()
                if existing:
                    return self._dict_to_topic(self._topic_to_dict(existing))

                topic = Topic(
                    title=title,
                    source_platform=source_platform,
                    hot_score=hot_score,
                    status=TopicStatus.PENDING,
                    **kwargs,
                )
                session.add(topic)
                session.flush()
                return self._dict_to_topic(self._topic_to_dict(topic))
        except DatabaseError:
            raise
        except Exception as e:
            log.print_log(f"[TopicRepository] create topic failed: {e}", "error")
            raise DatabaseError(f"创建主题失败: {title}") from e

    def get_by_title(self, title: str) -> Optional[Topic]:
        try:
            with self._get_session() as session:
                result = session.exec(select(Topic).where(Topic.title == title)).first()
                return self._dict_to_topic(self._topic_to_dict(result)) if result else None
        except Exception as e:
            log.print_log(f"[TopicRepository] get topic failed: {e}", "error")
            raise DatabaseError(f"获取主题失败: {title}") from e

    def get_hot_topics(self, limit: int = 20, min_score: int = 0) -> List[Topic]:
        try:
            with self._get_session() as session:
                statement = (
                    select(Topic)
                    .where(Topic.hot_score >= min_score)
                    .where(Topic.status == TopicStatus.APPROVED)
                    .order_by(desc(Topic.hot_score))
                    .limit(limit)
                )
                return [self._dict_to_topic(self._topic_to_dict(topic)) for topic in session.exec(statement).all()]
        except Exception as e:
            log.print_log(f"[TopicRepository] get hot topics failed: {e}", "error")
            raise DatabaseError("获取热门主题失败") from e

    def get_pending_topics(self, limit: int = 50) -> List[Topic]:
        try:
            with self._get_session() as session:
                statement = (
                    select(Topic)
                    .where(Topic.status == TopicStatus.PENDING)
                    .order_by(desc(Topic.hot_score))
                    .limit(limit)
                )
                return [self._dict_to_topic(self._topic_to_dict(topic)) for topic in session.exec(statement).all()]
        except Exception as e:
            log.print_log(f"[TopicRepository] get pending topics failed: {e}", "error")
            raise DatabaseError("获取待处理主题失败") from e

    def update_status(self, topic_id: int, status: TopicStatus) -> bool:
        try:
            with self._get_session() as session:
                topic = session.exec(select(Topic).where(Topic.id == topic_id)).first()
                if not topic:
                    raise RecordNotFoundError(f"Topic(id={topic_id}) not found")
                topic.status = status
                topic.updated_at = datetime.now()
                session.add(topic)
                return True
        except RecordNotFoundError:
            raise
        except Exception as e:
            log.print_log(f"[TopicRepository] update status failed: {e}", "error")
            raise DatabaseError("更新主题状态失败") from e

    def increment_hot_score(self, topic_id: int, delta: int = 1) -> bool:
        try:
            with self._get_session() as session:
                topic = session.exec(select(Topic).where(Topic.id == topic_id)).first()
                if not topic:
                    raise RecordNotFoundError(f"Topic(id={topic_id}) not found")
                topic.hot_score = (topic.hot_score or 0) + delta
                topic.updated_at = datetime.now()
                session.add(topic)
                return True
        except RecordNotFoundError:
            raise
        except Exception as e:
            log.print_log(f"[TopicRepository] increment score failed: {e}", "error")
            raise DatabaseError("增加热度分数失败") from e

    def search_topics(self, keyword: str, limit: int = 20) -> List[Topic]:
        try:
            with self._get_session() as session:
                statement = (
                    select(Topic)
                    .where(Topic.title.contains(keyword))
                    .order_by(desc(Topic.hot_score))
                    .limit(limit)
                )
                return [self._dict_to_topic(self._topic_to_dict(topic)) for topic in session.exec(statement).all()]
        except Exception as e:
            log.print_log(f"[TopicRepository] search failed: {e}", "error")
            raise DatabaseError("搜索主题失败") from e

    def bulk_update_status(self, topic_ids: List[int], status: TopicStatus) -> int:
        try:
            with self._get_session() as session:
                updated_count = 0
                for topic_id in topic_ids:
                    topic = session.exec(select(Topic).where(Topic.id == topic_id)).first()
                    if topic:
                        topic.status = status
                        topic.updated_at = datetime.now()
                        session.add(topic)
                        updated_count += 1
                return updated_count
        except Exception as e:
            log.print_log(f"[TopicRepository] bulk update failed: {e}", "error")
            raise DatabaseError("批量更新主题状态失败") from e
