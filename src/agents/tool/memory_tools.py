"""
记忆读写工具 - 供 LangChain ReAct Agent 使用

提供读取和写入 Agent 记忆的能力
"""

from typing import Any, Dict, List, Optional

from langchain.tools import BaseTool
from pydantic import BaseModel, Field


class ReadMemoryInput(BaseModel):
    agent_id: str = Field(description="Agent ID，例如 'news-agent-1'")
    limit: int = Field(default=100, gt=0, le=500, description="最多返回的记忆条数")


class ReadMemoryTool(BaseTool):
    """读取 Agent 记忆的工具"""

    name: str = "read_memory"
    description: str = """读取指定 Agent 的最近记忆记录。

    参数：
    - agent_id: Agent 的唯一标识符
    - limit: 最多返回的条数（默认 100 条）

    返回该 Agent 最近的记忆列表，每条包含 message 文本和 step 时间戳。"""

    args_schema: type[BaseModel] = ReadMemoryInput
    memory_store: Any = Field(exclude=True, default=None)

    class Config:
        arbitrary_types_allowed = True

    def _run(self, agent_id: str, limit: int = 100) -> Dict[str, Any]:
        try:
            if self.memory_store is None:
                return {"success": False, "error": "memory_store not configured"}
            entries = self.memory_store.recent(agent_id, limit)
            return {
                "success": True,
                "agent_id": agent_id,
                "num_entries": len(entries),
                "entries": entries,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _arun(self, agent_id: str, limit: int = 100) -> Dict[str, Any]:
        raise NotImplementedError("read_memory does not support async")


class WriteMemoryInput(BaseModel):
    agent_id: str = Field(description="Agent ID，例如 'news-agent-1'")
    message: str = Field(description="要写入的记忆内容文本")
    step: Optional[int] = Field(default=None, description="当前仿真步（可选）")
    meta: Optional[Dict] = Field(default=None, description="额外元数据（可选）")


class WriteMemoryTool(BaseTool):
    """写入 Agent 记忆的工具"""

    name: str = "write_memory"
    description: str = """写入一条记忆到指定 Agent 的记忆存储中。

    参数：
    - agent_id: Agent 的唯一标识符
    - message: 要保存的记忆内容（文本）
    - step: 当前仿真步（可选）
    - meta: 额外元数据（可选）

    用于保存 Agent 的推理结果、决策理由或重要观察。"""

    args_schema: type[BaseModel] = WriteMemoryInput
    memory_store: Any = Field(exclude=True, default=None)
    default_agent_id: str = Field(exclude=True, default="")
    current_step_getter: Any = Field(exclude=True, default=None)

    class Config:
        arbitrary_types_allowed = True

    def _run(
        self,
        agent_id: str,
        message: str,
        step: Optional[int] = None,
        meta: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        try:
            if self.memory_store is None:
                return {"success": False, "error": "memory_store not configured"}
            # 如果 step 未提供，尝试从 current_step_getter 获取
            if step is None and self.current_step_getter is not None:
                try:
                    step = self.current_step_getter()
                except Exception:
                    pass
            self.memory_store.append(agent_id, step or 0, message, meta)
            return {"success": True, "agent_id": agent_id, "message": message}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _arun(
        self,
        agent_id: str,
        message: str,
        step: Optional[int] = None,
        meta: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError("write_memory does not support async")


__all__ = ["ReadMemoryTool", "WriteMemoryTool", "create_memory_tools"]


def create_memory_tools(
    memory_store=None, default_agent_id: str = "", current_step_getter=None
) -> List[BaseTool]:
    """创建记忆读写工具集合"""
    return [
        ReadMemoryTool(memory_store=memory_store),
        WriteMemoryTool(
            memory_store=memory_store,
            default_agent_id=default_agent_id,
            current_step_getter=current_step_getter,
        ),
    ]
