"""
常见的技术指标计算工具。
"""

from typing import Iterable, List, Optional, Tuple
import math


def _ensure_window(prices: Iterable[float], window: int) -> List[float]:
    if window <= 0:
        raise ValueError("window must be positive")
    return list(prices)


def simpleMovingAverage(prices: Iterable[float], window: int) -> Optional[float]:
    """
    计算简单移动平均线（SMA）。
    """
    data = _ensure_window(prices, window)
    if len(data) < window:
        return None
    window_slice = data[-window:]
    return sum(window_slice) / window


def exponentialMovingAverage(
    prices: Iterable[float], window: int, previous_ema: Optional[float] = None
) -> Optional[float]:
    """
    计算指数移动平均线（EMA）。
    previous_ema 可用于迭代更新，否则使用前 window 个数据的均值作为初始值。
    """
    data = _ensure_window(prices, window)
    if len(data) < window:
        return None

    smoothing = 2 / (window + 1)

    if previous_ema is None:
        ema = simpleMovingAverage(data[:window], window)
    else:
        ema = previous_ema

    if ema is None:
        return None

    for price in data[-window:]:
        ema = (price - ema) * smoothing + ema
    return ema


def momentum(prices: Iterable[float], lookback: int) -> Optional[float]:
    """
    计算动量（当前价格相对 lookback 期前的百分比变化）。
    """
    data = _ensure_window(prices, lookback)
    if len(data) < lookback:
        return None
    current_price = data[-1]
    past_price = data[-lookback]
    if past_price == 0:
        return None
    return (current_price - past_price) / past_price


def volatility(prices: Iterable[float], window: int) -> Optional[float]:
    """
    粗略计算波动率：基于价格的简单收益标准差。
    """
    data = _ensure_window(prices, window)
    if len(data) <= window:
        return None

    returns = []
    for prev, curr in zip(data[-window - 1 : -1], data[-window:]):
        if prev != 0:
            returns.append((curr - prev) / prev)

    if not returns:
        return None

    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
    return math.sqrt(variance)


def bollingerBands(
    prices: Iterable[float], window: int, num_std: float = 2.0
) -> Optional[Tuple[float, float, float]]:
    """
    计算布林带（下轨、上轨、中轨）。
    """
    data = _ensure_window(prices, window)
    if len(data) < window:
        return None

    window_slice = data[-window:]
    mean = sum(window_slice) / window
    variance = sum((p - mean) ** 2 for p in window_slice) / window
    std = math.sqrt(variance)
    lower = mean - num_std * std
    upper = mean + num_std * std
    return lower, upper, mean


def relativeStrengthIndex(prices: Iterable[float], window: int) -> Optional[float]:
    """
    计算 RSI，相对强弱指标，返回 0-100。
    """
    if window <= 0:
        raise ValueError("window must be positive")

    data = list(prices)
    if len(data) <= window:
        return None

    gains = 0.0
    losses = 0.0
    for prev, curr in zip(data[-window - 1 : -1], data[-window:]):
        diff = curr - prev
        if diff > 0:
            gains += diff
        elif diff < 0:
            losses -= diff

    avg_gain = gains / window
    avg_loss = losses / window

    if avg_loss == 0 and avg_gain == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
