from typing import Dict, List, Optional, Tuple
from sortedcontainers import SortedDict
import uuid

from .order import Order, OrderType, OrderSide, OrderStatus, Trade


class OrderBook:
    """
    订单簿类 - 维护买卖订单的价格-数量映射

    使用价格优先、时间优先的撮合原则：
    - 买单按价格降序排列（高价优先）
    - 卖单按价格升序排列（低价优先）
    - 相同价格按时间优先
    """

    def __init__(self, symbol: str):
        """
        初始化订单簿

        Args:
            symbol: 股票代码
        """
        self.symbol = symbol

        # 买单：价格从高到低 (reverse=True)
        self.bidLevels: SortedDict = SortedDict(lambda px: -px)

        # 卖单：价格从低到高
        self.askLevels: SortedDict = SortedDict()

        # 订单ID到订单的映射
        self.orderMap: Dict[str, Order] = {}

        # 最新成交价
        self.lastPrice: Optional[float] = None

        # 成交历史
        self.tradeHistory: List[Trade] = []

    def addOrder(self, order: Order) -> List[Trade]:
        """
        添加订单到订单簿并尝试撮合

        Args:
            order: 订单对象

        Returns:
            成交记录列表
        """
        if order.symbol != self.symbol:
            raise ValueError(f"Order symbol {order.symbol} does not match orderbook symbol {self.symbol}")

        # 保存订单
        self.orderMap[order.orderId] = order

        # 尝试撮合
        trades = self._matchOrder(order)

        # 如果订单未完全成交且为限价单，加入订单簿
        if not order.isFilled and order.orderType == OrderType.LIMIT:
            self._addToBook(order)

        return trades

    def _matchOrder(self, order: Order) -> List[Trade]:
        """
        撮合订单

        Args:
            order: 待撮合的订单

        Returns:
            成交记录列表
        """
        trades = []

        if order.isBuy:
            # 买单：与卖单簿撮合
            while order.remainingQuantity > 0 and len(self.askLevels) > 0:
                askPrice = self.askLevels.keys()[0]

                # 检查价格是否匹配
                if order.orderType == OrderType.LIMIT and order.price < askPrice:
                    break

                askQueue = self.askLevels[askPrice]

                if not askQueue:
                    # 清理空价位
                    del self.askLevels[askPrice]
                    continue

                # 与第一个订单撮合（时间优先）
                opponentOrder = askQueue[0]
                trade = self._executeTrade(order, opponentOrder, askPrice)
                trades.append(trade)

                # 如果对手单完全成交，从订单簿移除
                if opponentOrder.isFilled:
                    askQueue.pop(0)
                    if not askQueue:
                        del self.askLevels[askPrice]
        else:
            # 卖单：与买单簿撮合
            while order.remainingQuantity > 0 and len(self.bidLevels) > 0:
                bidPrice = self.bidLevels.keys()[0]

                # 检查价格是否匹配
                if order.orderType == OrderType.LIMIT and order.price > bidPrice:
                    break

                bidQueue = self.bidLevels[bidPrice]

                if not bidQueue:
                    # 清理空价位
                    del self.bidLevels[bidPrice]
                    continue

                # 与第一个订单撮合（时间优先）
                opponentOrder = bidQueue[0]
                trade = self._executeTrade(opponentOrder, order, bidPrice)
                trades.append(trade)

                # 如果对手单完全成交，从订单簿移除
                if opponentOrder.isFilled:
                    bidQueue.pop(0)
                    if not bidQueue:
                        del self.bidLevels[bidPrice]

        return trades

    def _executeTrade(self, buyOrder: Order, sellOrder: Order, price: float) -> Trade:
        """
        执行成交

        Args:
            buy_order: 买单
            sell_order: 卖单
            price: 成交价格

        Returns:
            成交记录
        """
        # 成交数量为两个订单剩余数量的较小值
        quantity = min(buyOrder.remainingQuantity, sellOrder.remainingQuantity)

        # 更新订单状态
        buyOrder.fill(quantity)
        sellOrder.fill(quantity)

        # 更新最新成交价
        self.lastPrice = price

        # 创建成交记录
        trade = Trade(
            tradeId=str(uuid.uuid4()),
            symbol=self.symbol,
            buyOrderId=buyOrder.orderId,
            sellOrderId=sellOrder.orderId,
            buyerId=buyOrder.agentId,
            sellerId=sellOrder.agentId,
            price=price,
            quantity=quantity
        )

        self.tradeHistory.append(trade)
        return trade

    def _addToBook(self, order: Order) -> None:
        """
        将订单添加到订单簿

        Args:
            order: 订单对象
        """
        if order.price is None:
            raise ValueError("Cannot add market order to orderbook")

        queue = self.bidLevels if order.isBuy else self.askLevels
        if order.price not in queue:
            queue[order.price] = []
        queue[order.price].append(order)

    def cancelOrder(self, orderId: str) -> bool:
        """
        取消订单

        Args:
            orderId: 订单ID

        Returns:
            是否成功取消
        """
        if orderId not in self.orderMap:
            return False

        order = self.orderMap[orderId]

        if order.status in [OrderStatus.FILLED, OrderStatus.CANCELLED]:
            return False

        # 从订单簿移除
        queue = self.bidLevels if order.isBuy else self.askLevels
        if order.price in queue:
            ordersAtPrice = queue[order.price]
            if order in ordersAtPrice:
                ordersAtPrice.remove(order)
                if not ordersAtPrice:
                    del queue[order.price]

        # 更新订单状态
        order.cancel()
        return True

    def getBestBid(self) -> Optional[float]:
        """获取最优买价"""
        if len(self.bidLevels) == 0:
            return None
        return self.bidLevels.peekitem(0)[0]

    def getBestAsk(self) -> Optional[float]:
        """获取最优卖价"""
        if len(self.askLevels) == 0:
            return None
        return self.askLevels.peekitem(0)[0]

    def getMidPrice(self) -> Optional[float]:
        """获取中间价"""
        bestBid = self.getBestBid()
        bestAsk = self.getBestAsk()

        if bestBid is not None and bestAsk is not None:
            return (bestBid + bestAsk) / 2
        return None

    def getSpread(self) -> Optional[float]:
        """获取买卖价差"""
        bestBid = self.getBestBid()
        bestAsk = self.getBestAsk()

        if bestBid is not None and bestAsk is not None:
            return bestAsk - bestBid
        return None

    def getDepth(self, levels: int = 5) -> Tuple[List[Tuple[float, int]], List[Tuple[float, int]]]:
        """
        获取订单簿深度

        Args:
            levels: 返回的价格档位数量

        Returns:
            (买单深度, 卖单深度)，每个元素为(价格, 数量)元组
        """
        bids = []
        for levelIndex, price in enumerate(self.bidLevels.keys()):
            if levelIndex >= levels:
                break
            quantity = sum(order.remainingQuantity for order in self.bidLevels[price])
            bids.append((price, quantity))

        asks = []
        for levelIndex, price in enumerate(self.askLevels.keys()):
            if levelIndex >= levels:
                break
            quantity = sum(order.remainingQuantity for order in self.askLevels[price])
            asks.append((price, quantity))

        return bids, asks

    def estimateFillCost(self, side: OrderSide, quantity: int) -> Optional[float]:
        """根据当前盘口估算撮合指定数量需要的资金/收益。"""
        if quantity <= 0:
            return 0.0

        levelBook = self.askLevels if side == OrderSide.BUY else self.bidLevels
        remainingQuantity = quantity
        total = 0.0

        for price in levelBook.keys():
            if remainingQuantity <= 0:
                break
            levelQuantity = sum(order.remainingQuantity for order in levelBook[price])
            takeQuantity = min(remainingQuantity, levelQuantity)
            total += takeQuantity * price
            remainingQuantity -= takeQuantity

        if remainingQuantity > 0:
            return None

        return total

    def __repr__(self) -> str:
        bestBid = self.getBestBid()
        bestAsk = self.getBestAsk()
        return (f"OrderBook({self.symbol}, "
            f"bid={bestBid}, ask={bestAsk}, "
            f"last={self.lastPrice})")
