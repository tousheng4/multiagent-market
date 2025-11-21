from typing import Any, List
import json

from .MemoryConnector import MemoryConnector
from agents.memory.memoryModels import MemoryEntry


class RedisConnector(MemoryConnector):
    """
    Redis 版 Connector，支持窗口裁剪和 MemoryEntry 序列化。
    """

    def __init__(self, client: Any, window: int = 500, key_prefix: str = "agent"):
        self.client = client
        self.window = window
        self.key_prefix = key_prefix.rstrip(":")

    def append(self, entry: MemoryEntry) -> None:
        key = f"{self.key_prefix}:{entry.agent_id}:memory"
        payload = entry.to_storage_record(include_datetime=False)
        encoded = json.dumps(payload, separators=(",", ":"))
        self.client.lpush(key, encoded)
        self.client.ltrim(key, 0, self.window - 1)

    def recent(self, agent_id: str, limit: int = 100) -> List[MemoryEntry]:
        key = f"{self.key_prefix}:{agent_id}:memory"
        items = self.client.lrange(key, 0, limit - 1)
        result: List[MemoryEntry] = []
        for i in items:
            s = i.decode("utf-8") if isinstance(i, (bytes, bytearray)) else str(i)
            try:
                record = json.loads(s)
                result.append(MemoryEntry.from_record(record))
            except Exception:
                continue
        return result
