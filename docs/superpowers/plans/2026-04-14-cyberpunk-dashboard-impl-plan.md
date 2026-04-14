# 赛博朋克股票交易仪表盘 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个实时可视化 Web 仪表盘，FastAPI 后端通过 WebSocket 推送仿真数据，React 前端渲染赛博朋克风格的完整交易仪表盘。

**Architecture:** FastAPI 后端运行仿真，通过 WebSocket 实时推送每步数据（价格/订单簿/成交/Agent权益）到浏览器。前端 React/Vite 接收数据，用 Plotly 渲染交互图表。

**Tech Stack:** FastAPI + uvicorn + websockets + React 18 + Vite + Plotly + react-plotly.js

---

## 文件结构

```
backend/
├── main.py              # FastAPI 应用，WebSocket + REST 接口
└── requirements.txt     # fastapi, uvicorn[standard], websockets, python-dotenv

frontend/
├── public/
├── src/
│   ├── components/
│   │   ├── ConnectionStatus.tsx
│   │   ├── ControlButtons.tsx
│   │   ├── PriceChart.tsx
│   │   ├── TradeHistoryPanel.tsx
│   │   └── AgentPnLPanel.tsx
│   ├── App.tsx
│   ├── App.css
│   └── main.tsx
├── index.html
├── package.json
├── tsconfig.json
├── tsconfig.node.json
└── vite.config.ts
```

---

## 阶段 1：后端 — FastAPI + WebSocket

### Task 1: 创建 backend 目录和依赖文件

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/.env.example`

- [ ] **Step 1: 创建 backend/requirements.txt**

```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
websockets>=12.0
python-dotenv>=1.0.0
```

- [ ] **Step 2: 创建 backend/.env.example**

```
MINIMAX_API_KEY=your_key_here
```

- [ ] **Step 3: 安装后端依赖**

Run: `cd backend && pip install -r requirements.txt`

---

### Task 2: 实现 backend/main.py

**Files:**
- Create: `backend/main.py`

- [ ] **Step 1: 创建 backend/main.py**

```python
"""
FastAPI 后端 — 仿真 WebSocket 实时推送
"""
from __future__ import annotations
import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 加载 .env
_dotenv = Path(__file__).parent / ".env"
load_dotenv(_dotenv)

# ---------- Pydantic Models ----------
class StartRequest(BaseModel):
    symbols: List[str] = ["AAPL", "TSLA", "SPY"]
    steps: int = 100
    initial_cash: float = 100000.0


class TickMessage(BaseModel):
    type: str = "tick"
    step: int
    prices: Dict[str, float]
    spreads: Dict[str, float]
    trades: List[Dict[str, Any]]
    agent_values: Dict[str, float]
    news: List[Dict[str, Any]]


# ---------- FastAPI App ----------
app = FastAPI(title="MultiAgent Exchange Dashboard API")

# CORS 允许前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- 全局状态 ----------
class SimState:
    def __init__(self):
        self.active = False
        self.paused = False
        self.step = 0
        self.prices: Dict[str, float] = {}
        self.spreads: Dict[str, float] = {}
        self.trades: List[Dict[str, Any]] = []
        self.agent_values: Dict[str, float] = {}
        self.news: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def reset(self):
        with self._lock:
            self.active = False
            self.paused = False
            self.step = 0
            self.prices = {}
            self.spreads = {}
            self.trades = []
            self.agent_values = {}
            self.news = []


state = SimState()


# ---------- WebSocket 管理 ----------
class ConnectionManager:
    def __init__(self):
        self.connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, msg: dict):
        for conn in self.connections[:]:
            try:
                await conn.send_json(msg)
            except Exception:
                self.connections.remove(conn)


manager = ConnectionManager()


