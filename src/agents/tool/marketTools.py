"""
市场交易工具 - 供LangChain Agent使用

这些工具允许Agent查询市场数据和提交订单
"""

from typing import Any, Dict, Literal, Optional

from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from ...market.models.exchange import Exchange
from ...market.models.order import OrderSide, OrderType


class GetMarketDataInput(BaseModel):
    """获取市场数据的输入参数"""

    symbol: str = Field(description="股票代码，例如 'AAPL'")


class GetMarketDataTool(BaseTool):
    """获取市场数据工具"""

    name: str = "get_market_data"
    description: str = """获取指定股票的市场数据，包括：
    - 最优买价(best_bid)和卖价(best_ask)
    - 中间价(mid_price)
    - 买卖价差(spread)
    - 最新成交价(last_price)
    - 订单簿深度(bids, asks)
    输入应该是股票代码字符串，例如 'AAPL'"""

    args_schema: type[BaseModel] = GetMarketDataInput
    exchange: Exchange = Field(exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def _run(self, symbol: str) -> Dict[str, Any]:
        """执行工具"""
        try:
            data = self.exchange.get_market_data(symbol)
            return {"success": True, "data": data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _arun(self, symbol: str) -> Dict[str, Any]:
        """异步执行（暂不支持）"""
        raise NotImplementedError("get_market_data does not support async")


class GetAccountInput(BaseModel):
    """获取账户信息的输入参数"""

    pass  # 不需要参数，使用agent自己的ID


class GetAccountTool(BaseTool):
    """获取账户信息工具"""

    name: str = "get_account"
    description: str = """获取当前账户信息，包括：
    - 现金余额(cash)
    - 持仓(positions)
    - 总资产价值(portfolio_value)
    不需要输入参数"""

    args_schema: type[BaseModel] = GetAccountInput
    exchange: Exchange = Field(exclude=True)
    agentId: str = Field(exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def _run(self) -> Dict[str, Any]:
        """执行工具"""
        try:
            return {"success": True, "data": self.exchange.get_account(self.agentId)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _arun(self) -> Dict[str, Any]:
        """异步执行（暂不支持）"""
        raise NotImplementedError("get_account does not support async")


class SubmitOrderInput(BaseModel):
    """提交订单的输入参数"""

    symbol: str = Field(description="股票代码，例如 'AAPL'")
    side: Literal["buy", "sell"] = Field(description="买卖方向: 'buy' 或 'sell'")
    quantity: int = Field(gt=0, description="数量，必须是正整数")
    order_type: Literal["limit", "market"] = Field(
        description="订单类型: 'limit'(限价单) 或 'market'(市价单)"
    )
    price: Optional[float] = Field(
        default=None, description="价格（限价单必须提供，市价单不需要，必须为正）"
    )


class SubmitOrderTool(BaseTool):
    """提交订单工具"""

    name: str = "submit_order"
    description: str = """提交买入或卖出订单。参数说明：
    - symbol: 股票代码 (例如 'AAPL')
    - side: 'buy' 或 'sell'
    - quantity: 数量 (正整数)
    - order_type: 'limit'(限价单) 或 'market'(市价单)
    - price: 价格 (限价单必须提供)

    示例：
    买入100股AAPL，限价150美元: symbol='AAPL', side='buy', quantity=100, order_type='limit', price=150.0
    卖出50股AAPL，市价: symbol='AAPL', side='sell', quantity=50, order_type='market'"""

    args_schema: type[BaseModel] = SubmitOrderInput
    exchange: Exchange = Field(exclude=True)
    agentId: str = Field(exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def _run(
        self,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str,
        price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """执行工具"""
        try:
            # 转换参数
            orderType = OrderType.LIMIT if order_type == "limit" else OrderType.MARKET
            orderSide = OrderSide.BUY if side == "buy" else OrderSide.SELL

            if orderType == OrderType.LIMIT:
                if price is None or price <= 0:
                    return {
                        "success": False,
                        "error": "limit order requires positive price",
                    }
            else:
                price = None

            # 提交订单
            order, trades = self.exchange.submit_order(
                agent_id=self.agentId,
                symbol=symbol,
                order_type=orderType,
                side=orderSide,
                quantity=quantity,
                price=price,
            )

            return {
                "success": True,
                "order_id": order.orderId,
                "status": order.status.value,
                "filled_quantity": order.filledQuantity,
                "remaining_quantity": order.remainingQuantity,
                "num_trades": len(trades),
                "trades": [
                    {
                        "price": t.price,
                        "quantity": t.quantity,
                        "counterparty": (
                            t.sellerId if orderSide == OrderSide.BUY else t.buyerId
                        ),
                    }
                    for t in trades
                ],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _arun(
        self,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str,
        price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """异步执行（暂不支持）"""
        raise NotImplementedError("submit_order does not support async")


class GetTradeHistoryInput(BaseModel):
    """获取交易历史的输入参数"""

    symbol: Optional[str] = Field(
        default=None, description="股票代码（可选），不提供则返回所有股票的交易"
    )
    limit: int = Field(
        default=50, gt=0, le=500, description="返回的最大交易条数，按时间倒序"
    )
    after_ts: Optional[float] = Field(
        default=None, description="仅返回时间戳大于该值的交易记录"
    )


class GetTradeHistoryTool(BaseTool):
    """获取交易历史工具"""

    name: str = "get_trade_history"
    description: str = """获取自己的交易历史记录。
    可以指定股票代码过滤，或不指定获取所有交易。支持 limit 和 after_ts 过滤，按时间倒序返回。"""

    args_schema: type[BaseModel] = GetTradeHistoryInput
    exchange: Exchange = Field(exclude=True)
    agentId: str = Field(exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def _run(
        self,
        symbol: Optional[str] = None,
        limit: int = 50,
        after_ts: Optional[float] = None,
    ) -> Dict[str, Any]:
        """执行工具"""
        try:
            trades = self.exchange.get_trade_history(symbol=symbol, agent_id=self.agentId)

            if after_ts is not None:
                trades = [
                    t
                    for t in trades
                    if t.timestamp is not None and t.timestamp > after_ts
                ]

            trades = sorted(trades, key=lambda t: t.timestamp or 0.0, reverse=True)
            total = len(trades)
            trades = trades[:limit]

            return {
                "success": True,
                "num_trades": len(trades),
                "trades": [
                    {
                        "trade_id": t.tradeId,
                        "symbol": t.symbol,
                        "side": "buy" if t.buyerId == self.agentId else "sell",
                        "price": t.price,
                        "quantity": t.quantity,
                        "timestamp": t.timestamp,
                    }
                    for t in trades
                ],
                "truncated": total > limit,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _arun(
        self,
        symbol: Optional[str] = None,
        limit: int = 50,
        after_ts: Optional[float] = None,
    ) -> Dict[str, Any]:
        """异步执行（暂不支持）"""
        raise NotImplementedError("get_trade_history does not support async")


def create_market_tools(exchange: Exchange, agentId: str):
    """
    创建市场交易工具集合

    Args:
        exchange: 交易所实例
        agentId: Agent ID

    Returns:
        工具列表
    """
    return [
        GetMarketDataTool(exchange=exchange),
        GetAccountTool(exchange=exchange, agentId=agentId),
        SubmitOrderTool(exchange=exchange, agentId=agentId),
        GetTradeHistoryTool(exchange=exchange, agentId=agentId),
    ]
