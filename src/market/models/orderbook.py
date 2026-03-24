import math
import uuid
from collections import deque
from typing import Dict, List, Optional, Tuple

from sortedcontainers import SortedDict

from ...config import CONFIG
from .order import Order, OrderSide, OrderStatus, OrderType, Trade


class OrderBook:
    """
    订单簿类 - 维护买卖订单的价格-数量映射

    OrderBook - maintains price-quantity mapping for buy/sell orders

    使用价格优先、时间优先的撮合原则：
    - 买单按价格降序排列（高价优先）
    - 卖单按价格升序排列（低价优先）
    - 相同价格按时间优先
    """

    def __init__(self, symbol: str):
        """
        初始化订单簿 / Initialize orderbook

        Args:
            symbol: 股票代码
        """
        self.symbol = symbol
        self.tick_size = CONFIG.orderbook.default_tick_size

        # 买单：价格从高到低 (reverse=True)
        self.bid_levels: SortedDict = SortedDict(lambda px: -px)

        # 卖单：价格从低到高
        self.ask_levels: SortedDict = SortedDict()

        # 订单ID到订单的映射
        self.order_map: Dict[str, Order] = {}

        # 最新成交价
        self.last_price: Optional[float] = None

        # 成交历史
        self.trade_history: List[Trade] = []

        # 性能优化：缓存每个价格档位的总量
        if CONFIG.orderbook.enable_qty_cache:
            self._qty_cache: Dict[Tuple[str, int], int] = {}  # (side, ticks) -> qty
            self._cache_enabled = True
        else:
            self._cache_enabled = False

    def add_order(self, order: Order) -> List[Trade]:
        """
        添加订单到订单簿并尝试撮合

        Add order to orderbook and attempt matching

        Args:
            order: 订单对象

        Returns:
            成交记录列表
        """
        if order.symbol != self.symbol:
            raise ValueError(
                f"Order symbol {order.symbol} does not match orderbook symbol {self.symbol}"
            )

        # 保存订单
        self.order_map[order.order_id] = order

        # 尝试撮合
        trades = self._match_order(order)

        if order.is_filled:
            return trades

        if order.order_type == OrderType.LIMIT:
            # 限价单挂入簿等待后续撮合
            self._add_to_book(order)
        else:
            # 市价单采取 IOC：未成交部分立即取消
            order.cancel()
            self.order_map.pop(order.order_id, None)

        return trades

    def _match_order(self, order: Order) -> List[Trade]:
        """
        撮合订单 / Match order

        Args:
            order: 待撮合的订单

        Returns:
            成交记录列表
        """
        trades = []

        if order.is_buy:
            # 买单：与卖单簿撮合
            while order.remaining_quantity > 0 and len(self.ask_levels) > 0:
                ask_ticks = self.ask_levels.keys()[0]
                ask_price = ask_ticks * self.tick_size

                # 检查价格是否匹配
                if order.order_type == OrderType.LIMIT:
                    order_ticks = self._ticking(order.price, OrderSide.BUY)
                    if order_ticks < ask_ticks:
                        break

                ask_queue = self.ask_levels[ask_ticks]

                if not ask_queue:
                    # 清理空价位
                    del self.ask_levels[ask_ticks]
                    continue

                # 与第一个订单撮合（时间优先）
                opponent_order = ask_queue[0]
                trade = self._execute_trade(order, opponent_order, ask_price)
                trades.append(trade)

                # 如果对手单完全成交，从订单簿移除
                if opponent_order.is_filled:
                    ask_queue.popleft()
                    if not ask_queue:
                        del self.ask_levels[ask_ticks]
                    # 使缓存失效
                    self._invalidate_cache("ask", ask_ticks)
        else:
            # 卖单：与买单簿撮合
            while order.remaining_quantity > 0 and len(self.bid_levels) > 0:
                bid_ticks = self.bid_levels.keys()[0]
                bid_price = bid_ticks * self.tick_size

                # 检查价格是否匹配
                if order.order_type == OrderType.LIMIT:
                    order_ticks = self._ticking(order.price, OrderSide.SELL)
                    if order_ticks > bid_ticks:
                        break

                bid_queue = self.bid_levels[bid_ticks]

                if not bid_queue:
                    # 清理空价位
                    del self.bid_levels[bid_ticks]
                    continue

                # 与第一个订单撮合（时间优先）
                opponent_order = bid_queue[0]
                trade = self._execute_trade(opponent_order, order, bid_price)
                trades.append(trade)

                # 如果对手单完全成交，从订单簿移除
                if opponent_order.is_filled:
                    bid_queue.popleft()
                    if not bid_queue:
                        del self.bid_levels[bid_ticks]
                    # 使缓存失效
                    self._invalidate_cache("bid", bid_ticks)

        return trades

    def _execute_trade(
        self, buy_order: Order, sell_order: Order, price: float
    ) -> Trade:
        """
        执行成交 / Execute trade

        Args:
            buy_order: 买单
            sell_order: 卖单
            price: 成交价格

        Returns:
            成交记录
        """
        # 成交数量为两个订单剩余数量的较小值
        quantity = min(buy_order.remaining_quantity, sell_order.remaining_quantity)

        # 更新订单状态
        buy_order.fill(quantity)
        sell_order.fill(quantity)

        # 更新最新成交价
        self.last_price = price

        # 创建成交记录
        trade = Trade(
            trade_id=str(uuid.uuid4()),
            symbol=self.symbol,
            buy_order_id=buy_order.order_id,
            sell_order_id=sell_order.order_id,
            buyer_id=buy_order.agent_id,
            seller_id=sell_order.agent_id,
            price=price,
            quantity=quantity,
        )

        self.trade_history.append(trade)
        if buy_order.is_filled:
            self.order_map.pop(buy_order.order_id, None)
        if sell_order.is_filled:
            self.order_map.pop(sell_order.order_id, None)
        return trade

    def _add_to_book(self, order: Order) -> None:
        """
        将订单添加到订单簿 / Add order to book

        Args:
            order: 订单对象
        """
        if order.price is None:
            raise ValueError("Cannot add market order to orderbook")

        ticks = self._ticking(order.price, order.side)
        queue = self.bid_levels if order.is_buy else self.ask_levels

        if ticks not in queue:
            queue[ticks] = deque()
        queue[ticks].append(order)

        # 使缓存失效
        side = "bid" if order.is_buy else "ask"
        self._invalidate_cache(side, ticks)

    def cancel_order(self, order_id: str) -> bool:
        """
        取消订单 / Cancel order

        Args:
            order_id: 订单ID

        Returns:
            是否成功取消
        """
        if order_id not in self.order_map:
            return False

        order = self.order_map[order_id]

        if order.status in [OrderStatus.FILLED, OrderStatus.CANCELLED]:
            return False

        if order.price is None:
            # 市价单不会留在簿上，直接提示不可撤并清理记录
            self.order_map.pop(order_id, None)
            raise ValueError(
                "Cannot cancel market order with no price (IOC orders are not persisted)"
            )

        # 从订单簿移除 (O(n) operation - 可优化)
        queue = self.bid_levels if order.is_buy else self.ask_levels
        ticks = self._ticking(order.price, order.side)

        if ticks in queue:
            orders_at_price = queue[ticks]
            if order in orders_at_price:
                orders_at_price.remove(order)
                if not orders_at_price:
                    del queue[ticks]
                # 使缓存失效
                side = "bid" if order.is_buy else "ask"
                self._invalidate_cache(side, ticks)

        # 更新订单状态
        order.cancel()
        self.order_map.pop(order_id, None)
        return True

    @property
    def best_bid(self) -> Optional[float]:
        """获取最优买价 / Get best bid price"""
        if len(self.bid_levels) == 0:
            return None
        best_bid_ticks = self.bid_levels.peekitem(0)[0]
        return best_bid_ticks * self.tick_size

    @property
    def best_ask(self) -> Optional[float]:
        """获取最优卖价 / Get best ask price"""
        if len(self.ask_levels) == 0:
            return None
        best_ask_ticks = self.ask_levels.peekitem(0)[0]
        return best_ask_ticks * self.tick_size

    @property
    def mid_price(self) -> Optional[float]:
        """获取中间价 / Get mid price"""
        if self.best_bid is not None and self.best_ask is not None:
            return (self.best_bid + self.best_ask) / 2
        return None

    @property
    def spread(self) -> Optional[float]:
        """获取买卖价差 / Get bid-ask spread"""
        if self.best_bid is not None and self.best_ask is not None:
            return self.best_ask - self.best_bid
        return None

    def get_depth(
        self, levels: int = 5
    ) -> Tuple[List[Tuple[float, int]], List[Tuple[float, int]]]:
        """
        获取订单簿深度 / Get orderbook depth

        Args:
            levels: 返回的价格档位数量

        Returns:
            (买单深度, 卖单深度)，每个元素为(价格, 数量)元组
        """
        bids = []
        for level_index, ticks in enumerate(self.bid_levels.keys()):
            if level_index >= levels:
                break
            quantity = self._get_level_qty("bid", self.bid_levels, ticks)
            price = ticks * self.tick_size
            bids.append((price, quantity))

        asks = []
        for level_index, ticks in enumerate(self.ask_levels.keys()):
            if level_index >= levels:
                break
            quantity = self._get_level_qty("ask", self.ask_levels, ticks)
            price = ticks * self.tick_size
            asks.append((price, quantity))

        return bids, asks

    def estimate_cost(self, side: OrderSide, quantity: int) -> Optional[float]:
        """
        根据当前盘口估算撮合指定数量需要的资金/收益

        Estimate the cost/proceeds of matching given quantity at current market
        """
        if quantity <= 0:
            return 0.0

        level_book = self.ask_levels if side == OrderSide.BUY else self.bid_levels
        remaining_qty = quantity
        total = 0.0

        for ticks in level_book.keys():
            if remaining_qty <= 0:
                break
            level_qty = self._get_level_qty(
                "ask" if side == OrderSide.BUY else "bid", level_book, ticks
            )
            take_qty = min(remaining_qty, level_qty)
            price = ticks * self.tick_size
            total += take_qty * price
            remaining_qty -= take_qty

        if remaining_qty > 0:
            return None

        return total

    def _ticking(self, price: Optional[float], side: OrderSide) -> int:
        """
        将价格按 tickSize 映射到整数档位

        Map price to integer tick level based on tickSize

        买单向下取整（不超过委托价），卖单向上取整（不低于委托价）
        """
        if price is None:
            raise ValueError("price must be provided for tick conversion")
        ratio = price / self.tick_size
        eps = 1e-9
        if side == OrderSide.BUY:
            return int(math.floor(ratio + eps))
        return int(math.ceil(ratio - eps))

    def _invalidate_cache(self, side: str, ticks: int) -> None:
        """使缓存失效 / Invalidate cache"""
        if self._cache_enabled:
            self._qty_cache.pop((side, ticks), None)

    def _get_level_qty(self, side: str, levels: SortedDict, ticks: int) -> int:
        """获取价格档位总量（带缓存）/ Get level quantity with cache"""
        if not self._cache_enabled:
            return sum(o.remaining_quantity for o in levels[ticks])

        cache_key = (side, ticks)
        if cache_key not in self._qty_cache:
            self._qty_cache[cache_key] = sum(
                o.remaining_quantity for o in levels[ticks]
            )
        return self._qty_cache[cache_key]

    def __repr__(self) -> str:
        return (
            f"OrderBook({self.symbol}, "
            f"bid={self.best_bid}, ask={self.best_ask}, "
            f"last={self.last_price})"
        )
