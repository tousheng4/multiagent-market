# ReAct 多智能体股票交易所 — AI 开发者分步实现计划

> 每一步都必须小而具体，完成后立即运行验证测试。只写指令，不写代码。

---

## 阶段 0：环境验证

### Step 0.1：验证现有代码可运行

**指令**：在项目根目录执行 `python main.py`，观察是否正常输出 snapshot 信息（包含 step、prices、spreads、agent_values）。

**验证通过条件**：终端打印出至少 5 行 snapshot，且最后无报错。

---

## 阶段 1：事件系统扩展

### Step 1.1：在 event_hub.py 添加 EV_NEWS 常量

**指令**：打开 `src/environment/event_hub.py`，在 `EV_AUDIT` 常量下方添加：

```python
EV_NEWS: Final[str] = "news"
```

确保它与其他常量格式一致。

**验证**：执行 `python -c "from src.environment.event_hub import EV_NEWS; print(EV_NEWS)"`，输出应为 `news`。

---

### Step 1.2：确认 __init__.py 导出 EV_NEWS

**指令**：打开 `src/__init__.py`，在 `EV_AUDIT` 同行添加 `EV_NEWS`。

**验证**：执行 `python -c "from src import EV_NEWS; print(EV_NEWS)"`，输出应为 `news`。

---

## 阶段 2：模拟新闻生成器

### Step 2.1：创建 src/data/NewsGenerator.py 文件

**指令**：在 `src/data/` 目录下新建文件 `NewsGenerator.py`，包含：
- 类名 `NewsGenerator`
- 初始化参数：`hub: EventHub`, `symbols: List[str]`
- 方法 `generate(step: int)`：根据传入的 step 和 symbols，生成一条伪新闻字符串（如 "AAPL 上涨 2.3%，受益于AI芯片需求旺盛"），通过 `hub.emit(EV_NEWS, {"news": "...", "symbol": "...", "step": step}, src="news_generator")` 发出
- 内部维护一个简单的价格缓存（dict symbol → last_price），用于计算涨跌幅

**验证**：执行以下命令，验证 NewsGenerator 可正常实例化并 emit 事件：

```python
from src.environment.event_hub import EventHub, EV_NEWS
from src.data.NewsGenerator import NewsGenerator

received = []
hub = EventHub()
hub.on(EV_NEWS, lambda msg: received.append(msg))
ng = NewsGenerator(hub=hub, symbols=["AAPL", "TSLA"])
ng.generate(1)
assert len(received) == 1, "should receive 1 news event"
assert "news" in received[0]["payload"], "payload should have news key"
print("OK")
```

输出 `OK` 即通过。

---

## 阶段 3：工具层

### Step 3.1：确认 marketTools.py 与 LangChain 格式兼容

**指令**：读取 `src/agents/tool/marketTools.py`，检查每个 tool 函数是否使用 `@tool` 装饰器，或返回 `Tool` 对象。

**验证**：执行 `python -c "from src.agents.tool.marketTools import *; print('OK')"`，无报错即通过。

如果格式不兼容，在同一文件头部添加 `@tool` 装饰器导入，并给每个函数加上装饰器。

---

### Step 3.2：创建 src/agents/tool/news_tools.py

**指令**：在 `src/agents/tool/` 目录下新建 `news_tools.py`，包含两个 LangChain tool：

1. `get_recent_news(n: int = 10)` — 返回 NewsGenerator 内部缓存的最近 N 条新闻列表（每条包含 news 内容、symbol、step）。NewsGenerator 需维护一个 `self.news_history: List[Dict]` 列表，每次 generate() 时先 append 再 emit。
2. `search_news_by_symbol(symbol: str, n: int = 5)` — 返回指定 symbol 的最近 N 条新闻。

两个函数都使用 `@tool` 装饰器。

**验证**：执行以下测试：

