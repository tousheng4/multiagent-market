"""
ReAct Agent 实现：NewsAgent、StrategyAgent、RiskAgent、EvaluatorAgent
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from .ReActAgent import ReActAgent
from ..environment.event_hub import EV_ORDER_CMD

if TYPE_CHECKING:
    from ..data.NewsGenerator import NewsGenerator
    from ..environment.event_hub import EventHub
    from ..market.models.exchange import Exchange


class NewsAgent(ReActAgent):
    """
    新闻分析 Agent

    职责：读取最近的模拟新闻，推理宏观情绪，将结论写入记忆。
    """

    def __init__(
        self,
        agent_id: str,
        exchange: "Exchange",
        symbols: List[str],
        tools: List[Any],
        news_generator: "NewsGenerator",
        memory_store: Any = None,
    ):
        super().__init__(agent_id, exchange, symbols, tools, memory_store)
        self.news_generator = news_generator

    def observe(self) -> Dict[str, Any]:
        """读取最近 20 条新闻"""
        try:
            news_list = self.news_generator.get_recent_news(20)
            news_texts = [
                f"[Step {n.get('step', '?')}] {n.get('symbol', '?')}: {n.get('news', '')} (涨跌: {n.get('change_pct', 0):.2f}%)"
                for n in news_list
            ]
            return {
                "recent_news": news_texts[-10:],  # 最近10条
                "news_count": len(news_list),
            }
        except Exception as e:
            return {"recent_news": [], "news_count": 0, "error": str(e)}

    def think(self, observation: Dict[str, Any]) -> str:
        """让 LLM 根据新闻推理宏观情绪"""
        system_prompt = (
            "你是一个专业的财经新闻分析师。你的职责是根据最近的模拟新闻，\n"
            "判断当前市场的宏观情绪（看多/看空/中性），并给出简短理由。\n"
            "新闻来自模拟数据生成器，可能包含噪声，请忽略微小幅度的波动。\n"
            "请用中文回答，格式：情绪：[看多/看空/中性]，理由：xxx"
        )
        user_prompt = "最近新闻：\n" + "\n".join(observation.get("recent_news", []))

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        try:
            response = self.llm_with_tools.invoke(messages)
            return response.content or ""
        except Exception as e:
            return f"LLM error: {e}"

    def act(self, thought: str) -> None:
        """将 LLM 情绪分析结论写入记忆"""
        if not thought or thought.startswith("LLM error"):
            return
        self.log(
            f"宏观情绪分析: {thought}",
            meta={"event": "news_sentiment", "step": self.step_count},
        )
        if self.memory_store:
            try:
                self.memory_store.append(
                    self.agent_id,
                    self.step_count,
                    f"宏观情绪分析: {thought}",
                    {"type": "sentiment", "raw": thought},
                )
            except Exception:
                pass

    def get_system_prompt(self) -> str:
        return (
            "你是一个专业的财经新闻分析师。你的职责是根据最近的模拟新闻，\n"
            "判断当前市场的宏观情绪（看多/看空/中性），并给出简短理由。\n"
            "新闻来自模拟数据生成器，请忽略微小幅度的波动，关注明显趋势。\n"
            "请用中文回答，格式：情绪：[看多/看空/中性]，理由：xxx"
        )


class StrategyAgent(ReActAgent):
    """
    量化策略 Agent

    职责：读取行情、新闻、记忆，推理生成交易信号，调用 submit_order。
    """

    def __init__(
        self,
        agent_id: str,
        exchange: "Exchange",
        symbols: List[str],
        tools: List[Any],
        memory_store: Any = None,
    ):
        super().__init__(agent_id, exchange, symbols, tools, memory_store)

    def observe(self) -> Dict[str, Any]:
        """收集所有股票的行情数据和账户信息"""
        result = {}
        for symbol in self.symbols:
            try:
                market = self.exchange.get_market_data(symbol)
                result[symbol] = market
            except Exception:
                result[symbol] = {}

        try:
            account = self.exchange.get_account(self.agent_id)
        except Exception:
            account = {}

        # 获取最近的记忆
        recent_mem = []
        if self.memory_store:
            try:
                recent_mem = self.memory_store.recent(self.agent_id, 5)
            except Exception:
                pass

        return {
            "market_data": result,
            "account": account,
            "recent_memory": recent_mem,
        }

    def think(self, observation: Dict[str, Any]) -> str:
        """让 LLM 基于行情和账户信息生成交易决策"""
        market_data_str = json.dumps(observation.get("market_data", {}), indent=2, default=str)
        account_str = json.dumps(observation.get("account", {}), default=str)
        memory_str = json.dumps(observation.get("recent_memory", []), default=str)

        system_prompt = (
            "你是一个严格的量化交易策略师。你必须基于客观的市场数据做出决策。\n"
            "决策规则：\n"
            "1. 只有在中长期趋势明确时才能买入/卖出，避免频繁交易\n"
            "2. 单笔订单数量不超过50股\n"
            "3. 现金余额必须足以覆盖买入成本\n"
            "4. 持仓不能超过200股/标的\n"
            "5. 无明确机会时应持有（不操作）\n"
            "当需要下单时，请按以下格式调用 submit_order 工具：\n"
            '{"name": "submit_order", "parameters": {"symbol": "AAPL", "side": "buy", "quantity": 10, "order_type": "limit", "price": 150.0}}\n'
            "不需要下单时，回复：保持观望\n"
            "请用中文回答。"
        )
        user_prompt = (
            f"当前账户：\n{account_str}\n\n"
            f"行情数据：\n{market_data_str}\n\n"
            f"最近记忆：\n{memory_str}\n\n"
            "请做出交易决策。"
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        try:
            response = self.llm_with_tools.invoke(messages)
            return response.content or ""
        except Exception as e:
            return f"LLM error: {e}"

    def act(self, thought: str) -> None:
        """解析 LLM 输出，调用 submit_order"""
        if not thought or thought.startswith("LLM error") or "保持观望" in thought:
            return

        # 尝试从 thought 中解析 JSON tool call
        # MiniMax 通常在 tool_calls 字段中返回，而不是在 content 中
        # 这里处理纯文本格式的决策（备用方案）
        pattern = r'submit_order.*?\{[^{}]*"symbol"\s*:\s*"([^"]+)".*?"side"\s*:\s*"([^"]+)".*?"quantity"\s*:\s*(\d+).*?"price"\s*:\s*([\d.]+)\}'
        matches = re.findall(pattern, thought, re.DOTALL)
        for match in matches:
            symbol, side, quantity, price = match
            try:
                self.exchange.submit_order(
                    agent_id=self.agent_id,
                    symbol=symbol,
                    order_type=2,  # LIMIT
                    side=1 if side == "buy" else 0,  # BUY=1, SELL=0
                    quantity=int(quantity),
                    price=float(price),
                )
                self.log(
                    f"下单: {side.upper()} {quantity} {symbol} @ {price}",
                    meta={"event": "order", "symbol": symbol, "side": side},
                )
            except Exception as e:
                self.log(f"下单失败: {e}", meta={"event": "order_error"})


class RiskAgent:
    """
    风控 Agent（非 LLM 决策，纯规则）

    职责：监听 EV_ORDER_CMD，强制拦截不合规订单。
    注册到 EventHub，在订单进入撮合前进行检查。
    """

    # 风控规则常量
    MAX_POSITION_PER_SYMBOL = 200
    MAX_ORDER_QUANTITY = 100
    MAX_ORDER_VALUE = 50000.0

    def __init__(
        self,
        agent_id: str,
        exchange: "Exchange",
        symbols: List[str],
        tools: List[Any],
        hub: "EventHub",
        memory_store: Any = None,
    ):
        # RiskAgent 直接实现，不走 LLM
        self.agent_id = agent_id
        self.exchange = exchange
        self.symbols = symbols
        self.memory_store = memory_store
        self.step_count = 0
        self.hub = hub
        self.memory: list = []
        # 注册到 EV_ORDER_CMD 事件
        self._order_sid = self.hub.on(
            EV_ORDER_CMD, self._on_order_cmd, name=f"risk_{agent_id}"
        )

    def step(self) -> None:
        """RiskAgent 不走 ReAct 循环，每步只记录风控状态"""
        self.step_count += 1
        # 定期输出风控报告到记忆
        self._check_all_positions()

    def log(self, message: str, meta: Any = None) -> None:
        """记录日志"""
        entry = {"step": self.step_count, "msg": message}
        if meta:
            entry["meta"] = meta
        self.memory.append(entry)
        if self.memory_store:
            try:
                self.memory_store.append(self.agent_id, self.step_count, message, meta)
            except Exception:
                pass

    def _on_order_cmd(self, msg: Dict[str, Any]) -> None:
        """检查订单是否合规，不合规则拦截"""
        payload = msg.get("payload") or {}
        order_id = payload.get("order_id", "?")
        agent_id = payload.get("agent_id", "?")
        symbol = payload.get("symbol", "?")
        side = payload.get("side", "?")
        quantity = payload.get("quantity", 0)
        price = payload.get("price", 0)
        order_type = payload.get("order_type", "limit")

        # 规则1：单笔数量不超过 100
        if quantity > self.MAX_ORDER_QUANTITY:
            self._reject(
                order_id,
                agent_id,
                f"数量超限: {quantity} > {self.MAX_ORDER_QUANTITY}",
            )
            return

        # 规则2：单笔金额不超过 50000
        order_value = quantity * (price or 0)
        if order_value > self.MAX_ORDER_VALUE:
            self._reject(
                order_id,
                agent_id,
                f"单笔金额超限: {order_value:.2f} > {self.MAX_ORDER_VALUE}",
            )
            return

        # 规则3：空头不允许（卖出必须有持仓）
        if side == "sell":
            try:
                account = self.exchange.get_account(agent_id)
                position = account.get("positions", {}).get(symbol, 0)
                if position < quantity:
                    self._reject(
                        order_id,
                        agent_id,
                        f"持仓不足: 持有{position}股，卖出{quantity}股",
                    )
                    return
            except Exception:
                pass

        # 规则4：多头不允许保证金不足（简化版：检查现金）
        if side == "buy":
            try:
                account = self.exchange.get_account(agent_id)
                cash = account.get("cash", 0)
                cost = quantity * (price or 0)
                if cash < cost:
                    self._reject(
                        order_id,
                        agent_id,
                        f"现金不足: 现金{cash:.2f}，需要{cost:.2f}",
                    )
                    return
            except Exception:
                pass

        # 合规，转发到 Exchange（通过 event payload 让 Exchange 处理）
        self.log(
            f"订单放行: {agent_id} {side.upper()} {quantity} {symbol}",
            meta={
                "event": "risk_pass",
                "order_id": order_id,
                "agent_id": agent_id,
            },
        )

    def _reject(self, order_id: str, agent_id: str, reason: str) -> None:
        """发出拒绝事件"""
        self.hub.emit(
            "order_reject",
            {
                "order_id": order_id,
                "agent_id": agent_id,
                "reason": reason,
                "step": self.step_count,
            },
            src=self.agent_id,
        )
        self.log(
            f"风控拦截: {agent_id} 订单被拒绝，原因: {reason}",
            meta={"event": "risk_reject", "reason": reason},
        )

    def _check_all_positions(self) -> None:
        """定期检查所有 Agent 的持仓"""
        violations = []
        for agent_id in self.exchange.cash_balances:
            try:
                account = self.exchange.get_account(agent_id)
                positions = account.get("positions", {})
                for symbol, qty in positions.items():
                    if qty > self.MAX_POSITION_PER_SYMBOL:
                        violations.append(f"{agent_id} 持仓违规: {symbol}={qty}")
            except Exception:
                pass

        if violations:
            self.log(
                f"风控告警: {violations}",
                meta={"event": "risk_violation", "violations": violations},
            )


class EvaluatorAgent(ReActAgent):
    """
    绩效评估 Agent

    职责：每步汇总所有 Agent 的绩效，输出评估意见到记忆。
    """

    def __init__(
        self,
        agent_id: str,
        exchange: "Exchange",
        symbols: List[str],
        tools: List[Any],
        memory_store: Any = None,
    ):
        super().__init__(agent_id, exchange, symbols, tools, memory_store)

    def observe(self) -> Dict[str, Any]:
        """收集所有 Agent 的账户快照"""
        snapshots = {}
        for agent_id in self.exchange.cash_balances:
            try:
                account = self.exchange.get_account(agent_id)
                snapshots[agent_id] = {
                    "cash": account.get("cash", 0),
                    "positions": account.get("positions", {}),
                    "portfolio_value": account.get("portfolio_value", 0),
                }
            except Exception:
                snapshots[agent_id] = {}
        return {"agent_snapshots": snapshots}

    def think(self, observation: Dict[str, Any]) -> str:
        """让 LLM 汇总绩效并给出简短评价"""
        system_prompt = (
            "你是一个专业的基金绩效评估师。\n"
            "你的职责是汇总所有 Agent 的绩效数据，给出简短客观的评价。\n"
            "请用中文回答，格式：评估：[评价内容]，关键点：xxx"
        )
        user_prompt = (
            "各 Agent 绩效快照：\n"
            + json.dumps(observation.get("agent_snapshots", {}), indent=2, default=str)
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        try:
            response = self.llm_with_tools.invoke(messages)
            return response.content or ""
        except Exception as e:
            return f"LLM error: {e}"

    def act(self, thought: str) -> None:
        """将评估结果写入记忆"""
        if not thought or thought.startswith("LLM error"):
            return
        self.log(
            f"绩效评估: {thought}",
            meta={"event": "evaluation", "step": self.step_count},
        )
        if self.memory_store:
            try:
                self.memory_store.append(
                    self.agent_id,
                    self.step_count,
                    f"绩效评估: {thought}",
                    {"type": "evaluation", "raw": thought},
                )
            except Exception:
                pass
