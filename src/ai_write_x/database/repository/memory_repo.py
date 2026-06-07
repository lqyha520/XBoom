# -*- coding: UTF-8 -*-
"""
记忆仓储 - Memory Repository
提供 Agent 记忆相关的数据库操作。
"""

from contextlib import contextmanager
from typing import List, Dict, Any
from datetime import datetime, timedelta
from sqlmodel import select, desc, func

from src.ai_write_x.database import AgentMemory, get_session
from src.ai_write_x.database.repository.base import BaseRepository, _SessionAdapter
from src.ai_write_x.core.exceptions import DatabaseError
from src.ai_write_x.utils import log


class MemoryRepository(BaseRepository[AgentMemory]):
    """Agent memory repository."""

    @property
    def model(self) -> type[AgentMemory]:
        return AgentMemory

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

    def add(self, content: str, memory_type: str = "fact", agent_id: str = "unknown", **kwargs) -> AgentMemory:
        return self.create_memory(
            agent_id=agent_id,
            memory_type=memory_type,
            content=content,
            **kwargs,
        )

    def create_memory(
        self,
        agent_id: str,
        memory_type: str,
        content: str,
        metadata: Dict[str, Any] = None,
        **kwargs,
    ) -> AgentMemory:
        try:
            with self._get_session() as session:
                memory = AgentMemory(
                    agent_id=agent_id,
                    agent_role=kwargs.pop("agent_role", agent_id),
                    memory_type=memory_type,
                    content=content,
                    memory_text=kwargs.pop("memory_text", content),
                    metadata_json=kwargs.pop("metadata_json", None),
                    **kwargs,
                )
                if metadata is not None and memory.metadata_json is None:
                    import json
                    memory.metadata_json = json.dumps(metadata, ensure_ascii=False)
                session.add(memory)
                session.flush()
                return self._from_dict(self._to_dict(memory))
        except DatabaseError:
            raise
        except Exception as e:
            log.print_log(f"[MemoryRepository] create memory failed: {e}", "error")
            raise DatabaseError("创建记忆失败") from e

    def get_by_agent(self, agent_id: str, memory_type: str = None, limit: int = 50) -> List[AgentMemory]:
        try:
            with self._get_session() as session:
                statement = select(AgentMemory).where(AgentMemory.agent_id == agent_id)
                if memory_type:
                    statement = statement.where(AgentMemory.memory_type == memory_type)
                statement = statement.order_by(desc(AgentMemory.created_at)).limit(limit)
                return list(session.exec(statement).all())
        except Exception as e:
            log.print_log(f"[MemoryRepository] get memories failed: {e}", "error")
            raise DatabaseError("获取记忆失败") from e

    def get_recent_memories(self, hours: int = 24, limit: int = 100) -> List[AgentMemory]:
        try:
            with self._get_session() as session:
                cutoff = datetime.now() - timedelta(hours=hours)
                statement = (
                    select(AgentMemory)
                    .where(AgentMemory.created_at >= cutoff)
                    .order_by(desc(AgentMemory.created_at))
                    .limit(limit)
                )
                return list(session.exec(statement).all())
        except Exception as e:
            log.print_log(f"[MemoryRepository] get recent memories failed: {e}", "error")
            raise DatabaseError("获取最近记忆失败") from e

    def search_memories(self, agent_id: str, keyword: str, limit: int = 20) -> List[AgentMemory]:
        try:
            with self._get_session() as session:
                statement = (
                    select(AgentMemory)
                    .where(AgentMemory.agent_id == agent_id)
                    .where(AgentMemory.content.contains(keyword))
                    .order_by(desc(AgentMemory.created_at))
                    .limit(limit)
                )
                return list(session.exec(statement).all())
        except Exception as e:
            log.print_log(f"[MemoryRepository] search memories failed: {e}", "error")
            raise DatabaseError("搜索记忆失败") from e

    def get_statistics(self) -> Dict[str, Any]:
        try:
            with self._get_session() as session:
                total = session.exec(select(func.count(AgentMemory.id))).first() or 0
                type_results = session.exec(
                    select(AgentMemory.memory_type, func.count(AgentMemory.id)).group_by(AgentMemory.memory_type)
                ).all()
                agent_results = session.exec(
                    select(AgentMemory.agent_id, func.count(AgentMemory.id)).group_by(AgentMemory.agent_id)
                ).all()
                return {
                    "total": total,
                    "by_type": {mtype: count for mtype, count in type_results},
                    "by_agent": {aid: count for aid, count in agent_results},
                }
        except Exception as e:
            log.print_log(f"[MemoryRepository] statistics failed: {e}", "error")
            raise DatabaseError("获取记忆统计失败") from e

    def delete_by_agent(self, agent_id: str) -> int:
        try:
            with self._get_session() as session:
                result = session.exec(AgentMemory.__table__.delete().where(AgentMemory.agent_id == agent_id))
                return result.rowcount
        except Exception as e:
            log.print_log(f"[MemoryRepository] delete by agent failed: {e}", "error")
            raise DatabaseError("删除记忆失败") from e

    def cleanup_old_memories(self, days: int = 30) -> int:
        try:
            with self._get_session() as session:
                cutoff = datetime.now() - timedelta(days=days)
                result = session.exec(AgentMemory.__table__.delete().where(AgentMemory.created_at < cutoff))
                return result.rowcount
        except Exception as e:
            log.print_log(f"[MemoryRepository] cleanup memories failed: {e}", "error")
            raise DatabaseError("清理旧记忆失败") from e