```python
from src.agents.tool.news_tools import get_recent_news, search_news_by_symbol
from src.data.NewsGenerator import NewsGenerator
from src.environment.event_hub import EventHub

hub = EventHub()
ng = NewsGenerator(hub=hub, symbols=["AAPL", "TSLA"])
# 模拟生成几条新闻
ng.generate(1)
ng.generate(2)
# 通过 news_tools 读取
news = get_recent_news(10)
assert len(news) >= 2, "should have at least 2 news"
symbol_news = search_news_by_symbol("AAPL", 5)
assert isinstance(symbol_news, list), "should return list"
print("OK")
```

输出 `OK` 即通过。

---

### Step 3.3：创建 src/agents/tool/memory_tools.py

**指令**：在 `src/agents/tool/` 目录下新建 `memory_tools.py`，包含两个 LangChain tool：

1. `read_memory(agent_id: str, limit: int = 100)` — 读取指定 agent 的最近记忆，返回列表。优先用 MemoryStore，失败时返回空列表。
2. `write_memory(agent_id: str, message: str, meta: Optional[dict] = None)` — 写入一条记忆到 MemoryStore。

使用 `@tool` 装饰器。

**验证**：执行以下测试：

```python
from src.agents.tool.memory_tools import read_memory, write_memory
# 验证函数可导入
assert callable(read_memory)
assert callable(write_memory)
print("OK")
```

输出 `OK` 即通过。

---

## 阶段 4：ReAct Agent 基类

### Step 4.1：创建 src/agents/ReActAgent.py

**指令**：在 `src/agents/` 目录下新建 `ReActAgent.py`，包含抽象基类 `ReActAgent`（继承自 `BaseAgent`），提供以下方法框架：

1. `observe()` — 抽象方法，返回观察到的上下文 dict（市场数据、新闻、记忆等）
2. `think(observation: dict) -> str` — 调用 MiniMax LLM，返回推理字符串。内部使用 LangChain 的 `ChatMinimax` 模型 + tool calling 循环
3. `act(thought: str)` — 解析 thought，调用相应 tool 执行下单等操作
4. `step()` — 每步调用 `observe()` → `think()` → `act()`

__init__ 参数与 BaseAgent 相同，额外接收 `model_name: str = "abab6.5s-chat"`（MiniMax 模型名）和 `tools: List[Tool]`。

**验证**：执行 `python -c "from src.agents.ReActAgent import ReActAgent; print('OK')"`，无报错即通过。

---

## 阶段 5：Agent 实现

### Step 5.1：创建 src/agents/ReActAgents.py（NewsAgent）

**指令**：在同一目录下新建或扩展 `ReActAgents.py`，实现 `NewsAgent` 类（继承 `ReActAgent`）：

- `observe()`：调用 `get_recent_news(20)` 获取最近 20 条新闻
- `think(observation)`：Prompt 让 LLM 根据新闻推理宏观情绪，给出"看多/看空/中性"结论，附上理由
- `act(thought)`：将 LLM 结论写入记忆（调用 `write_memory`）

**验证**：实例化 NewsAgent，调用 `step()` 一轮，执行 `python -c "...（自行构造 mock hub 和 exchange）..."` 验证不报错。

---

### Step 5.2：创建 src/agents/ReActAgents.py（StrategyAgent）

**指令**：实现 `StrategyAgent` 类（继承 `ReActAgent`）：

- `observe()`：调用 `get_market_data(symbol)` 获取行情、`get_account()` 获取持仓、`get_recent_news(10)` 获取新闻
- `think(observation)`：Prompt 让 LLM 读取以上数据，决定买入/卖出/持有，输出具体股票、数量、价格
- `act(thought)`：解析 LLM 输出，调用 `submit_order` 执行

**验证**：同 Step 5.1，分别对 StrategyAgent 跑一轮 step 不报错。

---

### Step 5.3：创建 src/agents/ReActAgents.py（RiskAgent）

**指令**：实现 `RiskAgent` 类（继承 `ReActAgent`）：

- 不走 LLM 推理，注册到 EventHub 的 `EV_ORDER_CMD` 事件
- `on_order_cmd(event)` 方法：检查订单（保证金、持仓上限、单笔风险），不合规则 emit `EV_ORDER_REJECT` 并记录日志
- 限仓规则：单 symbol 持仓不超过 200 股，单笔订单不超过 100 股，保证金不足拒绝

