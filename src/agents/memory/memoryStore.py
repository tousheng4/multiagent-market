from datetime import datetime
from typing import Dict, List, Optional

from utils.connectors.MemoryConnector import MemoryConnector
from .memoryModels import MemoryEntry


class MemoryStore:
    def append(self, agentId: str, stepCount: int, message: str, meta: Optional[Dict] = None) -> None:
        raise NotImplementedError

    def recent_entries(self, agentId: str, limit: int = 100) -> List[MemoryEntry]:
        raise NotImplementedError

    def recent(self, agentId: str, limit: int = 100) -> List[Dict]:
        return [entry.as_read_dict() for entry in self.recent_entries(agentId, limit)]


class DualMemoryStore(MemoryStore):
    def __init__(self, redisConnector: Optional[MemoryConnector] = None, mongoConnector: Optional[MemoryConnector] = None):
        self.redisConnector = redisConnector
        self.mongoConnector = mongoConnector

    def append(self, agentId: str, stepCount: int, message: str, meta: Optional[Dict] = None) -> None:
        entry = MemoryEntry(
            agent_id=agentId,
            step=stepCount,
            message=message,
            metadata=meta or None,
            timestamp=datetime.utcnow(),
        )

        # Redis 作为高频缓存，ORM/Mongo 作为持久化
        if self.redisConnector:
            self.redisConnector.append(entry)
        if self.mongoConnector:
            self.mongoConnector.append(entry)

    def recent_entries(self, agentId: str, limit: int = 100) -> List[MemoryEntry]:
        # 优先从 Redis 读取，缺失时回退到持久化层
        entries: List[MemoryEntry] = []
        if self.redisConnector:
            entries = self.redisConnector.recent(agentId, limit)
        if not entries and self.mongoConnector:
            entries = self.mongoConnector.recent(agentId, limit)
        return entries[:limit]