# ---------- 仿真线程 ----------
def run_simulation(symbols: List[str], steps: int, initial_cash: float):
    """
    在独立线程中运行仿真，完成后通知主线程。
    真实撮合通过直接 import 现有 Exchange/Simulation 实现。
    """
    import sys
    from pathlib import Path

    # 确保 src 在 path 中
    src_path = Path(__file__).parent.parent / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    from src import Exchange, Simulation
    from src.data import DataFeed, DataLoader
    from src.data.NewsGenerator import NewsGenerator
    from src.environment.event_hub import EventHub, EV_NEWS, EV_TRADE

    hub = EventHub()
    exchange = Exchange(initial_cash=initial_cash, hub=hub)
    news_gen = NewsGenerator(hub=hub, symbols=symbols)

    sim = Simulation(
        exchange=exchange,
        symbols=symbols,
        initial_cash=initial_cash,
        hub=hub,
        async_mode=False,
        news_generator=news_gen,
    )

    loader = DataLoader()
    sim.data_feed = DataFeed(exchange, symbols, loader)

    # 订阅成交事件
    recent_trades: List[Dict] = []
    def on_trade(msg):
        payload = msg.get("payload") or {}
        recent_trades.append({
            "symbol": payload.get("symbol", ""),
            "side": payload.get("side", ""),
            "price": payload.get("price", 0),
            "quantity": payload.get("quantity", 0),
            "step": state.step,
        })
        # 只保留最近 20 条
        if len(recent_trades) > 20:
            recent_trades.pop(0)

    hub.on(EV_TRADE, on_trade)

    # 注册 Agent
    from src.agents.SimpleAgents import MarketMakerAgent, MomentumAgent
    mm = MarketMakerAgent(
        agent_id="mm-1", exchange=exchange, symbols=symbols,
        spread_bps=20.0, order_size=5, target_position=50,
    )
    sim.register_agent(mm, agentId="mm-1")
    for sym in symbols:
        exchange.position_records["mm-1"][sym] = 50

    mom = MomentumAgent(
        agent_id="mom-1", exchange=exchange, symbols=symbols,
        lookback_period=5, momentum_threshold=0.01, order_size=10,
    )
    sim.register_agent(mom, agentId="mom-1")
    for sym in symbols:
        exchange.position_records["mom-1"][sym] = 30

    for i in range(steps):
        while state.paused:
            time.sleep(0.1)

        st = sim.step()

        # 收集当前价格
        prices = st.get("prices", {})
        spreads = st.get("spreads", {})
        agent_vals = st.get("agent_values", {})

        # 收集新闻（从 news_gen）
        news_items = []
        if news_gen.news_history:
            last_news = news_gen.news_history[-len(symbols):] if len(news_gen.news_history) >= len(symbols) else news_gen.news_history[-1:]
            for n in last_news:
                news_items.append({
                    "symbol": n.get("symbol", ""),
                    "news": n.get("news", ""),
                    "step": n.get("step", 0),
                    "change_pct": n.get("change_pct", 0.0),
                })

        tick = {
            "type": "tick",
            "step": i + 1,
            "prices": prices,
            "spreads": spreads,
            "trades": list(recent_trades[-20:]),
            "agent_values": agent_vals,
            "news": news_items,
        }

        # 更新全局状态
        with state._lock:
            state.step = i + 1
            state.prices = prices
            state.spreads = spreads
            state.trades = list(recent_trades[-20:])
            state.agent_values = agent_vals
            state.news = news_items

        # 广播
        asyncio.run(manager.broadcast(tick))
        time.sleep(0.05)  # 避免过快

    state.active = False
    asyncio.run(manager.broadcast({"type": "done", "step": state.step}))


# ---------- REST API ----------
@app.post("/api/start")
async def start_simulation(req: StartRequest):
    if state.active:
        raise HTTPException(status_code=400, detail="Simulation already running")

    state.reset()
    state.active = True
    state.paused = False

    thread = threading.Thread(
        target=run_simulation,
        args=(req.symbols, req.steps, req.initial_cash),
        daemon=True,
    )
    thread.start()
    return {"status": "started", "steps": req.steps}


@app.post("/api/pause")
async def pause_simulation():
    if not state.active:
        raise HTTPException(status_code=400, detail="No active simulation")
    state.paused = True
    return {"status": "paused"}