**验证**：手动构造一个不合规订单事件，验证 RiskAgent 发出 EV_ORDER_REJECT：

```python
from src.environment.event_hub import EventHub, EV_ORDER_CMD, EV_ORDER_REJECT
hub = EventHub()
# 注册 RiskAgent
reject_count = [0]
hub.on(EV_ORDER_REJECT, lambda m: reject_count.__setitem__(0, reject_count[0] + 1))
# 手动发一个违规 EV_ORDER_CMD 事件
hub.emit(EV_ORDER_CMD, {"order_id": "x", "agent_id": "a1", "symbol": "AAPL", "side": "BUY", "quantity": 500, "price": 150}, src="test")
assert reject_count[0] >= 1, "should reject"
print("OK")
```

输出 `OK` 即通过。

---

### Step 5.4：创建 src/agents/ReActAgents.py（EvaluatorAgent）

**指令**：实现 `EvaluatorAgent` 类（继承 `ReActAgent`）：

- `observe()`：调用 `get_account()` 获取所有 Agent 账户信息（持仓、现金、总权益）
- `think(observation)`：Prompt 让 LLM 汇总绩效数据，给出简短评估意见
- `act(thought)`：将评估写入记忆

**验证**：同 Step 5.1，对 EvaluatorAgent 跑一轮 step 不报错。

---

## 阶段 6：Simulation 集成

### Step 6.1：修改 Simulation 每步发出 EV_NEWS

**指令**：打开 `src/environment/simulation.py`，找到 `step()` 方法。在 `self._emit_data()` 调用之前，添加：

```python
self.hub.emit(EV_NEWS, {"step": self._step}, src="simulation")
```

确保导入了 `EV_NEWS`。

**验证**：在 `main.py` 中注册一个 EV_NEWS 监听，打印收到的消息，运行 `python main.py` 确认每步都有 news 事件发出。

---

### Step 6.2：修改 main.py 注册所有新 Agent

**指令**：修改 `main.py`：
- 保留现有 MarketMakerAgent、MomentumAgent
- 新增 NewsGenerator 实例并注册
- 新增 NewsAgent、StrategyAgent、RiskAgent、EvaluatorAgent 实例并注册

所有 Agent 注册到 Simulation（调用 `sim.register_agent()`）。

**验证**：运行 `python main.py`，观察终端输出包含各类 Agent 的决策日志（新闻情绪、交易信号等），无报错即通过。

---

## 阶段 7：端到端验证

### Step 7.1：完整流程验证

**指令**：执行 `python main.py`，观察完整 10 步 simulation 输出。

**验证通过条件**：
1. 无任何 Python 异常或 traceback
2. 终端打印出包含 `step`、`prices`、`spreads`、`agent_values` 的 snapshot（至少 5 行）
3. 审计日志文件 `data/processed/audit.jsonl` 存在且包含内容
4. 进程正常退出（exit code 0）

---

## 阶段 8：清理与收尾

### Step 8.1：确认所有新建文件路径

**指令**：检查以下文件是否存在：

```
src/data/NewsGenerator.py
src/agents/ReActAgent.py
src/agents/ReActAgents.py
src/agents/tool/news_tools.py
src/agents/tool/memory_tools.py
docs/superpowers/specs/2026-04-13-react-multiagent-exchange-design.md
PLAN2.md（当前文件）
```

使用 `ls` 或 glob 确认每个文件路径。

**验证**：每个文件路径都能 `cat` 读取到内容。

---

## 注意事项

1. **严格按顺序执行**：阶段 0 → 8，每个 Step 完成后必须立即运行验证测试，通过才能继续。
2. **不跳步**：不要在当前 Step 未验证通过前进入下一个 Step。
3. **MiniMax API Key**：在 `~/.env` 或环境变量中配置 `MINIMAX_API_KEY`，否则 LangChain 调用会失败。
4. **Redis/Mongo 可选**：如果 Redis/Mongo 未运行，MemoryStore 会降级到本地内存，不影响核心功能。
5. **工具调用超时**：MiniMax LLM 调用可能需要几秒，确保 timeout 设置合理（建议 30s 以上）。
