"""
可复用的策略模板片段

Reusable strategy template snippets.
"""

from typing import Dict, List, Optional, Tuple

from .indicators import bollinger_bands, momentum
from .signals import bollinger_signal, momentum_signal


def update_price_hist(
    price_history: Dict[str, List[float]], symbol: str, price: float, max_length: int
) -> List[float]:
    """
    更新价格历史并截断长度

    Update price history and truncate to max length.
    """
    history = price_history.setdefault(symbol, [])
    history.append(price)
    if len(history) > max_length:
        del history[:-max_length]
    return history


def momentum_decision(
    market_data: Dict[str, float],
    price_history: Dict[str, List[float]],
    symbol: str,
    lookback: int,
    threshold: float,
    max_history: Optional[int] = None,
) -> Tuple[str, Optional[float], Optional[float], Optional[float]]:
    """
    生成动量交易信号和参考价格

    Generate momentum trading signal and reference price.

    Returns:
        signal: buy/sell/hold
        indicator: 动量值
        last_price: 最新价格
        trade_price: 用于下单的价格（买用 best_ask，卖用 best_bid）
    """
    last_price = market_data.get("last_price") or market_data.get("mid_price")
    if last_price is None:
        return "hold", None, None, None

    history = update_price_hist(
        price_history, symbol, last_price, max_history or lookback * 2
    )
    indicator = momentum(history, lookback)

    if indicator is None:
        return "hold", None, last_price, None

    signal = momentum_signal(indicator, threshold)
    trade_price: Optional[float] = None
    if signal == "buy":
        trade_price = market_data.get("best_ask")
    elif signal == "sell":
        trade_price = market_data.get("best_bid")

    return signal, indicator, last_price, trade_price


def mm_quotes(
    mid_price: Optional[float], spread_bps: float
) -> Tuple[Optional[float], Optional[float]]:
    """
    基于中间价生成做市商报价

    Generate market maker quotes based on mid price.
    """
    if mid_price is None or spread_bps <= 0:
        return None, None

    spread = mid_price * (spread_bps / 10000)
    bid_price = mid_price - spread / 2
    ask_price = mid_price + spread / 2

    return round(bid_price, 4), round(ask_price, 4)


def bollinger_decision(
    market_data: Dict[str, float],
    price_history: Dict[str, List[float]],
    symbol: str,
    window: int,
    num_std: float = 2.0,
    max_history: Optional[int] = None,
) -> Tuple[str, Optional[Tuple[float, float, float]], Optional[float], Optional[float]]:
    """
    生成基于布林带的均值回归信号

    Generate Bollinger Bands mean reversion signal.

    返回信号、布林带、最新价格和参考下单价
    """
    last_price = market_data.get("last_price") or market_data.get("mid_price")
    if last_price is None:
        return "hold", None, None, None

    history = update_price_hist(
        price_history, symbol, last_price, max_history or window * 2
    )
    bands = bollinger_bands(history, window, num_std)

    if bands is None:
        return "hold", None, last_price, None

    lower, upper, _ = bands
    signal = bollinger_signal(last_price, lower, upper)
    trade_price: Optional[float] = None
    if signal == "buy":
        trade_price = market_data.get("best_ask")
    elif signal == "sell":
        trade_price = market_data.get("best_bid")

    return signal, bands, last_price, trade_price
