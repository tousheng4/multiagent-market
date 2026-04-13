"""
工具工厂 - 创建所有 LangChain tools
"""

from typing import Any, List

from langchain_core.tools import BaseTool

from .marketTools import create_market_tools
from .memory_tools import create_memory_tools
from .news_tools import create_news_tools


def create_all_tools(
    exchange: Any,
    news_generator: Any,
    memory_store: Any = None,
    agent_id: str = "default-agent",
    current_step_getter: Any = None,
) -> List[BaseTool]:
    """
    创建所有工具的合集

    Args:
        exchange: 交易所实例
        news_generator: 新闻生成器实例
        memory_store: 记忆存储（可选）
        agent_id: Agent ID（用于市场工具）
        current_step_getter: 获取当前步的回调（用于写记忆）
    """
    tools: List[BaseTool] = []

    # 市场工具
    tools.extend(create_market_tools(exchange=exchange, agentId=agent_id))

    # 新闻工具
    if news_generator:
        tools.extend(create_news_tools(news_generator=news_generator))

    # 记忆工具
    tools.extend(
        create_memory_tools(
            memory_store=memory_store,
            default_agent_id=agent_id,
            current_step_getter=current_step_getter,
        )
    )

    return tools
