"""
交易信号判定函数。
"""

from typing import Optional


def momentumSignal(momentum_value: Optional[float], threshold: float) -> str:
    """
    根据动量值生成信号。
    """
    if momentum_value is None:
        return "hold"
    if momentum_value > threshold:
        return "buy"
    if momentum_value < -threshold:
        return "sell"
    return "hold"


def crossoverSignal(
    short_ma: Optional[float], long_ma: Optional[float], deadband: float = 0.0
) -> str:
    """
    均线金叉/死叉信号。
    """
    if short_ma is None or long_ma is None:
        return "hold"
    if short_ma > long_ma + deadband:
        return "buy"
    if short_ma < long_ma - deadband:
        return "sell"
    return "hold"


def breakoutSignal(
    price: Optional[float], support: Optional[float], resistance: Optional[float], buffer: float = 0.0
) -> str:
    """
    突破/回落信号。
    """
    if price is None or support is None or resistance is None:
        return "hold"
    if resistance > support and price >= resistance * (1 - buffer):
        return "breakout_up"
    if resistance > support and price <= support * (1 + buffer):
        return "breakout_down"
    return "range"


def rsiSignal(rsi_value: Optional[float], overbought: float = 70.0, oversold: float = 30.0) -> str:
    """
    基于 RSI 的超买超卖信号。
    """
    if rsi_value is None:
        return "hold"
    if rsi_value >= overbought:
        return "sell"
    if rsi_value <= oversold:
        return "buy"
    return "hold"


def bollingerSignal(price: Optional[float], lower: Optional[float], upper: Optional[float]) -> str:
    """
    布林带反转信号：触及下轨买入，触及上轨卖出。
    """
    if price is None or lower is None or upper is None:
        return "hold"
    if price <= lower:
        return "buy"
    if price >= upper:
        return "sell"
    return "hold"