@app.post("/api/resume")
async def resume_simulation():
    if not state.active:
        raise HTTPException(status_code=400, detail="No active simulation")
    state.paused = False
    return {"status": "resumed"}


@app.get("/api/status")
async def get_status():
    with state._lock:
        return {
            "active": state.active,
            "paused": state.paused,
            "step": state.step,
            "prices": state.prices,
            "spreads": state.spreads,
            "trades": state.trades[-20:],
            "agent_values": state.agent_values,
            "news": state.news,
        }


# ---------- WebSocket ----------
@app.websocket("/ws/sim")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        # 发送当前状态快照
        with state._lock:
            if state.active:
                await ws.send_json({
                    "type": "tick",
                    "step": state.step,
                    "prices": state.prices,
                    "spreads": state.spreads,
                    "trades": state.trades[-20:],
                    "agent_values": state.agent_values,
                    "news": state.news,
                })
        while True:
            data = await ws.receive_text()
            # 简单的 ping/pong
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(ws)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
```

- [ ] **Step 2: 验证后端启动**

Run: `cd backend && pip install -r requirements.txt && python -c "from main import app; print('OK')"`

---

## 阶段 2：前端 — React/Vite 项目骨架

### Task 3: 创建前端项目

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/App.css`
- Create: `frontend/.env.example`

- [ ] **Step 1: 创建 frontend/package.json**

```json
{
  "name": "multiagent-exchange-dashboard",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-plotly.js": "^2.6.0",
    "plotly.js": "^2.35.3"
  },
  "devDependencies": {
    "@types/react": "^18.3.1",
    "@types/react-dom": "^18.3.1",
    "@types/react-plotly.js": "^2.6.3",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.3",
    "vite": "^5.4.2"
  }
}
```

- [ ] **Step 2: 创建 frontend/vite.config.ts**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
```

- [ ] **Step 3: 创建 frontend/tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 4: 创建 frontend/tsconfig.node.json**

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 5: 创建 frontend/index.html**

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>多智能体股票交易所</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: 创建 frontend/src/main.tsx**

```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './App.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

- [ ] **Step 7: 创建 frontend/src/App.css（赛博朋克全局样式）**

```css
/* 赛博朋克全局变量 */
:root {
  --bg-primary: #0a0a0f;
  --bg-panel: #12121a;
  --bg-panel-hover: #1a1a2a;
  --border-neon: #00f0ff;
  --color-up: #00ff88;
  --color-down: #ff2d6a;
  --color-warn: #f0f000;
  --color-text: #e0e0ff;
  --color-text-dim: #7070a0;
  --font-display: 'Orbitron', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
  --glow-cyan: 0 0 8px #00f0ff80, 0 0 20px #00f0ff40;
  --glow-green: 0 0 8px #00ff8880, 0 0 20px #00ff8840;
  --glow-red: 0 0 8px #ff2d6a80, 0 0 20px #ff2d6a40;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  background-color: var(--bg-primary);
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: 13px;
  overflow-x: hidden;
  background-image:
    radial-gradient(ellipse at 20% 0%, #00f0ff08 0%, transparent 50%),
    radial-gradient(ellipse at 80% 100%, #ff2d6a08 0%, transparent 50%);
}

::-webkit-scrollbar {
  width: 6px;
  background: var(--bg-panel);
}
::-webkit-scrollbar-thumb {
  background: var(--border-neon);
  border-radius: 3px;
}
```

- [ ] **Step 8: 创建 frontend/src/App.tsx**

```tsx
import { useState, useEffect, useCallback, useRef } from 'react'
import ConnectionStatus from './components/ConnectionStatus'
import ControlButtons from './components/ControlButtons'
import PriceChart from './components/PriceChart'
import TradeHistoryPanel from './components/TradeHistoryPanel'
import AgentPnLPanel from './components/AgentPnLPanel'
import './App.css'

export interface TickData {
  type: string
  step: number
  prices: Record<string, number>
  spreads: Record<string, number>
  trades: Array<{
    symbol: string
    side: string
    price: number
    quantity: number
    step: number
  }>
  agent_values: Record<string, number>
  news: Array<{
    symbol: string
    news: string
    step: number
    change_pct: number
  }>
}

const WS_URL = `ws://${window.location.hostname}:8000/ws/sim`
const API_BASE = `http://${window.location.hostname}:8000`

