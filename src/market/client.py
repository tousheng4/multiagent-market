from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol, Tuple, runtime_checkable

from .models.exchange import Exchange
from .models.order import Order, OrderSide, OrderType, Trade


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
    def order_cmd(
        self,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        quantity: int,
        price: Optional[float] = None,
        cmd_id: Optional[str] = None,
    ) -> str: ...
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
        return self.exchange.get_account(self.agent_id)

    def data(self, symbol: str) -> Dict:
        return self.exchange.get_market_data(symbol)

    def order(
        self,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        quantity: int,
        price: Optional[float] = None,
    ) -> Tuple[Order, List[Trade]]:
        return self.exchange.submit_order(
            self.agent_id, symbol, order_type, side, quantity, price
        )

    def order_cmd(
        self,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        quantity: int,
        price: Optional[float] = None,
        cmd_id: Optional[str] = None,
    ) -> str:
        return self.exchange.publish_order_cmd(
            self.agent_id,
            symbol,
            order_type,
            side,
            quantity,
            price,
            cmd_id,
        )

    def trades(self, symbol: Optional[str] = None) -> List[Trade]:
        return self.exchange.get_trade_history(symbol=symbol, agent_id=self.agent_id)
