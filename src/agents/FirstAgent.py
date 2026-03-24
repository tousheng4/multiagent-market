"""
第一个基于LLM的交易Agent

这个Agent会根据LLM的输出进行交易
"""

from ..market.exchange import Exchange
from .BaseAgent import BaseAgent


class FirstAgent(BaseAgent):
    """第一个基于LLM的交易Agent"""

    def __init__(
        self,
        agentId: str,
        exchange: Exchange,
        symbols: List[str],
        memoryStore: Optional["MemoryStore"] = None,
    ):
        super().__init__(agentId, exchange, symbols, memoryStore)

    def step(self) -> None:
        """执行一次交易"""
        self.stepCount += 1
