"""
策略模块 - 提供技术指标、信号生成和风险管理工具

Strategy module - provides technical indicators, signal generation, and risk management tools.
"""

from .indicators import (bollinger_bands, ema, momentum, rsi, simple_ma,
                         weighted_ma)
from .risk import clamp_sell_qty, max_affordable_qty, within_band
from .signals import (bollinger_signal, breakout_signal, crossover_signal,
                      momentum_signal, rsi_signal)
from .templates import (bollinger_decision, mm_quotes, momentum_decision,
                        update_price_hist)

__all__ = [
    # Indicators
    "bollinger_bands",
    "ema",
    "momentum",
    "rsi",
    "simple_ma",
    "weighted_ma",
    # Risk management
    "clamp_sell_qty",
    "max_affordable_qty",
    "within_band",
    # Signals
    "bollinger_signal",
    "breakout_signal",
    "crossover_signal",
    "momentum_signal",
    "rsi_signal",
    # Templates
    "bollinger_decision",
    "mm_quotes",
    "momentum_decision",
    "update_price_hist",
]
