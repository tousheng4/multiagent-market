from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class MemoryEntry:
    """
    标准化的记忆条目结构，方便在不同 Connector/ORM 之间互通。
    """

    agent_id: str
    step: int
    message: str
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_storage_record(self, include_datetime: bool = False) -> Dict[str, Any]:
        """
        扁平化的存储格式，适合 Redis/Mongo/ORM 等无 schema 存储。
        """
        payload: Dict[str, Any] = {
            "agentId": self.agent_id,
            "step": self.step,
            "msg": self.message,
            "ts": self.timestamp.timestamp(),
        }
        if self.metadata:
            payload.update(self.metadata)
        if include_datetime:
            payload["timestamp"] = self.timestamp
        return payload

    def as_read_dict(self) -> Dict[str, Any]:
        """
        对外展示使用的格式，保留 ts（秒）并补充可读字符串时间戳。
        """
        payload = self.to_storage_record(include_datetime=False)
        payload["timestamp"] = self.timestamp.isoformat()
        return payload

    @classmethod
    def from_record(cls, payload: Dict[str, Any]) -> "MemoryEntry":
        agent_id = payload.get("agentId") or payload.get("agent_id") or ""
        step_value = payload.get("step", payload.get("stepCount", 0))
        message = payload.get("msg") or payload.get("message") or ""
        raw_ts = payload.get("timestamp", payload.get("ts"))

        if isinstance(raw_ts, datetime):
            timestamp = raw_ts
        else:
            try:
                timestamp = (
                    datetime.fromtimestamp(float(raw_ts))
                    if raw_ts is not None
                    else datetime.utcnow()
                )
            except Exception:
                timestamp = datetime.utcnow()

        meta_keys = {
            "agentId",
            "agent_id",
            "step",
            "stepCount",
            "msg",
            "message",
            "ts",
            "timestamp",
            "_id",
        }
        metadata = {k: v for k, v in payload.items() if k not in meta_keys}

        try:
            step_int = int(step_value)
        except Exception:
            step_int = 0

        return cls(
            agent_id=agent_id,
            step=step_int,
            message=str(message),
            metadata=metadata or None,
            timestamp=timestamp,
        )
