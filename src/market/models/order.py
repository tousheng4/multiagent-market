from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class OrderType(Enum):
    """订单类型 / Order type"""

    MARKET = "market"  # 市价单
    LIMIT = "limit"  # 限价单


class OrderSide(Enum):
    """订单方向 / Order side"""

    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """订单状态 / Order status"""

    PENDING = "pending"  # 待处理
    PARTIAL = "partial"  # 部分成交
    FILLED = "filled"  # 完全成交
    CANCELLED = "cancelled"  # 已取消


@dataclass
class Order:
    """
    订单类 / Order class

    Attributes:
        order_id: 订单唯一ID
        agent_id: 下单Agent的ID
        symbol: 股票代码
        order_type: 订单类型（市价/限价）
        side: 买卖方向
        quantity: 订单数量
        price: 价格（市价单时为None）
        timestamp: 下单时间戳
        status: 订单状态
        filled_quantity: 已成交数量
    """

    order_id: str
    agent_id: str
    symbol: str
    order_type: OrderType
    side: OrderSide
    quantity: int
    price: Optional[float] = None
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0

    def __post_init__(self):
        """初始化后处理 / Post-initialization validation"""
        if self.timestamp is None:
            self.timestamp = datetime.now().timestamp()

        # 限价单必须有价格
        if self.order_type == OrderType.LIMIT:
            if self.price is None:
                raise ValueError("Limit order must have a price")
            if self.price <= 0:
                raise ValueError("Limit order price must be positive")

        # 验证数量为正
        if self.quantity <= 0:
            raise ValueError("Order quantity must be positive")

    @property
    def remaining_quantity(self) -> int:
        """剩余未成交数量 / Remaining unfilled quantity"""
        return self.quantity - self.filled_quantity

    @property
    def is_buy(self) -> bool:
        """是否为买单 / Is buy order"""
        return self.side == OrderSide.BUY

    @property
    def is_sell(self) -> bool:
        """是否为卖单 / Is sell order"""
        return self.side == OrderSide.SELL

    @property
    def is_filled(self) -> bool:
        """是否完全成交 / Is completely filled"""
        return self.filled_quantity >= self.quantity

    def fill(self, qty_to_fill: int) -> None:
        """
        成交指定数量 / Fill specified quantity

        Args:
            qty_to_fill: 成交数量
        """
        if qty_to_fill <= 0:
            raise ValueError("Fill quantity must be positive")

        if self.filled_quantity + qty_to_fill > self.quantity:
            raise ValueError("Fill quantity exceeds remaining quantity")

        self.filled_quantity += qty_to_fill

        # 更新状态
        if self.is_filled:
            self.status = OrderStatus.FILLED
        else:
            self.status = OrderStatus.PARTIAL

    def cancel(self) -> None:
        """取消订单 / Cancel order"""
        if self.status == OrderStatus.FILLED:
            raise ValueError("Cannot cancel filled order")
        self.status = OrderStatus.CANCELLED

    def __repr__(self) -> str:
        price_label = f"@{self.price}" if self.price is not None else "MARKET"
        return (
            f"Order({self.order_id}, {self.agent_id}, {self.side.value} "
            f"{self.quantity} {self.symbol} {price_label}, "
            f"filled={self.filled_quantity}, status={self.status.value})"
        )


@dataclass
class Trade:
    """
    成交记录 / Trade record

    Attributes:
        trade_id: 成交ID
        symbol: 股票代码
        buy_order_id: 买单ID
        sell_order_id: 卖单ID
        buyer_id: 买方Agent ID
        seller_id: 卖方Agent ID
        price: 成交价格
        quantity: 成交数量
        timestamp: 成交时间戳
    """

    trade_id: str
    symbol: str
    buy_order_id: str
    sell_order_id: str
    buyer_id: str
    seller_id: str
    price: float
    quantity: int
    timestamp: Optional[float] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().timestamp()

    def __repr__(self) -> str:
        return (
            f"Trade({self.trade_id}, {self.symbol}, "
            f"{self.quantity}@{self.price}, "
            f"{self.buyer_id}<->{self.seller_id})"
        )
