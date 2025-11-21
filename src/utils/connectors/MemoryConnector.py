from abc import ABC, abstractmethod
from typing import List

from agents.memory.memoryModels import MemoryEntry


class MemoryConnector(ABC):
    """
    基础 Connector 抽象，面向 ORM/NoSQL 的统一接口。
    """

    @abstractmethod
    def append(self, entry: MemoryEntry) -> None:
        raise NotImplementedError

    @abstractmethod
    def recent(self, agent_id: str, limit: int = 100) -> List[MemoryEntry]:
        raise NotImplementedError
