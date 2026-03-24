"""
全局配置管理（使用 Pydantic）

Configuration management using Pydantic for type safety and validation.
"""

from pydantic import BaseModel, Field


class ExchangeConfig(BaseModel):
    """交易所配置 / Exchange configuration"""

    seen_cache_size: int = Field(100_000, description="命令去重缓存大小")
    default_initial_cash: float = Field(100_000.0, description="默认初始资金")


class OrderBookConfig(BaseModel):
    """订单簿配置 / OrderBook configuration"""

    default_tick_size: float = Field(0.05, description="默认最小价格变动单位")
    enable_qty_cache: bool = Field(True, description="是否启用深度缓存优化")


class SimulationConfig(BaseModel):
    """仿真配置 / Simulation configuration"""

    default_queue_size: int = Field(4096, description="异步队列大小")
    verbose_step_interval: int = Field(100, description="详细输出间隔")


class LoggingConfig(BaseModel):
    """日志配置 / Logging configuration"""

    level: str = Field("INFO", description="日志级别")
    format: str = Field(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s", description="日志格式"
    )


class GlobalConfig(BaseModel):
    """全局配置 / Global configuration"""

    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    orderbook: OrderBookConfig = Field(default_factory=OrderBookConfig)
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


# 全局配置实例 / Global config instance
CONFIG = GlobalConfig()
