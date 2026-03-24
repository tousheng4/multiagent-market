"""
常见的风险管理与仓位控制工具

Common risk management and position control utilities.
"""

import math
from typing import Optional


def max_affordable_qty(cash: float, price: Optional[float], cap: int) -> int:
    """
    基于可用现金与价格计算最大可买数量，结果不会超过 cap

    Calculate maximum affordable quantity based on cash and price, capped at max.
    """
    if price is None or price <= 0 or cap <= 0:
        return 0
    affordable = math.floor(cash / price)
    return int(max(0, min(cap, affordable)))


def clamp_sell_qty(position: int, desired: int) -> int:
    """
    基于当前持仓约束卖出数量，防止超卖

    Clamp sell quantity to prevent overselling.
    """
    if position <= 0 or desired <= 0:
        return 0
    return min(position, desired)


def within_band(position: int, target: int, band: int) -> bool:
    """
    判断当前持仓是否处于目标持仓的容忍区间内

    Check if position is within target band.
    """
    lower = target - band
    upper = target + band
    return lower <= position <= upper
