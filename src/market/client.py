from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Protocol, runtime_checkable

from .models.order import Order, OrderType, OrderSide, Trade
from .models.exchange import Exchange


@runtime_checkable
class MarketClient(Protocol):
    """Per-agent market interface used by trading strategies."""

    def account(self) -> Dict: ...
    def data(self, symbol: str) -> Dict: ...
    def order(
        self,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        quantity: int,
        price: Optional[float] = None,
    ) -> Tuple[Order, List[Trade]]: ...
    def trades(self, symbol: Optional[str] = None) -> List[Trade]: ...


@dataclass(slots=True)
class AgentClient:
    """Lightweight adapter that binds an `Exchange` to a specific agent."""

    exchange: Exchange
    agent_id: str

    def __post_init__(self) -> None:
        if not self.agent_id:
            raise ValueError("agent_id must be a non-empty string")

    def account(self) -> Dict:
        return self.exchange.getAccount(self.agent_id)

    def data(self, symbol: str) -> Dict:
        return self.exchange.getMarketData(symbol)

    def order(
        self,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        quantity: int,
        price: Optional[float] = None,
    ) -> Tuple[Order, List[Trade]]:
        return self.exchange.submitOrder(self.agent_id, symbol, order_type, side, quantity, price)

    def trades(self, symbol: Optional[str] = None) -> List[Trade]:
        return self.exchange.getTradeHistory(symbol=symbol, agentId=self.agent_id)
