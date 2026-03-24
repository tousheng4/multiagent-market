## 目标概述
围绕数据管线、事件驱动仿真、消息解耦、LLM 多智能体、可视化与回放，补全仓库缺口，形成可复现实验与回测的整体闭环。

## 现状对照（已具备）
- 基础数据加载与步进：`src/data/pipeline.py` 读取本地 `data/raw` 并按步推进行情快照。
- 事件驱动的仿真骨架：`src/environment/simulation.py` 使用 blinker 信号解耦数据与快照。
- 交易所撮合与事件信号：`src/market/models/exchange.py` 提供订单与成交事件。
- 规则型智能体与记忆存储接口：`src/agents/SimpleAgents.py`、`src/agents/memory/memoryStore.py`。
- Redis/Mongo 连接器雏形：`src/utils/connectors/RedisConnector.py`、`src/utils/connectors/MongoConnector.py`。
- LangChain 工具封装：`src/agents/tool/marketTools.py`，但未接入真正的 LLM Agent。

## 主要缺口（按需求逐条对照）
1. **Stooq + 因子数据的完整管线**：目前是“本地 CSV 读取 + 索引对齐”，缺少下载、清洗、日期对齐与统一快照输出的完整流程与可复用产物。
2. **事件驱动引擎的异步扩展**：现有 blinker 信号同步分发，未提供异步/队列化扩展接口或调度器。
3. **Kafka 解耦撮合与上下游**：未实现订单/成交/快照主题、生产者/消费者与幂等回报、审计流。
4. **LLM 多智能体框架**：仅有 LLM Agent 雏形与工具封装，缺少数据/新闻/策略/风控/执行/评估多角色编排。
5. **分层记忆体系落地**：MemoryStore 结构具备，但未在仿真中集成“本地 + Redis + Mongo”协同与回读策略。
6. **Notebook 交互可视化与回放**：未提供行情/盘口/成交/PNL 回放与对比的 Notebook 实例。

## 补全计划（可执行步骤）
### 阶段 1：数据管线与快照统一
- 建立数据下载与清洗脚本的统一入口（包含 Stooq 与 Fama-French），规范输出字段与日期格式。
- 在 `DataLoader` 中增加日期解析、缺失处理、统一时区/频率。
- 引入基于日期的多源对齐逻辑（价格与因子 join），输出“统一快照序列”。
- 将快照序列持久化为可复用产物（如 Parquet/CSV），并在 `DataFeed` 中优先读取快照产物。

### 阶段 2：事件驱动与异步扩展
- 为 `Simulation` 增加可插拔的事件分发器接口（同步/异步实现）。
- 提供异步队列适配（如 `asyncio.Queue`），保证数据推送与策略决策解耦。
- 明确事件协议（data/snapshot/order/trade）及 payload schema。

### 阶段 3：Kafka 解耦与流式审计
- 定义 Kafka 主题：`orders`、`trades`、`snapshots`、`audit`。
- 在撮合核心侧增加生产者（订单提交、成交、快照输出）。
- 在上游策略与下游风控侧增加消费者，保证幂等回报与可重放审计。
- 设计消息 schema 与幂等键（订单 ID / 成交 ID / 快照时间戳）。

### 阶段 4：多智能体与 LLM 编排
- 实现 DataAgent、NewsAgent、StrategyAgent、RiskAgent、ExecutionAgent、Evaluator。
- 统一消息传递通道（记忆存储或轻量队列），并定义 JSON 建议格式。
- 将 LangChain 工具真正接入 StrategyAgent，完成工具调用闭环。

### 阶段 5：分层记忆体系
- 在仿真启动时配置 MemoryStore（本地 + Redis + Mongo）并注入到 Agent。
- 实现读写策略与回读优先级（Redis 热缓存 → Mongo 持久化 → 本地兜底）。
- 增加记忆写入与摘要策略，避免无限增长。

### 阶段 6：Notebook 可视化与回放
- 提供 Jupyter Notebook 示例，完成行情、盘口、成交、PNL 回放。
- 加入多代理对比图表（收益曲线、回撤、成交效率）。
- 增加一次完整实验的可复现脚手架（输入数据 + 参数 + 输出图表）。

## 交付里程碑建议
- M1：数据快照产物可复用 + 回测可复现。
- M2：异步事件分发与 Kafka 解耦链路跑通（含审计）。
- M3：多智能体（含 LLM）可运行 + 记忆分层稳定。
- M4：Notebook 回放与对比完整呈现。
