"""
统一日志模块

Unified logging module for the entire application.
"""

import logging
import sys
from typing import Optional

from ..config import CONFIG


def setup_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """
    创建并配置 logger

    Create and configure a logger instance.

    Args:
        name: logger名称（通常使用 __name__）
        level: 日志级别，默认从配置读取

    Returns:
        配置好的 logger 实例
    """
    logger = logging.getLogger(name)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    log_level = level or CONFIG.logging.level
    logger.setLevel(getattr(logging, log_level.upper()))

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(CONFIG.logging.format))
    logger.addHandler(handler)

    return logger


# 模块级 logger（用于快速导入）
logger = setup_logger(__name__)
