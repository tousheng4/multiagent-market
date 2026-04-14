# 赛博朋克风格股票交易仪表盘 — 设计方案

## Context

目标：为多智能体股票交易所开发一个实时可视化的 Web 仪表盘网站。
技术栈已确定：FastAPI + WebSocket + React/Vite + Plotly。

---

## Architecture

```
[Python Simulation] ←→ [FastAPI Backend] ←→ [WebSocket] ←→ [React/Vite Frontend]
                         ↕                                            ↕
                    [Market Data]                              [Plotly Charts]
```

FastAPI 运行仿真，通过 WebSocket 实时推送每步数据，前端渲染完整仪表盘。

---

## Frontend — React/Vite 前端

### 页面布局

```
┌─────────────────────────────────────────────────────────────┐
│  HEADER: 交易所实时仿真系统  ● 连接状态        [控制按钮]    │
├─────────────────────────────────────────────────────────────┤
│   [价格 K 线 / 均线 — Plotly 图表区域]     [实时订单簿深度]   │
│   3 个 symbol 的价格曲线，步进实时追加                         │
├─────────────────────────────────────────────────────────────┤
│   [成交记录滚动面板]              [Agent PnL 排行]           │
│   最新 20 条成交                  权益曲线图 + 数值          │
└─────────────────────────────────────────────────────────────┘
```

### 配色方案（赛博朋克）

```
背景：#0a0a0f（深黑）
面板：#12121a（深灰紫）
边框/线条：#00f0ff（青色霓虹）
上涨：#00ff88（霓虹绿）
下跌：#ff2d6a（霓虹红）
文字主色：#e0e0ff（淡紫白）
强调色：#f0f000（黄色霓虹）
```

字体：`Orbitron`（标题）+ `JetBrains Mono`（数据）

### 组件

| 组件 | 说明 |
|------|------|
| `DashboardPage` | 主页面，布局所有模块 |
| `PriceChart` | Plotly K 线/折线图，实时追加数据点 |
| `OrderBookPanel` | 买卖盘深度（水平条形图） |
| `TradeHistoryPanel` | 成交记录滚动列表 |
| `AgentPnLPanel` | Agent 权益排行 + 曲线图 |
| `ConnectionStatus` | WebSocket 连接状态指示器 |
| `ControlButtons` | 启动/暂停/恢复按钮 |

---

## Backend — FastAPI 后端

### 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/start` | POST | 启动仿真（传入 symbols、steps） |
| `/api/pause` | POST | 暂停仿真 |
| `/api/resume` | POST | 恢复仿真 |
| `/ws/sim` | WebSocket | 实时推送每步数据 |

### WebSocket 推送消息格式

```json
{
  "type": "tick",
  "step": 1,
  "prices": {"AAPL": 8.07, "TSLA": 1.13, "SPY": 82.96},
  "spreads": {"AAPL": 0.05, "TSLA": 0.05, "SPY": 0.20},
  "trades": [{"symbol": "AAPL", "side": "buy", "price": 8.07, "quantity": 10}],
  "agent_values": {"mm-1": 104607.5, "mom-1": 102764.5}
}
```

### 文件结构

```
frontend/
├── src/
│   ├── components/
│   │   ├── PriceChart.tsx
│   │   ├── OrderBookPanel.tsx
│   │   ├── TradeHistoryPanel.tsx
│   │   ├── AgentPnLPanel.tsx
│   │   ├── ConnectionStatus.tsx
│   │   └── ControlButtons.tsx
│   ├── App.tsx
│   └── main.tsx
├── index.html
├── package.json
└── vite.config.ts

backend/
├── main.py          # FastAPI 入口，WebSocket 处理
└── simulation_ws.py # 仿真与 WebSocket 胶水层
```

---

## 实现顺序

1. **后端** — FastAPI + WebSocket 接口，`/api/start` 启动仿真线程，`/ws/sim` 推送数据
2. **前端骨架** — React/Vite 项目，`DashboardPage` 主框架，`ConnectionStatus`
3. **价格图表** — `PriceChart`（Plotly 实时追加）
4. **成交记录** — `TradeHistoryPanel`
5. **Agent PnL** — `AgentPnLPanel`
6. **控制按钮** — `ControlButtons`（启动/暂停/恢复）
7. **联调** — 前后端 WebSocket 打通，端到端测试

---

## Verification

```bash
# 后端
cd backend && uvicorn main:app --reload --port 8000

# 前端
cd frontend && npm install && npm run dev
```

打开 `http://localhost:5173`，点击"启动"后观察图表实时更新。
