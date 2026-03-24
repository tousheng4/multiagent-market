"""
全局常量定义

Global constants used across the application.
"""

from typing import Final

# 订单相关常量 / Order-related constants
MIN_ORDER_QUANTITY: Final[int] = 1
MIN_ORDER_PRICE: Final[float] = 0.01

# 性能调优相关 / Performance tuning constants
MAX_PRICE_HISTORY: Final[int] = 1000
ORDERBOOK_DEPTH_LEVELS: Final[int] = 10

# 数据处理相关 / Data processing constants
DEFAULT_LOOKBACK_PERIOD: Final[int] = 20
