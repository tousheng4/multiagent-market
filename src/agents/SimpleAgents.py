"""
简单的规则型交易Agent

这些Agent不使用LLM，而是基于简单的规则进行交易
适合作为baseline或者提供市场流动性
"""

import random
from typing import List

from .BaseAgent import BaseAgent
from ..market.models.exchange import Exchange
from ..market.models.order import OrderType, OrderSide
from ..strategy import (
    clampSellQuantity,
    marketMakerQuotes,
    maxAffordableQuantity,
    momentumDecision,
    withinPositionBand,
)


class RandomAgent(BaseAgent):
    """
    随机交易Agent

    以一定概率随机买入或卖出股票
    """

    def __init__(
        self,
        agentId: str,
        exchange: Exchange,
        symbols: List[str],
        tradeProb: float = 0.1,
        maxQuantity: int = 10
    ):
        """
        初始化随机Agent

        Args:
            agentId: Agent ID
            exchange: 交易所
            symbols: 股票列表
            tradeProb: 每步交易的概率
            maxQuantity: 最大交易数量
        """
        super().__init__(agentId, exchange, symbols)
        self.tradeProb = tradeProb
        self.maxQuantity = maxQuantity

    def step(self) -> None:
        """执行一个交易步骤"""
        self.stepCount += 1

        # 以一定概率交易
        if random.random() > self.tradeProb:
            return

        # 随机选择股票
        symbol = random.choice(self.symbols)

        # 获取市场数据
        try:
            marketData = self.getMarketData(symbol)
            account = self.getAccount()

            # 随机决定买卖方向
            if random.random() < 0.5:
                # 买入
                bestAsk = marketData.get('best_ask')
                if bestAsk and account['cash'] > bestAsk * self.maxQuantity:
                    quantity = random.randint(1, self.maxQuantity)
                    price = bestAsk

                    self.exchange.submitOrder(
                        agentId=self.agentId,
                        symbol=symbol,
                        orderType=OrderType.LIMIT,
                        side=OrderSide.BUY,
                        quantity=quantity,
                        price=price
                    )
                    self.logMessage(
                        f"Buy {quantity} {symbol} @ {price}",
                        meta={"event": "trade", "side": "buy", "symbol": symbol, "qty": quantity, "price": price},
                    )
            else:
                # 卖出
                position = account['positions'].get(symbol, 0)
                if position > 0:
                    quantity = random.randint(1, min(position, self.maxQuantity))
                    bestBid = marketData.get('best_bid')

                    if bestBid:
                        self.exchange.submitOrder(
                            agentId=self.agentId,
                            symbol=symbol,
                            orderType=OrderType.LIMIT,
                            side=OrderSide.SELL,
                            quantity=quantity,
                            price=bestBid
                        )
                        self.logMessage(
                            f"Sell {quantity} {symbol} @ {bestBid}",
                            meta={"event": "trade", "side": "sell", "symbol": symbol, "qty": quantity, "price": bestBid},
                        )
        except Exception as e:
            self.logMessage(f"Error: {e}", meta={"event": "error", "symbol": symbol})


class MarketMakerAgent(BaseAgent):
    """
    做市商Agent

    在买卖两侧同时挂单，提供流动性并赚取价差
    """

    def __init__(
        self,
        agentId: str,
        exchange: Exchange,
        symbols: List[str],
        spreadBps: float = 10.0,  # 价差（基点）
        orderSize: int = 10,
        targetPosition: int = 100
    ):
        """
        初始化做市商Agent

        Args:
            agentId: Agent ID
            exchange: 交易所
            symbols: 股票列表
            spreadBps: 买卖价差（基点，1bp=0.01%）
            orderSize: 每次挂单数量
            targetPosition: 目标持仓（中性位置）
        """
        super().__init__(agentId, exchange, symbols)
        self.spreadBps = spreadBps
        self.orderSize = orderSize
        self.targetPosition = targetPosition

    def step(self) -> None:
        self.stepCount += 1

    def onEvent(self, event) -> None:
        if not isinstance(event, dict):
            return
        if event.get("type") != "data":
            return
        payload = event.get("payload") or {}
        account = self.getAccount()
        for symbol in self.symbols:
            try:
                # 获取中间价作为参考价
                marketData = self.getMarketData(symbol)
                midPrice = marketData.get('mid_price') or marketData.get('last_price')
                bidPrice, askPrice = marketMakerQuotes(midPrice, self.spreadBps)
                if bidPrice is None or askPrice is None:
                    continue

                self.logMessage(
                    f"Quote {symbol} bid={bidPrice:.4f} ask={askPrice:.4f}",
                    meta={
                        "event": "quote",
                        "mode": "market_maker",
                        "symbol": symbol,
                        "bid": bidPrice,
                        "ask": askPrice,
                        "mid_price": midPrice,
                        "position": account['positions'].get(symbol, 0),
                        "cash": account['cash'],
                    },
                )

                position = account['positions'].get(symbol, 0)
                cash = account['cash']

                affordable = maxAffordableQuantity(cash, bidPrice, self.orderSize)
                if position < self.targetPosition and affordable > 0:
                    self.exchange.submitOrder(
                        agentId=self.agentId,
                        symbol=symbol,
                        orderType=OrderType.LIMIT,
                        side=OrderSide.BUY,
                        quantity=affordable,
                        price=round(bidPrice, 2)
                    )
                    self.logMessage(
                        f"MM Buy {affordable} {symbol} @ {bidPrice:.2f}",
                        meta={
                            "event": "trade",
                            "mode": "market_maker",
                            "side": "buy",
                            "symbol": symbol,
                            "qty": affordable,
                            "price": round(bidPrice, 2),
                        },
                    )

                if position > self.targetPosition and not withinPositionBand(position, self.targetPosition, self.orderSize):
                    sellQuantity = clampSellQuantity(position - self.targetPosition, self.orderSize)
                    if sellQuantity > 0:
                        self.exchange.submitOrder(
                            agentId=self.agentId,
                            symbol=symbol,
                            orderType=OrderType.LIMIT,
                            side=OrderSide.SELL,
                            quantity=sellQuantity,
                            price=round(askPrice, 2)
                        )
                        self.logMessage(
                            f"MM Sell {sellQuantity} {symbol} @ {askPrice:.2f}",
                            meta={
                                "event": "trade",
                                "mode": "market_maker",
                                "side": "sell",
                                "symbol": symbol,
                                "qty": sellQuantity,
                                "price": round(askPrice, 2),
                            },
                        )
            except Exception as e:
                self.logMessage(f"Error in {symbol}: {e}", meta={"event": "error", "symbol": symbol})