function App() {
  const [wsConnected, setWsConnected] = useState(false)
  const [simActive, setSimActive] = useState(false)
  const [simPaused, setSimPaused] = useState(false)
  const [tick, setTick] = useState<TickData | null>(null)
  const [priceHistory, setPriceHistory] = useState<Record<string, Array<{x: number, y: number}>>>({})
  const [trades, setTrades] = useState<TickData['trades']>([])
  const [agentValues, setAgentValues] = useState<Record<string, number>>({})
  const [news, setNews] = useState<TickData['news']>([])
  const wsRef = useRef<WebSocket | null>(null)

  const connectWS = useCallback(() => {
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => setWsConnected(true)
    ws.onclose = () => setWsConnected(false)
    ws.onerror = () => setWsConnected(false)

    ws.onmessage = (event) => {
      if (event.data === 'pong') return
      const data: TickData = JSON.parse(event.data)
      if (data.type === 'done') {
        setSimActive(false)
        return
      }
      setTick(data)

      // 追加价格历史
      setPriceHistory(prev => {
        const next = { ...prev }
        for (const [sym, price] of Object.entries(data.prices)) {
          if (!next[sym]) next[sym] = []
          next[sym] = [...next[sym], { x: data.step, y: price }]
        }
        return next
      })

      setTrades(data.trades)
      setAgentValues(data.agent_values)
      setNews(data.news)
      setSimActive(data.type === 'tick')
    }
  }, [])

  useEffect(() => {
    connectWS()
    return () => wsRef.current?.close()
  }, [connectWS])

  const handleStart = async () => {
    await fetch(`${API_BASE}/api/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbols: ['AAPL', 'TSLA', 'SPY'], steps: 200, initial_cash: 100000 }),
    })
    setSimActive(true)
    setSimPaused(false)
  }

  const handlePause = async () => {
    await fetch(`${API_BASE}/api/pause`, { method: 'POST' })
    setSimPaused(true)
  }

  const handleResume = async () => {
    await fetch(`${API_BASE}/api/resume`, { method: 'POST' })
    setSimPaused(false)
  }

  return (
    <div className="app">
      {/* Header */}
      <header className="dashboard-header">
        <div className="header-left">
          <h1 className="logo">NEXUS EXCHANGE</h1>
          <span className="header-sub">多智能体仿真系统</span>
        </div>
        <div className="header-right">
          <ConnectionStatus connected={wsConnected} step={tick?.step ?? 0} />
          <ControlButtons
            active={simActive}
            paused={simPaused}
            onStart={handleStart}
            onPause={handlePause}
            onResume={handleResume}
          />
        </div>
      </header>

      {/* News Ticker */}
      {news.length > 0 && (
        <div className="news-ticker">
          {news.map((n, i) => (
            <span key={i} className={`news-item ${n.change_pct >= 0 ? 'up' : 'down'}`}>
              [{n.symbol}] {n.news}
            </span>
          ))}
        </div>
      )}

      {/* Main Grid */}
      <main className="dashboard-grid">
        {/* 价格图表 - 跨两列 */}
        <div className="panel price-panel">
          <div className="panel-header">
            <span className="panel-title">价格走势</span>
            <span className="panel-badge">实时</span>
          </div>
          <PriceChart data={priceHistory} />
        </div>

        {/* 成交记录 */}
        <div className="panel trades-panel">
          <div className="panel-header">
            <span className="panel-title">成交记录</span>
            <span className="panel-badge">{trades.length}</span>
          </div>
          <TradeHistoryPanel trades={trades} />
        </div>

        {/* Agent PnL */}
        <div className="panel pnl-panel">
          <div className="panel-header">
            <span className="panel-title">Agent 权益</span>
          </div>
          <AgentPnLPanel values={agentValues} />
        </div>
      </main>
    </div>
  )
}

export default App
```

- [ ] **Step 9: 创建 frontend/.env.example**

```
VITE_WS_URL=ws://localhost:8000/ws/sim
VITE_API_BASE=http://localhost:8000
```

- [ ] **Step 10: 安装依赖并验证构建**

Run: `cd frontend && npm install && npm run build`（预期无报错）

---

### Task 4: 实现 ConnectionStatus 组件

**Files:**
- Create: `frontend/src/components/ConnectionStatus.tsx`

- [ ] **Step 1: 创建 frontend/src/components/ConnectionStatus.tsx**

```tsx
import './ConnectionStatus.css'

interface Props {
  connected: boolean
  step: number
}

export default function ConnectionStatus({ connected, step }: Props) {
  return (
    <div className={`connection-status ${connected ? 'connected' : 'disconnected'}`}>
      <span className="status-dot" />
      <span className="status-text">
        {connected ? 'LIVE' : '离线'}
      </span>
      {step > 0 && <span className="status-step">Step {step}</span>}
    </div>
  )
}
```

- [ ] **Step 2: 创建 frontend/src/components/ConnectionStatus.css**

```css
.connection-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 4px;
  border: 1px solid;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.connection-status.connected {
  border-color: var(--color-up);
  color: var(--color-up);
  box-shadow: var(--glow-green);
}

.connection-status.disconnected {
  border-color: var(--color-down);
  color: var(--color-down);
  box-shadow: var(--glow-red);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.status-step {
  color: var(--color-text-dim);
  font-weight: 400;
  margin-left: 4px;
}
```

---

### Task 5: 实现 ControlButtons 组件

**Files:**
- Create: `frontend/src/components/ControlButtons.tsx`
- Create: `frontend/src/components/ControlButtons.css`

- [ ] **Step 1: 创建 frontend/src/components/ControlButtons.tsx**

```tsx
import './ControlButtons.css'

interface Props {
  active: boolean
  paused: boolean
  onStart: () => void
  onPause: () => void
  onResume: () => void
}

export default function ControlButtons({ active, paused, onStart, onPause, onResume }: Props) {
  return (
    <div className="control-buttons">
      {!active && (
        <button className="btn btn-start" onClick={onStart}>
          <span className="btn-icon">&#9654;</span> 启动仿真
        </button>
      )}
      {active && !paused && (
        <button className="btn btn-pause" onClick={onPause}>
          <span className="btn-icon">&#10074;&#10074;</span> 暂停
        </button>
      )}
      {active && paused && (
        <button className="btn btn-resume" onClick={onResume}>
          <span className="btn-icon">&#9654;</span> 继续
        </button>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 创建 frontend/src/components/ControlButtons.css**

```css
.control-buttons {
  display: flex;
  gap: 8px;
}

.btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 16px;
  border: 1px solid var(--border-neon);
  border-radius: 4px;
  background: transparent;
  color: var(--border-neon);
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  cursor: pointer;
  transition: all 0.15s ease;
  text-transform: uppercase;
}

.btn:hover {
  background: var(--border-neon);
  color: var(--bg-primary);
  box-shadow: var(--glow-cyan);
}

.btn-start {
  border-color: var(--color-up);
  color: var(--color-up);
}
.btn-start:hover {
  background: var(--color-up);
  box-shadow: var(--glow-green);
}

.btn-pause {
  border-color: var(--color-warn);
  color: var(--color-warn);
}
.btn-pause:hover {
  background: var(--color-warn);
  color: var(--bg-primary);
}

.btn-resume {
  border-color: var(--color-up);
  color: var(--color-up);
}
.btn-resume:hover {
  background: var(--color-up);
  color: var(--bg-primary);
  box-shadow: var(--glow-green);
}
```

---

### Task 6: 实现 PriceChart 组件

**Files:**
- Create: `frontend/src/components/PriceChart.tsx`
- Create: `frontend/src/components/PriceChart.css`

- [ ] **Step 1: 创建 frontend/src/components/PriceChart.tsx**

```tsx
import Plotly from 'react-plotly.js'
import './PriceChart.css'

interface DataPoint {
  x: number
  y: number
}

interface Props {
  data: Record<string, DataPoint[]>
}

const SYMBOL_COLORS: Record<string, string> = {
  AAPL: '#00f0ff',
  TSLA: '#f0f000',
  SPY: '#00ff88',
}

const LAYOUT: Plotly.Layout = {
  paper_bgcolor: 'transparent',
  plot_bgcolor: 'transparent',
  font: { color: '#e0e0ff', family: 'JetBrains Mono, monospace', size: 11 },
  margin: { t: 10, r: 10, b: 40, l: 60 },
  xaxis: {
    title: { text: 'Step', font: { color: '#7070a0' } },
    gridcolor: '#1a1a2a',
    linecolor: '#00f0ff',
    tickcolor: '#00f0ff',
    zerolinecolor: '#2a2a4a',
  },
  yaxis: {
    title: { text: 'Price ($)', font: { color: '#7070a0' } },
    gridcolor: '#1a1a2a',
    linecolor: '#00f0ff',
    tickcolor: '#00f0ff',
    zerolinecolor: '#2a2a4a',
  },
  legend: {
    orientation: 'h',
    x: 0.5,
    xanchor: 'center',
    y: -0.15,
    bgcolor: 'rgba(0,0,0,0)',
    font: { color: '#e0e0ff' },
  },
  hovermode: 'x unified' as const,
  showlegend: true,
}

const CONFIG: Plotly.Config = {
  responsive: true,
  displayModeBar: true,
  modeBarButtonsToRemove: ['lasso2d', 'select2d'],
  displaylogo: false,
}

export default function PriceChart({ data }: Props) {
  const symbols = Object.keys(data)

  if (symbols.length === 0 || Object.values(data).every(arr => arr.length === 0)) {
    return (
      <div className="chart-empty">
        <span>等待数据...</span>
      </div>
    )
  }

  const traces: Plotly.Data[] = symbols.map(sym => ({
    x: data[sym].map(p => p.x),
    y: data[sym].map(p => p.y),
    type: 'scatter',
    mode: 'lines' as const,
    name: sym,
    line: { color: SYMBOL_COLORS[sym] || '#ffffff', width: 2 },
    hovertemplate: `<b>${sym}</b><br>Step %{x}<br>$%{y:.4f}<extra></extra>`,
  }))

  return (
    <div className="price-chart">
      <Plotly data={traces} layout={LAYOUT} config={CONFIG} useResizeHandler style={{ width: '100%', height: '100%' }} />
    </div>
  )
}
```

- [ ] **Step 2: 创建 frontend/src/components/PriceChart.css**

```css
.price-chart {
  width: 100%;
  height: 320px;
  padding: 8px;
}

.chart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 320px;
  color: var(--color-text-dim);
  font-size: 14px;
  letter-spacing: 0.1em;
}
```

---

### Task 7: 实现 TradeHistoryPanel 组件

**Files:**
- Create: `frontend/src/components/TradeHistoryPanel.tsx`
- Create: `frontend/src/components/TradeHistoryPanel.css`

- [ ] **Step 1: 创建 frontend/src/components/TradeHistoryPanel.tsx**

```tsx
import './TradeHistoryPanel.css'

interface Trade {
  symbol: string
  side: string
  price: number
  quantity: number
  step: number
}

interface Props {
  trades: Trade[]
}

export default function TradeHistoryPanel({ trades }: Props) {
  if (trades.length === 0) {
    return <div className="trades-empty">暂无成交</div>
  }

  return (
    <div className="trade-list">
      {trades.slice().reverse().map((t, i) => (
        <div key={i} className={`trade-row ${t.side === 'buy' ? 'up' : 'down'}`}>
          <span className="trade-step">#{t.step}</span>
          <span className="trade-symbol">{t.symbol}</span>
          <span className="trade-side">{t.side === 'buy' ? '买' : '卖'}</span>
          <span className="trade-qty">{t.quantity}</span>
          <span className="trade-price">@${t.price.toFixed(2)}</span>
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 2: 创建 frontend/src/components/TradeHistoryPanel.css**

```css
.trade-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 260px;
  overflow-y: auto;
  padding: 4px;
}

.trade-row {
  display: grid;
  grid-template-columns: 50px 50px 30px 40px 70px;
  gap: 6px;
  padding: 5px 8px;
  border-radius: 3px;
  font-size: 11px;
  border-left: 2px solid transparent;
  background: #0d0d15;
  transition: background 0.1s;
}

.trade-row:hover {
  background: var(--bg-panel-hover);
}

.trade-row.up {
  border-left-color: var(--color-up);
  color: var(--color-up);
}

.trade-row.down {
  border-left-color: var(--color-down);
  color: var(--color-down);
}

.trade-step {
  color: var(--color-text-dim);
  font-size: 10px;
}

.trade-symbol {
  font-weight: 700;
  color: var(--color-text);
}

.trade-side {
  font-weight: 700;
  text-transform: uppercase;
}

.trade-qty {
  text-align: right;
  color: var(--color-text);
}

.trade-price {
  text-align: right;
  font-weight: 700;
}

.trades-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100px;
  color: var(--color-text-dim);
  font-size: 12px;
}
```

---

### Task 8: 实现 AgentPnLPanel 组件

**Files:**
- Create: `frontend/src/components/AgentPnLPanel.tsx`
- Create: `frontend/src/components/AgentPnLPanel.css`

- [ ] **Step 1: 创建 frontend/src/components/AgentPnLPanel.tsx**

```tsx
import './AgentPnLPanel.css'

interface Props {
  values: Record<string, number>
}

const INITIAL_CASH = 100000

export default function AgentPnLPanel({ values }: Props) {
  const entries = Object.entries(values)

  if (entries.length === 0) {
    return <div className="pnl-empty">等待数据...</div>
  }

  return (
    <div className="pnl-content">
      {entries.map(([agentId, value]) => {
        const pnl = value - INITIAL_CASH
        const pnlPct = (pnl / INITIAL_CASH) * 100
        const isPositive = pnl >= 0
        return (
          <div key={agentId} className="pnl-row">
            <div className="pnl-agent-info">
              <span className="pnl-agent-id">{agentId}</span>
              <span className={`pnl-value ${isPositive ? 'up' : 'down'}`}>
                ${value.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </span>
            </div>
            <div className="pnl-bar-container">
              <div
                className={`pnl-bar ${isPositive ? 'up' : 'down'}`}
                style={{ width: `${Math.min(Math.abs(pnlPct) * 10, 100)}%` }}
              />
            </div>
            <span className={`pnl-pct ${isPositive ? 'up' : 'down'}`}>
              {isPositive ? '+' : ''}{pnlPct.toFixed(2)}%
            </span>
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 2: 创建 frontend/src/components/AgentPnLPanel.css**

```css
.pnl-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 8px;
}

.pnl-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.pnl-agent-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.pnl-agent-id {
  font-size: 11px;
  color: var(--color-text-dim);
  font-weight: 700;
  letter-spacing: 0.05em;
}

.pnl-value {
  font-size: 13px;
  font-weight: 700;
}

.pnl-value.up { color: var(--color-up); }
.pnl-value.down { color: var(--color-down); }

.pnl-bar-container {
  height: 4px;
  background: #1a1a2a;
  border-radius: 2px;
  overflow: hidden;
}

.pnl-bar {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s ease;
}

.pnl-bar.up {
  background: var(--color-up);
  box-shadow: var(--glow-green);
}

.pnl-bar.down {
  background: var(--color-down);
  box-shadow: var(--glow-red);
}

.pnl-pct {
  font-size: 11px;
  font-weight: 700;
  text-align: right;
}

.pnl-pct.up { color: var(--color-up); }
.pnl-pct.down { color: var(--color-down); }

.pnl-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100px;
  color: var(--color-text-dim);
  font-size: 12px;
}
```

---

### Task 9: 实现 Dashboard 整体布局样式

**Files:**
- Modify: `frontend/src/App.css`（追加布局样式）

- [ ] **Step 1: 追加布局样式到 frontend/src/App.css**

追加以下内容到 `App.css` 末尾：

```css
/* ---------- Header ---------- */
.dashboard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 24px;
  border-bottom: 1px solid #1a1a3a;
  background: linear-gradient(180deg, #0f0f1a 0%, #0a0a0f 100%);
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-left {
  display: flex;
  align-items: baseline;
  gap: 16px;
}

.logo {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 900;
  color: var(--border-neon);
  letter-spacing: 0.15em;
  text-shadow: var(--glow-cyan);
}

.header-sub {
  font-size: 11px;
  color: var(--color-text-dim);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

/* ---------- News Ticker ---------- */
.news-ticker {
  display: flex;
  gap: 32px;
  padding: 8px 24px;
  background: #0d0d18;
  border-bottom: 1px solid #1a1a3a;
  overflow-x: auto;
  white-space: nowrap;
}

.news-item {
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.05em;
  flex-shrink: 0;
}

.news-item.up { color: var(--color-up); }
.news-item.down { color: var(--color-down); }

/* ---------- Dashboard Grid ---------- */
.dashboard-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  grid-template-rows: auto auto;
  gap: 16px;
  padding: 16px 24px;
}

.price-panel {
  grid-column: 1 / 2;
  grid-row: 1;
}

.trades-panel {
  grid-column: 2 / 3;
  grid-row: 1 / 3;
}

.pnl-panel {
  grid-column: 1 / 2;
  grid-row: 2;
}

/* ---------- Panel ---------- */
.panel {
  background: var(--bg-panel);
  border: 1px solid #1a1a3a;
  border-radius: 6px;
  overflow: hidden;
  position: relative;
}

.panel::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--border-neon), transparent);
  opacity: 0.6;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid #1a1a3a;
  background: #0d0d18;
}

.panel-title {
  font-family: var(--font-display);
  font-size: 11px;
  font-weight: 700;
  color: var(--border-neon);
  letter-spacing: 0.15em;
  text-transform: uppercase;
}

.panel-badge {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid var(--border-neon);
  color: var(--border-neon);
  font-weight: 700;
}

@media (max-width: 900px) {
  .dashboard-grid {
    grid-template-columns: 1fr;
    grid-template-rows: auto;
  }
  .price-panel, .trades-panel, .pnl-panel {
    grid-column: 1;
    grid-row: auto;
  }
}
```

---

## 阶段 3：端到端联调

### Task 10: 启动并验证

- [ ] **Step 1: 启动后端**

Run: `cd backend && pip install -r requirements.txt && uvicorn main:app --reload --port 8000`
Expected: `Uvicorn running on http://0.0.0.0:8000`

- [ ] **Step 2: 启动前端**

Run: `cd frontend && npm install && npm run dev`
Expected: `Local: http://localhost:5173/`

- [ ] **Step 3: 浏览器验证**

1. 打开 `http://localhost:5173`
2. 页面加载，Header 显示 "NEXUS EXCHANGE"
3. 点击"启动仿真"按钮
4. 观察：价格图表实时追加曲线，新闻滚动，Agent PnL 更新
5. 全部无报错即为通过

---

## 注意事项

1. **Windows 兼容性**：所有路径使用正斜杠，后端 `threading` 在 Windows 上正常工作。
2. **CORS**：已配置允许所有 origin，前端开发服务器代理 `/api` 和 `/ws` 到 `localhost:8000`。
3. **仿真线程**：后端仿真运行在独立 daemon 线程，不阻塞 FastAPI 主线程。
4. **Plotly 图例**：已设置 `useResizeHandler` 保证响应式重绘。
5. **中文显示**：已引入 JetBrains Mono 和 Orbitron，数字和英文数据使用等宽字体。
