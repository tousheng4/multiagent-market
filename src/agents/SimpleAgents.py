"""
简单的规则型交易Agent

Simple rule-based trading agents.

这些Agent不使用LLM，而是基于简单的规则进行交易
适合作为baseline或者提供市场流动性
"""

import random
from typing import Any, Dict, List

from ..market.models.exchange import Exchange
from ..market.models.order import OrderSide, OrderType
from ..strategy import (clamp_sell_qty, max_affordable_qty, mm_quotes,
                        momentum_decision, within_band)
from ..utils.logger import setup_logger
from .BaseAgent import BaseAgent

logger = setup_logger(__name__)


class RandomAgent(BaseAgent):
    """
    随机交易Agent / Random trading agent

    以一定概率随机买入或卖出股票
    """

    def __init__(
        self,
        agent_id: str,
        exchange: Exchange,
        symbols: List[str],
        trade_prob: float = 0.1,
        max_quantity: int = 10,
    ):
        """
        初始化随机Agent / Initialize random agent

        Args:
            agent_id: Agent ID
            exchange: 交易所
            symbols: 股票列表
            trade_prob: 每步交易的概率
            max_quantity: 最大交易数量
        """
        super().__init__(agent_id, exchange, symbols)
        self.trade_prob = trade_prob
        self.max_quantity = max_quantity

    def step(self) -> None:
        """执行一个交易步骤 / Execute one trading step"""
        self.step_count += 1

        # 以一定概率交易
        if random.random() > self.trade_prob:
            return

        # 随机选择股票
        symbol = random.choice(self.symbols)

        # 获取市场数据
        try:
            market_data = self.get_market_data(symbol)
            account = self.get_account()

            # 随机决定买卖方向
            if random.random() < 0.5:
                # 买入
                best_ask = market_data.get("best_ask")
                if best_ask and account["cash"] > best_ask * self.max_quantity:
                    quantity = random.randint(1, self.max_quantity)
                    price = best_ask

                    self.exchange.submit_order(
                        agent_id=self.agent_id,
                        symbol=symbol,
                        order_type=OrderType.LIMIT,
                        side=OrderSide.BUY,
                        quantity=quantity,
                        price=price,
                    )
                    self.log(
                        f"Buy {quantity} {symbol} @ {price}",
                        meta={
                            "event": "trade",
                            "side": "buy",
                            "symbol": symbol,
                            "qty": quantity,
                            "price": price,
                        },
                    )
            else:
                # 卖出
                position = account["positions"].get(symbol, 0)
                if position > 0:
                    quantity = random.randint(1, min(position, self.max_quantity))
                    best_bid = market_data.get("best_bid")

                    if best_bid:
                        self.exchange.submit_order(
                            agent_id=self.agent_id,
                            symbol=symbol,
                            order_type=OrderType.LIMIT,
                            side=OrderSide.SELL,
                            quantity=quantity,
                            price=best_bid,
                        )
                        self.log(
                            f"Sell {quantity} {symbol} @ {best_bid}",
                            meta={
                                "event": "trade",
                                "side": "sell",
                                "symbol": symbol,
                                "qty": quantity,
                                "price": best_bid,
                            },
                        )
        except Exception as e:
            logger.error(f"Error in {symbol}: {e}", exc_info=True)
            self.log(f"Error: {e}", meta={"event": "error", "symbol": symbol})


class MarketMakerAgent(BaseAgent):
    """
    做市商Agent / Market maker agent

    在买卖两侧同时挂单，提供流动性并赚取价差
    """

    def __init__(
        self,
        agent_id: str,
        exchange: Exchange,
        symbols: List[str],
        spread_bps: float = 10.0,  # 价差（基点）
        order_size: int = 10,
        target_position: int = 100,
    ):
        """
        初始化做市商Agent / Initialize market maker agent

        Args:
            agent_id: Agent ID
            exchange: 交易所
            symbols: 股票列表
            spread_bps: 买卖价差（基点，1bp=0.01%）
            order_size: 每次挂单数量
            target_position: 目标持仓（中性位置）
        """
        super().__init__(agent_id, exchange, symbols)
        self.spread_bps = spread_bps
        self.order_size = order_size
        self.target_position = target_position

    def step(self) -> None:
        self.step_count += 1

    def on_event(self, event: Dict[str, Any]) -> None:
        if not isinstance(event, dict):
            return
        if event.get("type") != "data":
            return
        payload = event.get("payload") or {}
        account = self.get_account()
        for symbol in self.symbols:
            try:
                # 获取参考价：用 last_price 而不是 mid_price（mid_price 可能基于旧的挂单）
                market_data = self.get_market_data(symbol)
                ref_price = market_data.get("last_price")
                if ref_price is None:
                    ref_price = market_data.get("mid_price")
                if ref_price is None:
                    continue
                bid_price, ask_price = mm_quotes(ref_price, self.spread_bps)
                if bid_price is None or ask_price is None:
                    continue

                self.log(
                    f"Quote {symbol} bid={bid_price:.4f} ask={ask_price:.4f}",
                    meta={
                        "event": "quote",
                        "mode": "market_maker",
                        "symbol": symbol,
                        "bid": bid_price,
                        "ask": ask_price,
                        "ref_price": ref_price,
                        "position": account["positions"].get(symbol, 0),
                        "cash": account["cash"],
                    },
                )

                position = account["positions"].get(symbol, 0)
                cash = account["cash"]

                # 做市商应该双向挂单，无论持仓如何都提供买卖报价
                # 买方：检查现金是否足够
                affordable = max_affordable_qty(cash, bid_price, self.order_size)
                if affordable > 0:
                    self.exchange.submit_order(
                        agent_id=self.agent_id,
                        symbol=symbol,
                        order_type=OrderType.LIMIT,
                        side=OrderSide.BUY,
                        quantity=affordable,
                        price=round(bid_price, 2),
                    )
                    self.log(
                        f"MM Buy {affordable} {symbol} @ {bid_price:.2f}",
                        meta={
                            "event": "trade",
                            "mode": "market_maker",
                            "side": "buy",
                            "symbol": symbol,
                            "qty": affordable,
                            "price": round(bid_price, 2),
                        },
                    )

                # 卖方：检查是否有持仓可卖
                if position > 0:
                    sell_quantity = min(position, self.order_size)
                    self.exchange.submit_order(
                        agent_id=self.agent_id,
                        symbol=symbol,
                        order_type=OrderType.LIMIT,
                        side=OrderSide.SELL,
                        quantity=sell_quantity,
                        price=round(ask_price, 2),
                    )
                    self.log(
                        f"MM Sell {sell_quantity} {symbol} @ {ask_price:.2f}",
                        meta={
                            "event": "trade",
                            "mode": "market_maker",
                            "side": "sell",
                            "symbol": symbol,
                            "qty": sell_quantity,
                            "price": round(ask_price, 2),
                        },
                    )
            except Exception as e:
                logger.error(f"Error in {symbol}: {e}", exc_info=True)
                self.log(
                    f"Error in {symbol}: {e}", meta={"event": "error", "symbol": symbol}
                )


