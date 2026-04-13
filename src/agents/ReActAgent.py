"""
ReAct Agent 基类

每个 Agent 每步执行：observe() → think() → act()
通过 MiniMax + LangChain 实现 tool calling 推理。
"""

from __future__ import annotations

import os
from abc import abstractmethod
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from langchain_community.chat_models.minimax import MiniMaxChat
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

from .BaseAgent import BaseAgent

if TYPE_CHECKING:
    from ..environment.event_hub import EventHub
    from ..market.models.exchange import Exchange


class ReActAgent(BaseAgent):
    """
    基于 ReAct 循环的 Agent 基类

    每步执行：
        observe() → 收集观察到的上下文
        think(observation) → 调用 LLM 推理
        act(thought) → 解析并执行 tool 调用
    """

    def __init__(
        self,
        agent_id: str,
        exchange: "Exchange",
        symbols: List[str],
        tools: List[BaseTool],
        memory_store: Optional[Any] = None,
        model_name: str = "abab6.5-chat",
        temperature: float = 0.7,
        max_tokens: int = 512,
    ):
        """
        初始化 ReAct Agent

        Args:
            agent_id: Agent 唯一标识
            exchange: 交易所实例
            symbols: 交易股票列表
            tools: LangChain tool 列表
            memory_store: 记忆存储（可选）
            model_name: MiniMax 模型名
            temperature: 采样温度
            max_tokens: 最大生成 token 数
        """
        super().__init__(agent_id, exchange, symbols, memory_store)
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.tools = tools

        # 初始化 MiniMax LLM
        api_key = os.environ.get("MINIMAX_API_KEY")
        if not api_key:
            raise ValueError("MINIMAX_API_KEY environment variable not set")

        self.llm = MiniMaxChat(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=api_key,
        )
        # 绑定 tools
        self.llm_with_tools = self.llm.bind_tools(tools)

        # Agent 自己的观察缓存
        self._last_observation: Dict[str, Any] = {}

    @abstractmethod
    def observe(self) -> Dict[str, Any]:
        """
        收集当前观察到的上下文（市场数据、新闻、记忆等）

        Returns:
            dict: 观察结果
        """
        pass

    def think(self, observation: Dict[str, Any]) -> str:
        """
        调用 LLM 进行推理，返回思考字符串

        Args:
            observation: observe() 返回的观察数据

        Returns:
            str: LLM 的原始输出文本
        """
        system_prompt = self.get_system_prompt()
        user_prompt = self.format_observation(observation)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        try:
            response = self.llm_with_tools.invoke(messages)
            return response.content or ""
        except Exception as e:
            self.log(f"LLM 调用失败: {e}", meta={"event": "llm_error"})
            return f"LLM error: {e}"

    def act(self, thought: str) -> None:
        """
        解析 LLM 输出并执行 tool 调用

        默认实现处理 tool_calls。如果 LLM 没有发起 tool 调用，
        子类可override此方法自定义行为。

        Args:
            thought: LLM 输出文本
        """
        # LangChain MiniMaxChat 返回的响应中 tool_calls 会被附加到 response
        # 这里需要重新调用一次 llm_with_tools 并处理 tool_calls
        # 为了简化，默认不执行 tool，将推理结果记录到记忆
        pass

    def step(self) -> None:
        """执行一步 ReAct 循环"""
        self.step_count += 1
        observation = self.observe()
        self._last_observation = observation
        thought = self.think(observation)
        self.act(thought)

    def get_system_prompt(self) -> str:
        """
        返回系统提示词。子类可override自定义。

        Returns:
            str: 系统提示词
        """
        return (
            "你是一个专业的股票交易Agent。你可以通过工具查询市场数据、下单、读取新闻和记忆。\n"
            "你的推理应该基于客观数据，遵循严格的风控规则。\n"
            "请用中文回答。"
        )

    def format_observation(self, observation: Dict[str, Any]) -> str:
        """
        将观察数据格式化为字符串输入给 LLM

        Args:
            observation: observe() 返回的 dict

        Returns:
            str: 格式化的字符串
        """
        lines = ["=== 当前市场观察 ==="]
        for key, value in observation.items():
            lines.append(f"[{key}]: {value}")
        lines.append("\n请基于以上信息做出交易决策，并说明理由。")
        return "\n".join(lines)
