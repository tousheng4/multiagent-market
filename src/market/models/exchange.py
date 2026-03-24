from __future__ import annotations

import uuid
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional, Set, Tuple

from ...config import CONFIG
from ...environment.event_hub import (EV_ORDER_ACK, EV_ORDER_CMD,
                                      EV_ORDER_REJECT, EV_TRADE, EventHub)
from ...utils.logger import setup_logger
from .order import Order, OrderSide, OrderType, Trade
from .orderbook import OrderBook

logger = setup_logger(__name__)


class Exchange:
    def __init__(self, initial_cash: float = None, hub: Optional[EventHub] = None):
        if initial_cash is None:
            initial_cash = CONFIG.exchange.default_initial_cash

        self.initial_cash = initial_cash

        self.order_books: Dict[str, OrderBook] = {}
        self.cash_balances: Dict[str, float] = {}
        self.position_records: Dict[str, Dict[str, int]] = {}
        self.order_records: Dict[str, Order] = {}
        self.trade_records: List[Trade] = []

        # 性能优化：交易历史索引 / Performance optimization: trade history index
        self._trades_by_symbol: Dict[str, List[Trade]] = defaultdict(list)
        self._trades_by_agent: Dict[str, List[Trade]] = defaultdict(list)

        self.current_time = 0

        self.hub = hub or EventHub()
        self._order_sid = ""

        self._seen: Set[str] = set()
        self._seen_q: Deque[str] = deque()
        self._seen_cap = CONFIG.exchange.seen_cache_size

    def set_hub(self, hub: EventHub) -> None:
        self.hub = hub

    def _has(self, key: str) -> bool:
        return bool(key) and key in self._seen

    def _mark(self, key: str) -> None:
        if not key or key in self._seen:
            return
        self._seen.add(key)
        self._seen_q.append(key)
        while len(self._seen_q) > self._seen_cap:
            old = self._seen_q.popleft()
            self._seen.discard(old)

    def start_order_consumer(self) -> None:
        if self._order_sid:
            return
        self._order_sid = self.hub.on(
            EV_ORDER_CMD, self._on_order_cmd, name="exchange_order_cmd"
        )

    def stop_order_consumer(self) -> None:
        if not self._order_sid:
            return
        self.hub.off(EV_ORDER_CMD, self._order_sid)
        self._order_sid = ""

    def _on_order_cmd(self, msg: Dict) -> None:
        """处理订单命令事件（修复逻辑）/ Handle order command event (fixed logic)"""
        payload = msg.get("payload") or {}
        cmd_id = str(msg.get("id") or payload.get("cmd_id") or "")
        if self._has(cmd_id):
            return

        try:
            order_type = OrderType(str(payload.get("order_type", "")).lower())
            side = OrderSide(str(payload.get("side", "")).lower())
            qty = int(payload.get("quantity"))
            raw = payload.get("price")
            px = None if raw is None else float(raw)

            self.submit_order(
                agent_id=str(payload.get("agent_id")),
                symbol=str(payload.get("symbol")),
                order_type=order_type,
                side=side,
                quantity=qty,
                price=px,
                cmd_id=cmd_id or None,
            )
            # ✅ 修复：只在成功后标记 / Fixed: only mark on success
            self._mark(cmd_id)

        except Exception as exc:
            logger.error(f"Order command failed: {exc}", exc_info=True)
            self.hub.emit(
                EV_ORDER_REJECT,
                {
                    "cmd_id": cmd_id or None,
                    "agent_id": payload.get("agent_id"),
                    "symbol": payload.get("symbol"),
                    "reason": str(exc),
                },
                key=cmd_id or str(payload.get("agent_id") or ""),
                src="exchange",
            )
            # ✅ 修复：失败时不标记，允许重试 / Fixed: don't mark on failure

    def publish_order_cmd(
        self,
        agent_id: str,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        quantity: int,
        price: Optional[float] = None,
        cmd_id: Optional[str] = None,
    ) -> str:
        msg = self.hub.emit(
            EV_ORDER_CMD,
            {
                "cmd_id": cmd_id,
                "agent_id": agent_id,
                "symbol": symbol,
                "order_type": order_type.value,
                "side": side.value,
                "quantity": int(quantity),
                "price": None if price is None else float(price),
            },
            key=cmd_id or f"{agent_id}:{symbol}:{self.current_time}",
            src=f"agent:{agent_id}",
            eid=cmd_id,
        )
        return str(msg["id"])

    def register_agent(
        self, agent_id: str, initial_cash: Optional[float] = None
    ) -> None:
        if agent_id in self.cash_balances:
            raise ValueError(f"Agent {agent_id} already registered")

        cash = initial_cash if initial_cash is not None else self.initial_cash
        self.cash_balances[agent_id] = cash
        self.position_records[agent_id] = {}

    def add_symbol(self, symbol: str) -> None:
        if symbol not in self.order_books:
            self.order_books[symbol] = OrderBook(symbol)

    def submit_order(
        self,
        agent_id: str,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        quantity: int,
        price: Optional[float] = None,
        cmd_id: Optional[str] = None,
    ) -> Tuple[Order, List[Trade]]:
        if agent_id not in self.cash_balances:
            raise ValueError(f"Agent {agent_id} not registered")

        if symbol not in self.order_books:
            raise ValueError(f"Symbol {symbol} not found")

        order = Order(
            order_id=str(uuid.uuid4()),
            agent_id=agent_id,
            symbol=symbol,
            order_type=order_type,
            side=side,
            quantity=quantity,
            price=price,
            timestamp=self.current_time,
        )

        if not self._risk_check(order):
            raise ValueError(f"Risk check failed for order {order}")

        self.order_records[order.order_id] = order
        trades = self.order_books[symbol].add_order(order)

        for trade in trades:
            trade.timestamp = float(self.current_time)
            self._settle_trade(trade)
            self.hub.emit(
                EV_TRADE,
                {
                    "trade_id": trade.trade_id,
                    "symbol": trade.symbol,
                    "buy_order_id": trade.buy_order_id,
                    "sell_order_id": trade.sell_order_id,
                    "buyer_id": trade.buyer_id,
                    "seller_id": trade.seller_id,
                    "price": float(trade.price),
                    "quantity": int(trade.quantity),
                    "timestamp": trade.timestamp,
                    "cmd_id": cmd_id,
                    "order_id": order.order_id,
                },
                key=trade.trade_id,
                src="exchange",
            )

        self.trade_records.extend(trades)

        self.hub.emit(
            EV_ORDER_ACK,
            {
                "cmd_id": cmd_id,
                "order_id": order.order_id,
                "agent_id": order.agent_id,
                "symbol": order.symbol,
                "order_type": order.order_type.value,
                "side": order.side.value,
                "quantity": int(order.quantity),
                "price": None if order.price is None else float(order.price),
                "filled_quantity": int(order.filled_quantity),
                "status": order.status.value,
                "timestamp": self.current_time,
                "trade_ids": [t.trade_id for t in trades],
            },
            key=cmd_id or order.order_id,
            src="exchange",
        )

        if cmd_id:
            self._mark(cmd_id)

        return order, trades

    def _risk_check(self, order: Order) -> bool:
        """风险检查（优化错误处理）/ Risk check with improved error handling"""
        aid = order.agent_id

        if order.is_buy:
            required = self._estimate_buy_cost(order)
            if required is None:
                logger.warning(
                    f"Cannot estimate cost for market order {order.order_id}: "
                    f"orderbook for {order.symbol} is empty"
                )
                return False
            return self.cash_balances[aid] >= required

        pos = self.position_records[aid].get(order.symbol, 0)
        return pos >= order.quantity

    def _estimate_buy_cost(self, order: Order) -> Optional[float]:
        if order.order_type == OrderType.LIMIT:
            if order.price is None:
                return None
            return order.price * order.quantity

        book = self.order_books[order.symbol]
        return book.estimate_cost(OrderSide.BUY, order.quantity)

    def _settle_trade(self, trade: Trade) -> None:
        """结算交易（添加索引）/ Settle trade with index update"""
        buyer = trade.buyer_id
        seller = trade.seller_id
        symbol = trade.symbol
        qty = trade.quantity
        gross = trade.price * qty

        self.cash_balances[buyer] -= gross
        self.cash_balances[seller] += gross

        if symbol not in self.position_records[buyer]:
            self.position_records[buyer][symbol] = 0
        if symbol not in self.position_records[seller]:
            self.position_records[seller][symbol] = 0

        self.position_records[buyer][symbol] += qty
        self.position_records[seller][symbol] -= qty

        # ✅ 性能优化：更新索引 / Performance optimization: update index
        self._trades_by_symbol[symbol].append(trade)
        self._trades_by_agent[buyer].append(trade)
        self._trades_by_agent[seller].append(trade)

    def cancel_order(self, order_id: str) -> bool:
        if order_id not in self.order_records:
            return False
        order = self.order_records[order_id]
        return self.order_books[order.symbol].cancel_order(order_id)

    def get_order_book(self, symbol: str) -> Optional[OrderBook]:
        return self.order_books.get(symbol)

    def get_account(self, agent_id: str) -> Dict:
        if agent_id not in self.cash_balances:
            raise ValueError(f"Agent {agent_id} not found")

        return {
            "cash": self.cash_balances[agent_id],
            "positions": self.position_records[agent_id].copy(),
            "portfolio_value": self._calc_portfolio_value(agent_id),
        }

    def _calc_portfolio_value(self, agent_id: str) -> float:
        """计算投资组合价值 / Calculate portfolio value"""
        total = self.cash_balances[agent_id]

        for symbol, qty in self.position_records[agent_id].items():
            if qty == 0:
                continue
            book = self.order_books[symbol]
            mid = book.mid_price
            if mid is None:
                mid = book.last_price
            if mid is not None:
                total += qty * mid

        return total

    def get_market_data(self, symbol: str) -> Dict:
        if symbol not in self.order_books:
            raise ValueError(f"Symbol {symbol} not found")

        book = self.order_books[symbol]
        bids, asks = book.get_depth(levels=5)

        return {
            "symbol": symbol,
            "best_bid": book.best_bid,
            "best_ask": book.best_ask,
            "mid_price": book.mid_price,
            "spread": book.spread,
            "last_price": book.last_price,
            "bids": bids,
            "asks": asks,
            "timestamp": self.current_time,
        }

    def step(self) -> None:
        self.current_time += 1

    def update_price(self, symbol: str, price: float) -> None:
        """更新市场价格（简化名称）/ Update market price (simplified name)"""
        if symbol not in self.order_books:
            raise ValueError(f"Symbol {symbol} not found")
        self.order_books[symbol].last_price = float(price)

    def get_trade_history(
        self, symbol: Optional[str] = None, agent_id: Optional[str] = None
    ) -> List[Trade]:
        """获取交易历史（使用索引优化）/ Get trade history with index optimization"""
        # ✅ 性能优化：优先使用索引 / Performance optimization: use index when possible
        if symbol is not None and agent_id is None:
            return self._trades_by_symbol.get(symbol, []).copy()

        if agent_id is not None and symbol is None:
            return self._trades_by_agent.get(agent_id, []).copy()

        # 需要同时过滤时，使用较小的集合作为基础
        if symbol is not None and agent_id is not None:
            agent_trades = self._trades_by_agent.get(agent_id, [])
            return [t for t in agent_trades if t.symbol == symbol]

        # 都不指定时返回全部
        return self.trade_records.copy()

    def __repr__(self) -> str:
        return (
            f"Exchange(symbols={list(self.order_books.keys())}, "
            f"agents={len(self.cash_balances)}, trades={len(self.trade_records)})"
        )