class MomentumAgent(BaseAgent):
    """
    动量交易Agent / Momentum trading agent

    基于价格动量进行交易：价格上涨时买入，价格下跌时卖出
    """

    def __init__(
        self,
        agent_id: str,
        exchange: Exchange,
        symbols: List[str],
        lookback_period: int = 5,
        momentum_threshold: float = 0.02,  # 2%
        order_size: int = 10,
    ):
        """
        初始化动量Agent / Initialize momentum agent

        Args:
            agent_id: Agent ID
            exchange: 交易所
            symbols: 股票列表
            lookback_period: 回溯周期
            momentum_threshold: 动量阈值（百分比）
            order_size: 订单大小
        """
        super().__init__(agent_id, exchange, symbols)
        self.lookback_period = lookback_period
        self.momentum_threshold = momentum_threshold
        self.order_size = order_size

        # 价格历史
        self.price_history = {symbol: [] for symbol in symbols}

    def step(self) -> None:
        self.step_count += 1

    def on_event(self, event: Dict[str, Any]) -> None:
        if not isinstance(event, dict):
            return
        if event.get("type") != "data":
            return
        account = self.get_account()
        for symbol in self.symbols:
            try:
                market_data = self.get_market_data(symbol)
                signal, indicator, last_price, trade_price = momentum_decision(
                    market_data=market_data,
                    price_history=self.price_history,
                    symbol=symbol,
                    lookback=self.lookback_period,
                    threshold=self.momentum_threshold,
                    max_history=self.lookback_period * 2,
                )

                position = account["positions"].get(symbol, 0)
                cash = account["cash"]

                self.log(
                    f"Momentum signal {signal} for {symbol}",
                    meta={
                        "event": "signal",
                        "mode": "momentum",
                        "symbol": symbol,
                        "signal": signal,
                        "momentum": indicator,
                        "last_price": last_price,
                        "trade_price": trade_price,
                    },
                )

                if (
                    signal == "buy"
                    and trade_price
                    and cash > trade_price * self.order_size
                ):
                    self.exchange.submit_order(
                        agent_id=self.agent_id,
                        symbol=symbol,
                        order_type=OrderType.LIMIT,
                        side=OrderSide.BUY,
                        quantity=self.order_size,
                        price=trade_price,
                    )
                    self.log(
                        (
                            f"Momentum Buy {self.order_size} {symbol}, momentum={indicator:.2%}"
                            if indicator is not None
                            else f"Momentum Buy {self.order_size} {symbol}"
                        ),
                        meta={
                            "event": "trade",
                            "mode": "momentum",
                            "side": "buy",
                            "symbol": symbol,
                            "qty": self.order_size,
                            "price": trade_price,
                            "momentum": indicator,
                            "last_price": last_price,
                        },
                    )

                elif signal == "sell" and trade_price and position > 0:
                    sell_quantity = min(self.order_size, position)
                    if sell_quantity > 0:
                        self.exchange.submit_order(
                            agent_id=self.agent_id,
                            symbol=symbol,
                            order_type=OrderType.LIMIT,
                            side=OrderSide.SELL,
                            quantity=sell_quantity,
                            price=trade_price,
                        )
                        self.log(
                            (
                                f"Momentum Sell {sell_quantity} {symbol}, momentum={indicator:.2%}"
                                if indicator is not None
                                else f"Momentum Sell {sell_quantity} {symbol}"
                            ),
                            meta={
                                "event": "trade",
                                "mode": "momentum",
                                "side": "sell",
                                "symbol": symbol,
                                "qty": sell_quantity,
                                "price": trade_price,
                                "momentum": indicator,
                                "last_price": last_price,
                            },
                        )
            except Exception as e:
                logger.error(f"Error in {symbol}: {e}", exc_info=True)
                self.log(
                    f"Error in {symbol}: {e}", meta={"event": "error", "symbol": symbol}
                )

    def reset(self) -> None:
        """重置Agent / Reset agent"""
        super().reset()
        self.price_history = {symbol: [] for symbol in self.symbols}
