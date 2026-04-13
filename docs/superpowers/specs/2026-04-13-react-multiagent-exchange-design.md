# ReAct 事件驱动多智能体股票交易所 — 设计方案

## Context

当前项目是一个多智能体市场模拟系统，已有：
- blinker 事件总线（EventHub）、订单撮合引擎（Exchange）、规则型 Agent
- LangChain 工具封装（marketTools.py）但未接入真实 LLM
- MemoryStore 接口（本地+Redis+Mongo 三层）
- 数据管道和 Simulation 仿真循环

**目标**：将系统升级为基于 ReAct 的 LLM 多智能体股票交易所，每个 Agent 每步执行完整的 `observe → think → act` 循环，通过 MiniMax + LangChain 实现 tool calling 推理，强制风控拦截。

---

## Architecture

```
EventHub (blinker, 共享事件总线)
├── Simulation          — 仿真循环，每步: 发 data 事件 → 各 Agent ReAct → 撮合 → 发 snapshot
├── Exchange            — 订单簿撮合，接收 Agent 订单，发成交/拒绝事件
├── NewsGenerator       — 模拟新闻生成器，按时间步生成伪新闻
├── AuditWriter         — 审计日志写入
│
├── ReAct Agents (每步完整 ReAct 循环)
│   ├── NewsAgent         — 读取新闻事件，推理宏观方向
│   ├── StrategyAgent     — 读取行情+指标，推理技术信号，下单
│   ├── RiskAgent         — 监听所有持仓，强制拦截违规订单
│   ├── EvaluatorAgent    — 汇总绩效，输出评估意见
│   │
│   └── Rule Agents (保留现有实现，不改)
│       ├── MarketMakerAgent
│       ├── MomentumAgent
│       └── RandomAgent
│
└── MemoryStore (三层: 本地缓存 → Redis → Mongo)
```

---

## Agent 详细设计

### 1. ReActAgent 基类

每个 Agent 每步执行：
```
observe()  → 读取 EventHub 缓存的市场数据/新闻/自己记忆
think()    → 调用 MiniMax (LangChain tool calling)，生成推理 + action
act()      → 执行下单/撤单/读新闻等 tool 调用
```

关键文件：`src/agents/ReActAgent.py`（新建）

### 2. NewsAgent

- **工具**：read_news（查模拟新闻）、log（写记忆）
- **行为**：每步读取过去 N 条新闻，推理"当前宏观情绪"，输出文字结论存储到记忆
- **新闻来源**：NewsGenerator 发出的 `EV_NEWS` 事件

### 3. StrategyAgent

- **工具**：get_market_data（查行情）、get_account（查持仓）、submit_order、cancel_order、read_memory、log
- **行为**：每步观察行情 + 新闻 + 自己的记忆，推理生成买入/卖出/持有信号，调用 submit_order

### 4. RiskAgent

- **工具**：get_account（查所有 Agent 持仓）、log
- **行为**：监听 `EV_ORDER_CMD` 事件，在订单进入撮合前强制检查：
  - 保证金是否足够
  - 持仓是否超限
  - 单笔风险是否超标
- **强制拦截**：不合规订单 → emit `EV_ORDER_REJECT`，不进入 Exchange

### 5. EvaluatorAgent

- **工具**：get_account、read_memory、log
- **行为**：每步汇总所有 Agent 的 PnL、持仓，回测绩效指标，输出评估意见到记忆

### 6. Rule Agents（现有，保留）

MarketMakerAgent、MomentumAgent、RandomAgent 不改，复用现有实现。

---

## Tool 实现

现有 `src/agents/tool/marketTools.py` 已有封装，需确认与 LangChain tool 格式兼容。

新增 tools：
- `news_tools.py` — `get_recent_news`、`search_news_by_symbol`
- `memory_tools.py` — `read_memory`、`write_memory`（复用 MemoryStore）

---

## 新闻生成器

`src/data/NewsGenerator.py`（新建）：
- 每次 `Simulation.step()` 时，根据价格变动生成伪新闻
- 例如："AAPL 上涨 2.3%，受益于 AI 芯片需求旺盛"
- 通过 EventHub 发出 `EV_NEWS` 事件

---

## 风控流程

```
Agent.submit_order()
    ↓
EventHub.emit(EV_ORDER_CMD, ...)
    ↓
RiskAgent.on_order_cmd() ← 强制拦截检查
    ├─ 合规 → Exchange.submit_order()
    └─ 不合规 → emit EV_ORDER_REJECT（订单丢弃）
```

---

## 关键文件

| 文件 | 操作 |
|------|------|
| `src/agents/ReActAgent.py` | 新建 |
| `src/agents/ReActAgents.py`（News/Strategy/Risk/Evaluator） | 新建 |
| `src/agents/tool/news_tools.py` | 新建 |
| `src/agents/tool/memory_tools.py` | 新建 |
| `src/data/NewsGenerator.py` | 新建 |
| `src/environment/event_hub.py` | 增加 EV_NEWS, EV_ORDER_CMD payload 扩展 |
| `src/environment/simulation.py` | 每步发 EV_DATA 前先发 EV_NEWS |
| `src/agents/tool/marketTools.py` | 确认 LangChain tool 格式兼容 |

---

## 实现顺序（阶段）

1. **基础骨架** — ReActAgent 基类 + MiniMax + LangChain 打通
2. **工具层** — marketTools + newsTools + memoryTools
3. **事件扩展** — EventHub 加 EV_NEWS，NewsGenerator
4. **Agent 实现** — NewsAgent → StrategyAgent → RiskAgent → EvaluatorAgent
5. **集成测试** — main.py 五类 Agent 一起跑

---

## Verification

```bash
python main.py
```

观察输出：
- 每步有 `data` snapshot 打印（prices, spreads, agent_values）
- ReAct Agent 有 MiniMax 调用日志
- RiskAgent 有拦截记录（如有）
- 最终审计日志写入 `data/processed/audit.jsonl`
