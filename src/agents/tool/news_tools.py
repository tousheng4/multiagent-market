"""
新闻查询工具 - 供 LangChain ReAct Agent 使用

提供读取模拟新闻的能力
"""

from typing import Any, Dict, List

from langchain.tools import BaseTool
from pydantic import BaseModel, Field


class GetRecentNewsInput(BaseModel):
    n: int = Field(default=10, gt=0, le=100, description="返回的新闻条数")


class GetRecentNewsTool(BaseTool):
    """获取最近新闻的工具"""

    name: str = "get_recent_news"
    description: str = """获取最近的模拟新闻列表。每条新闻包含：
    - news: 新闻内容文本
    - symbol: 相关股票代码
    - step: 仿真步数
    - change_pct: 价格变动百分比

    返回最近 n 条新闻（默认 10 条），按时间倒序排列。"""

    args_schema: type[BaseModel] = GetRecentNewsInput
    news_generator: Any = Field(exclude=True, default=None)

    class Config:
        arbitrary_types_allowed = True

    def _run(self, n: int = 10) -> Dict[str, Any]:
        try:
            news = self.news_generator.get_recent_news(n)
            return {
                "success": True,
                "num_news": len(news),
                "news": [
                    {
                        "news": item.get("news", ""),
                        "symbol": item.get("symbol", ""),
                        "step": item.get("step", 0),
                        "change_pct": item.get("change_pct", 0.0),
                    }
                    for item in news
                ],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _arun(self, n: int = 10) -> Dict[str, Any]:
        raise NotImplementedError("get_recent_news does not support async")


class SearchNewsBySymbolInput(BaseModel):
    symbol: str = Field(description="股票代码，例如 'AAPL'")
    n: int = Field(default=5, gt=0, le=100, description="返回的新闻条数")


class SearchNewsBySymbolTool(BaseTool):
    """按股票代码搜索新闻的工具"""

    name: str = "search_news_by_symbol"
    description: str = """搜索特定股票代码的最近新闻。

    参数：
    - symbol: 股票代码（如 'AAPL'）
    - n: 返回条数（默认 5 条）

    返回该股票相关的最近 n 条新闻。"""

    args_schema: type[BaseModel] = SearchNewsBySymbolInput
    news_generator: Any = Field(exclude=True, default=None)

    class Config:
        arbitrary_types_allowed = True

    def _run(self, symbol: str, n: int = 5) -> Dict[str, Any]:
        try:
            all_news = self.news_generator.get_recent_news(1000)
            filtered = [item for item in all_news if item.get("symbol") == symbol][-n:]
            return {
                "success": True,
                "symbol": symbol,
                "num_news": len(filtered),
                "news": [
                    {
                        "news": item.get("news", ""),
                        "step": item.get("step", 0),
                        "change_pct": item.get("change_pct", 0.0),
                    }
                    for item in filtered
                ],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _arun(self, symbol: str, n: int = 5) -> Dict[str, Any]:
        raise NotImplementedError("search_news_by_symbol does not support async")


__all__ = [
    "GetRecentNewsTool",
    "SearchNewsBySymbolTool",
    "create_news_tools",
]


def create_news_tools(news_generator) -> List[BaseTool]:
    """创建新闻工具集合"""
    return [
        GetRecentNewsTool(news_generator=news_generator),
        SearchNewsBySymbolTool(news_generator=news_generator),
    ]