class MomentumAgent(BaseAgent):
    """
    动量交易Agent

    基于价格动量进行交易：价格上涨时买入，价格下跌时卖出
    """

    def __init__(
        self,
        agentId: str,
        exchange: Exchange,
        symbols: List[str],
        lookbackPeriod: int = 5,
        momentumThreshold: float = 0.02,  # 2%
        orderSize: int = 10
    ):
        """
        初始化动量Agent

        Args:
            agentId: Agent ID
            exchange: 交易所
            symbols: 股票列表
            lookbackPeriod: 回溯周期
            momentumThreshold: 动量阈值（百分比）
            orderSize: 订单大小
        """
        super().__init__(agentId, exchange, symbols)
        self.lookbackPeriod = lookbackPeriod
        self.momentumThreshold = momentumThreshold
        self.orderSize = orderSize

        # 价格历史
        self.priceHistory = {symbol: [] for symbol in symbols}

    def step(self) -> None:
        self.stepCount += 1

    def onEvent(self, event) -> None:
        if not isinstance(event, dict):
            return
        if event.get("type") != "data":
            return
        account = self.getAccount()
        for symbol in self.symbols:
            try:
                marketData = self.getMarketData(symbol)
                signal, indicator, lastPrice, tradePrice = momentumDecision(
                    market_data=marketData,
                    price_history=self.priceHistory,
                    symbol=symbol,
                    lookback=self.lookbackPeriod,
                    threshold=self.momentumThreshold,
                    max_history=self.lookbackPeriod * 2,
                )

                position = account['positions'].get(symbol, 0)
                cash = account['cash']

                self.logMessage(
                    f"Momentum signal {signal} for {symbol}",
                    meta={
                        "event": "signal",
                        "mode": "momentum",
                        "symbol": symbol,
                        "signal": signal,
                        "momentum": indicator,
                        "last_price": lastPrice,
                        "trade_price": tradePrice,
                    },
                )

                if signal == "buy" and tradePrice and cash > tradePrice * self.orderSize:
                    self.exchange.submitOrder(
                        agentId=self.agentId,
                        symbol=symbol,
                        orderType=OrderType.LIMIT,
                        side=OrderSide.BUY,
                        quantity=self.orderSize,
                        price=tradePrice
                    )
                    self.logMessage(
                        f"Momentum Buy {self.orderSize} {symbol}, momentum={indicator:.2%}" if indicator is not None else f"Momentum Buy {self.orderSize} {symbol}",
                        meta={
                            "event": "trade",
                            "mode": "momentum",
                            "side": "buy",
                            "symbol": symbol,
                            "qty": self.orderSize,
                            "price": tradePrice,
                            "momentum": indicator,
                            "last_price": lastPrice,
                        },
                    )

                elif signal == "sell" and tradePrice and position > 0:
                    sellQuantity = min(self.orderSize, position)
                    if sellQuantity > 0:
                        self.exchange.submitOrder(
                            agentId=self.agentId,
                            symbol=symbol,
                            orderType=OrderType.LIMIT,
                            side=OrderSide.SELL,
                            quantity=sellQuantity,
                            price=tradePrice
                        )
                        self.logMessage(
                            f"Momentum Sell {sellQuantity} {symbol}, momentum={indicator:.2%}" if indicator is not None else f"Momentum Sell {sellQuantity} {symbol}",
                            meta={
                                "event": "trade",
                                "mode": "momentum",
                                "side": "sell",
                                "symbol": symbol,
                                "qty": sellQuantity,
                                "price": tradePrice,
                                "momentum": indicator,
                                "last_price": lastPrice,
                            },
                        )
            except Exception as e:
                self.logMessage(f"Error in {symbol}: {e}", meta={"event": "error", "symbol": symbol})

    def reset(self) -> None:
        """重置Agent"""
        super().reset()
        self.priceHistory = {symbol: [] for symbol in self.symbols}
