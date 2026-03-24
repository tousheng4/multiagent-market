"""
交易 Agent 基类（不包含任何 LLM 依赖）

Base class for trading agents (no LLM dependencies).
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ..market.models.exchange import Exchange
from ..utils.logger import setup_logger

if TYPE_CHECKING:
    from .memory.memoryStore import MemoryStore

logger = setup_logger(__name__)


class BaseAgent(ABC):
    """
    交易Agent基类 / Base class for trading agents

    所有交易Agent都应该继承这个类并实现step方法
    """

    def __init__(
        self,
        agent_id: str,
        exchange: Exchange,
        symbols: List[str],
        memory_store: Optional["MemoryStore"] = None,
    ):
        """
        初始化Agent / Initialize agent

        Args:
            agent_id: Agent唯一标识
            exchange: 交易所实例
            symbols: 交易的股票列表
            memory_store: 可选的记忆存储
        """
        self.agent_id = agent_id
        self.exchange = exchange
        self.symbols = symbols
        self.memory_store = memory_store

        # 内部状态
        self.step_count = 0
        # 本地内存作为兜底缓存（存储与 MemoryEntry 兼容的结构）
        self.memory: List[Dict[str, Any]] = []
        self.event_bus = None

    @abstractmethod
    def step(self) -> None:
        """
        执行一个交易步骤 / Execute one trading step

        这个方法会在每个仿真时间步被调用
        子类必须实现这个方法
        """
        pass

    def reset(self) -> None:
        """重置Agent状态 / Reset agent state"""
        self.step_count = 0
        self.memory.clear()

    def get_account(self) -> Dict[str, Any]:
        """获取账户信息 / Get account information"""
        return self.exchange.get_account(self.agent_id)

    def get_market_data(self, symbol: str) -> Dict[str, Any]:
        """获取市场数据 / Get market data"""
        return self.exchange.get_market_data(symbol)

    def log(self, message: str, meta: Optional[Dict[str, Any]] = None) -> None:
        """
        记录日志，并尝试写入 MemoryStore

        Log message and try to write to MemoryStore.

        meta 可扩展上下文（如事件类型、符号、异常栈等），会被存成 MemoryEntry.metadata
        """
        local_entry = {
            "step": self.step_count,
            "msg": message,
        }
        if meta:
            local_entry["meta"] = meta
        self.memory.append(local_entry)

        if self.memory_store:
            try:
                self.memory_store.append(self.agent_id, self.step_count, message, meta)
            except Exception as exc:
                logger.warning(f"Failed to write to memory store: {exc}")

    def recent_memory(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取最近的记忆（优先 MemoryStore，失败时回退本地缓存）

        Get recent memory (prefer MemoryStore, fallback to local cache).
        """
        if self.memory_store:
            try:
                return self.memory_store.recent(self.agent_id, limit)
            except Exception:
                pass
        return self.memory[-limit:]

    def on_event(self, event: Any) -> None:
        pass

    def on_snapshot(self, payload: Any) -> None:
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.agent_id}, step={self.step_count})"
