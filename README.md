# Multiagent Market — 多智能体仿真股票交易所

基于 ReAct 的事件驱动多智能体市场仿真系统，配套赛博朋克风格实时监控仪表盘。

## 功能概览

- **订单撮合引擎**：限价单/市价单、完整订单簿（买卖盘）、撮合成交、持仓结算
- **ReAct 智能体**：每步执行完整 `observe → think → act` 循环，通过 MiniMax + LangChain tool calling 推理下单
- **规则型智能体**：做市商（MarketMaker）、动量交易（Momentum）作为流动性基线
- **风控拦截**：RiskAgent 在订单进入撮合前强制检查，不合规直接拒绝
- **事件总线**：基于 blinker 的 EventHub，所有模块通过事件解耦通信
- **新闻生成器**：根据价格变动自动生成模拟新闻，触发 LLM 宏观推理
- **实时仪表盘**：FastAPI WebSocket 推送，React + Plotly 可视化价格曲线、成交记录、Agent 权益

## 项目结构

```
multiagent-market/
├── src/
│   ├── agents/
│   │   ├── BaseAgent.py          # Agent 基类
│   │   ├── ReActAgent.py         # ReAct 基类（MiniMax + LangChain）
│   │   ├── ReActAgents.py        # NewsAgent / StrategyAgent / RiskAgent / EvaluatorAgent
│   │   ├── SimpleAgents.py       # MarketMakerAgent / MomentumAgent / RandomAgent
│   │   └── tool/
│   │       ├── marketTools.py    # 行情、账户、下单工具
│   │       ├── news_tools.py     # 新闻查询工具
│   │       ├── memory_tools.py   # 记忆读写工具
│   │       └── create_tools.py   # 工具集合工厂
│   ├── data/
│   │   ├── pipeline.py           # 数据加载 / DataFeed
│   │   └── NewsGenerator.py      # 模拟新闻生成器
│   ├── environment/
│   │   ├── event_hub.py          # EventHub 事件总线
│   │   └── simulation.py         # 仿真主循环
│   ├── market/
│   │   ├── models/
│   │   │   ├── exchange.py       # 交易所（撮合、结算、风控）
│   │   │   ├── orderbook.py      # 订单簿
│   │   │   └── order.py          # 订单 / 成交数据模型
│   │   └── client.py             # Agent 用市场客户端
│   ├── strategy/                 # 指标、信号、风控策略函数
│   └── server/
│       └── main.py               # FastAPI 后端 + WebSocket 推送
├── frontend/                     # React + Vite 仪表盘
│   └── src/
│       ├── App.tsx               # 主布局 + WebSocket 状态管理
│       └── components/           # 价格图表、成交记录、Agent 权益面板
├── main.py                       # CLI 入口（纯后端仿真）
├── pyproject.toml
└── .env.example
```

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 填写 MINIMAX_API_KEY（可选，不填则只运行规则型 Agent）
```

### 3. 启动后端

```bash
uv run uvicorn src.server.main:app --reload --port 8000
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 `http://localhost:5173`，点击"启动仿真"即可。

### 5. 纯命令行运行（无前端）

```bash
uv run python main.py
```

## Agent 说明

| Agent | 类型 | 行为 |
|-------|------|------|
| MarketMakerAgent | 规则 | 双向挂单，赚取买卖价差 |
| MomentumAgent | 规则 | 动量信号驱动，跟趋势买卖 |
| NewsAgent | ReAct + LLM | 读取新闻，推理宏观情绪 |
| StrategyAgent | ReAct + LLM | 结合行情 + 记忆，推理下单信号 |
| RiskAgent | 规则拦截 | 强制检查保证金、持仓限额，拒绝违规订单 |
| EvaluatorAgent | ReAct + LLM | 汇总 PnL，输出绩效评估 |

## 技术栈

- **后端**：Python 3.11+、FastAPI、uvicorn、blinker、LangChain、MiniMax
- **前端**：React 18、Vite、TypeScript、Plotly.js
- **数据**：DuckDB、pandas
- **包管理**：uv
