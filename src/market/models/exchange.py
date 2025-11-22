from typing import Dict, List, Optional, Tuple
import uuid

from .order import Order, OrderType, OrderSide, Trade
from .orderbook import OrderBook
from blinker import Namespace


class Exchange:
    """
    交易所类 - 管理多个股票的订单簿和撮合

    功能：
    - 管理多个股票的订单簿
    - 处理订单提交、撮合、取消
    - 管理Agent的持仓和现金
    - 记录交易历史
    """

    def __init__(self, initialCash: float = 100000.0):
        """
        初始化交易所

        Args:
            initialCash: 每个Agent的初始现金
        """
        self.initialCash = initialCash

        # 股票代码 -> 订单簿
        self.orderBooks: Dict[str, OrderBook] = {}

        # Agent ID -> 现金余额
        self.cashBalances: Dict[str, float] = {}

        # Agent ID -> {股票代码 -> 持仓数量}
        self.positionRecords: Dict[str, Dict[str, int]] = {}

        # 所有订单
        self.orderRecords: Dict[str, Order] = {}

        # 所有成交
        self.tradeRecords: List[Trade] = []

        # 当前时间步
        self.currentTime = 0
        # 事件命名空间（实例级）
        self._signal_ns = Namespace()
        self.sig_order_submitted = self._signal_ns.signal("order_submitted")
        self.sig_trade_executed = self._signal_ns.signal("trade_executed")

    def registerAgent(self, agentId: str, initialCash: Optional[float] = None) -> None:
        """
        注册Agent

        Args:
            agentId: Agent ID
            initialCash: 初始现金（如果不指定则使用默认值）
        """
        if agentId in self.cashBalances:
            raise ValueError(f"Agent {agentId} already registered")

        cashAmount = initialCash if initialCash is not None else self.initialCash
        self.cashBalances[agentId] = cashAmount
        self.positionRecords[agentId] = {}

    def addSymbol(self, symbol: str) -> None:
        """
        添加新的交易股票

        Args:
            symbol: 股票代码
        """
        if symbol not in self.orderBooks:
            self.orderBooks[symbol] = OrderBook(symbol)

    def submitOrder(
        self,
        agentId: str,
        symbol: str,
        orderType: OrderType,
        side: OrderSide,
        quantity: int,
        price: Optional[float] = None
    ) -> Tuple[Order, List[Trade]]:
        """
        提交订单
        Args:
            agentId: Agent ID
            symbol: 股票代码
            orderType: 订单类型
            side: 买卖方向
            quantity: 数量
            price: 价格（市价单为None）

        Returns:
            (订单对象, 成交列表)
        """
        if agentId not in self.cashBalances:
            raise ValueError(f"Agent {agentId} not registered")

        if symbol not in self.orderBooks:
            raise ValueError(f"Symbol {symbol} not found")

        order = Order(
            orderId=str(uuid.uuid4()),
            agentId=agentId,
            symbol=symbol,
            orderType=orderType,
            side=side,
            quantity=quantity,
            price=price,
            timestamp=self.currentTime
        )

        if not self._riskCheck(order):
            raise ValueError(f"Risk check failed for order {order}")

        self.orderRecords[order.orderId] = order

        book = self.orderBooks[symbol]
        trades = book.addOrder(order)

        for trade in trades:
            trade.timestamp = float(self.currentTime)
            self._settleTrade(trade)
            try:
                self.sig_trade_executed.send(self, trade=trade)
            except Exception as e:
                print(f"Trade event dispatch error: {e}")

        self.tradeRecords.extend(trades)
        try:
            self.sig_order_submitted.send(self, order=order)
        except Exception as e:
            print(f"Order event dispatch error: {e}")

        return order, trades

    def _riskCheck(self, order: Order) -> bool:
        """
        风控检查

        Args:
            order: 订单

        Returns:
            是否通过检查
        """
        agentId = order.agentId

        if order.isBuy:
            requiredCash = self._estimateBuyCash(order)
            if requiredCash is None:
                return False

            if self.cashBalances[agentId] < requiredCash:
                return False
        else:
            positionQuantity = self.positionRecords[agentId].get(order.symbol, 0)
            if positionQuantity < order.quantity:
                return False

        return True

    def _estimateBuyCash(self, order: Order) -> Optional[float]:
        """估算买单需要的现金，市价单会逐档遍历盘口。"""
        if order.orderType == OrderType.LIMIT:
            if order.price is None:
                return None
            return order.price * order.quantity

        book = self.orderBooks[order.symbol]
        return book.estimateFillCost(OrderSide.BUY, order.quantity)

    def _settleTrade(self, trade: Trade) -> None:
        """
        结算成交

        Args:
            trade: 成交记录
        """
        buyer = trade.buyerId
        seller = trade.sellerId
        symbol = trade.symbol
        tradeQuantity = trade.quantity
        grossValue = trade.price * tradeQuantity

        # 更新现金
        self.cashBalances[buyer] -= grossValue
        self.cashBalances[seller] += grossValue

        # 更新持仓
        if symbol not in self.positionRecords[buyer]:
            self.positionRecords[buyer][symbol] = 0
        if symbol not in self.positionRecords[seller]:
            self.positionRecords[seller][symbol] = 0

        self.positionRecords[buyer][symbol] += tradeQuantity
        self.positionRecords[seller][symbol] -= tradeQuantity

    def cancelOrder(self, orderId: str) -> bool:
        """
        取消订单

        Args:
            orderId: 订单ID

        Returns:
            是否成功取消
        """
        if orderId not in self.orderRecords:
            return False

        order = self.orderRecords[orderId]
        book = self.orderBooks[order.symbol]
        return book.cancelOrder(orderId)

    def getOrderBook(self, symbol: str) -> Optional[OrderBook]:
        """获取指定股票的订单簿"""
        return self.orderBooks.get(symbol)

    def getAccount(self, agentId: str) -> Dict:
        """
        获取Agent账户信息

        Args:
            agentId: Agent ID

        Returns:
            账户信息字典
        """
        if agentId not in self.cashBalances:
            raise ValueError(f"Agent {agentId} not found")

        return {
            "cash": self.cashBalances[agentId],
            "positions": self.positionRecords[agentId].copy(),
            "portfolio_value": self._calculatePortfolioValue(agentId)
        }

    def _calculatePortfolioValue(self, agentId: str) -> float:
        """
        计算Agent的总资产价值

        Args:
            agentId: Agent ID

        Returns:
            总资产价值
        """
        totalValue = self.cashBalances[agentId]

        for symbol, quantity in self.positionRecords[agentId].items():
            if quantity == 0:
                continue

            book = self.orderBooks[symbol]

            # 使用中间价估值
            midPrice = book.getMidPrice()
            if midPrice is None:
                # 如果没有中间价，使用最新成交价
                midPrice = book.lastPrice

            if midPrice is not None:
                totalValue += quantity * midPrice

        return totalValue

    def getMarketData(self, symbol: str) -> Dict:
        """
        获取市场数据

        Args:
            symbol: 股票代码

        Returns:
            市场数据字典
        """
        if symbol not in self.orderBooks:
            raise ValueError(f"Symbol {symbol} not found")

        book = self.orderBooks[symbol]
        bids, asks = book.getDepth(levels=5)

        return {
            "symbol": symbol,
            "best_bid": book.getBestBid(),
            "best_ask": book.getBestAsk(),
            "mid_price": book.getMidPrice(),
            "spread": book.getSpread(),
            "last_price": book.lastPrice,
            "bids": bids,
            "asks": asks,
            "timestamp": self.currentTime
        }

    def step(self) -> None:
        """时间步进"""
        self.currentTime += 1

    def updateMarketPrice(self, symbol: str, price: float) -> None:
        """外部数据源更新最新成交价，用于数据管线驱动行情。"""
        if symbol not in self.orderBooks:
            raise ValueError(f"Symbol {symbol} not found")
        self.orderBooks[symbol].lastPrice = float(price)

    def getTradeHistory(self, symbol: Optional[str] = None, agentId: Optional[str] = None) -> List[Trade]:
        """
        获取成交历史

        Args:
            symbol: 股票代码（可选）
            agentId: Agent ID（可选）

        Returns:
            成交记录列表
        """
        trades = self.tradeRecords

        if symbol is not None:
            trades = [t for t in trades if t.symbol == symbol]

        if agentId is not None:
            trades = [t for t in trades if t.buyerId == agentId or t.sellerId == agentId]

        return trades

    def __repr__(self) -> str:
        return (f"Exchange(symbols={list(self.orderBooks.keys())}, "
            f"agents={len(self.cashBalances)}, "
            f"trades={len(self.tradeRecords)})")
