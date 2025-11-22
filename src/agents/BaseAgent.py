"""
交易 Agent 基类（不包含任何 LLM 依赖）
"""

from typing import List, Dict, Any, Optional, TYPE_CHECKING
from abc import ABC, abstractmethod

from ..market.models.exchange import Exchange

if TYPE_CHECKING:
    from .memory.memoryStore import MemoryStore


class BaseAgent(ABC):
    """
    交易Agent基类

    所有交易Agent都应该继承这个类并实现step方法
    """

    def __init__(
        self,
        agentId: str,
        exchange: Exchange,
        symbols: List[str],
        memoryStore: Optional["MemoryStore"] = None,
    ):
        """
        初始化Agent

        Args:
            agentId: Agent唯一标识
            exchange: 交易所实例
            symbols: 交易的股票列表
        """
        self.agentId = agentId
        self.exchange = exchange
        self.symbols = symbols
        self.memoryStore = memoryStore

        # 内部状态
        self.stepCount = 0
        # 本地内存作为兜底缓存（存储与 MemoryEntry 兼容的结构）
        self.memory: List[Dict[str, Any]] = []
        self.eventBus = None

    @abstractmethod
    def step(self) -> None:
        """
        执行一个交易步骤

        这个方法会在每个仿真时间步被调用
        子类必须实现这个方法
        """
        pass

    def reset(self) -> None:
        """重置Agent状态"""
        self.stepCount = 0
        self.memory.clear()

    def getAccount(self) -> Dict[str, Any]:
        """获取账户信息"""
        return self.exchange.getAccount(self.agentId)

    def getMarketData(self, symbol: str) -> Dict[str, Any]:
        """获取市场数据"""
        return self.exchange.getMarketData(symbol)

    def logMessage(self, message: str, meta: Optional[Dict[str, Any]] = None) -> None:
        """
        记录日志，并尝试写入 MemoryStore。

        meta 可扩展上下文（如事件类型、符号、异常栈等），会被存成 MemoryEntry.metadata。
        """
        local_entry = {
            "step": self.stepCount,
            "msg": message,
        }
        if meta:
            local_entry["meta"] = meta
        self.memory.append(local_entry)

        if self.memoryStore:
            try:
                self.memoryStore.append(self.agentId, self.stepCount, message, meta)
            except Exception:
                # 存储失败不阻断仿真流程，保留本地缓存
                pass

    def recentMemory(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取最近的记忆（优先 MemoryStore，失败时回退本地缓存）。
        """
        if self.memoryStore:
            try:
                return self.memoryStore.recent(self.agentId, limit)
            except Exception:
                pass
        return self.memory[-limit:]

    def onEvent(self, event: Any) -> None:
        pass

    def onSnapshot(self, payload: Any) -> None:
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.agentId}, step={self.stepCount})"
