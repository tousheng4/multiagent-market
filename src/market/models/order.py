from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


class OrderType(Enum):
    """订单类型"""
    MARKET = "market"  # 市价单
    LIMIT = "limit"    # 限价单


class OrderSide(Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"      # 待处理
    PARTIAL = "partial"      # 部分成交
    FILLED = "filled"        # 完全成交
    CANCELLED = "cancelled"  # 已取消


@dataclass
class Order:
    """
    订单类

    Attributes:
        orderId: 订单唯一ID
        agentId: 下单Agent的ID
        symbol: 股票代码
        orderType: 订单类型（市价/限价）
        side: 买卖方向
        quantity: 订单数量
        price: 价格（市价单时为None）
        timestamp: 下单时间戳
        status: 订单状态
        filledQuantity: 已成交数量
    """
    orderId: str
    agentId: str
    symbol: str
    orderType: OrderType
    side: OrderSide
    quantity: int
    price: Optional[float] = None
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    status: OrderStatus = OrderStatus.PENDING
    filledQuantity: int = 0

    def __post_init__(self):
        """初始化后处理"""
        if self.timestamp is None:
            self.timestamp = datetime.now().timestamp()

        # 限价单必须有价格
        if self.orderType == OrderType.LIMIT:
            if self.price is None:
                raise ValueError("Limit order must have a price")
            if self.price <= 0:
                raise ValueError("Limit order price must be positive")

        # 验证数量为正
        if self.quantity <= 0:
            raise ValueError("Order quantity must be positive")

    @property
    def remainingQuantity(self) -> int:
        """剩余未成交数量"""
        return self.quantity - self.filledQuantity

    @property
    def isBuy(self) -> bool:
        """是否为买单"""
        return self.side == OrderSide.BUY

    @property
    def isSell(self) -> bool:
        """是否为卖单"""
        return self.side == OrderSide.SELL

    @property
    def isFilled(self) -> bool:
        """是否完全成交"""
        return self.filledQuantity >= self.quantity

    def fill(self, quantityToFill: int) -> None:
        """
        成交指定数量

        Args:
            quantityToFill: 成交数量
        """
        if quantityToFill <= 0:
            raise ValueError("Fill quantity must be positive")

        if self.filledQuantity + quantityToFill > self.quantity:
            raise ValueError("Fill quantity exceeds remaining quantity")

        self.filledQuantity += quantityToFill

        # 更新状态
        if self.isFilled:
            self.status = OrderStatus.FILLED
        else:
            self.status = OrderStatus.PARTIAL

    def cancel(self) -> None:
        """取消订单"""
        if self.status == OrderStatus.FILLED:
            raise ValueError("Cannot cancel filled order")
        self.status = OrderStatus.CANCELLED

    def __repr__(self) -> str:
        priceLabel = f"@{self.price}" if self.price is not None else "MARKET"
        return (f"Order({self.orderId}, {self.agentId}, {self.side.value} "
            f"{self.quantity} {self.symbol} {priceLabel}, "
            f"filled={self.filledQuantity}, status={self.status.value})")


@dataclass
class Trade:
    """
    成交记录

    Attributes:
        tradeId: 成交ID
        symbol: 股票代码
        buyOrderId: 买单ID
        sellOrderId: 卖单ID
        buyerId: 买方Agent ID
        sellerId: 卖方Agent ID
        price: 成交价格
        quantity: 成交数量
        timestamp: 成交时间戳
    """
    tradeId: str
    symbol: str
    buyOrderId: str
    sellOrderId: str
    buyerId: str
    sellerId: str
    price: float
    quantity: int
    timestamp: float = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().timestamp()

    def __repr__(self) -> str:
        return (f"Trade({self.tradeId}, {self.symbol}, "
            f"{self.quantity}@{self.price}, "
            f"{self.buyerId}<->{self.sellerId})")
