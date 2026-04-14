"""
FastAPI 后端 — 仿真 WebSocket 实时推送

运行方式（项目根目录下）：
    python -m src.server.main
或（安装后）：
    uvicorn src.server.main:app --reload --port 8000
"""
from __future__ import annotations
import asyncio
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 加载 .env（从 src/server/.env 向上两级找到项目根）
_server_dir = Path(__file__).resolve().parent
_project_root = _server_dir.parent.parent
_env_file = _project_root / ".env"
load_dotenv(_env_file)


# ---------- Pydantic Models ----------
class StartRequest(BaseModel):
    symbols: List[str] = ["AAPL", "TSLA", "SPY"]
    steps: int = 1000
    initial_cash: float = 100000.0


# ---------- FastAPI App ----------
app = FastAPI(title="MultiAgent Exchange Dashboard API")

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
    运行在项目根目录时直接导入 src 模块。
    """
    # 内部导入避免循环依赖
    from src import Exchange, Simulation
    from src.data import DataFeed, DataLoader
    from src.data.NewsGenerator import NewsGenerator
    from src.environment.event_hub import EventHub, EV_TRADE

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
        if len(recent_trades) > 20:
            recent_trades.pop(0)

    hub.on(EV_TRADE, on_trade)

    # 注册 Agent
    from src.agents.SimpleAgents import MarketMakerAgent, MomentumAgent

    mm = MarketMakerAgent(
        agent_id="mm-1",
        exchange=exchange,
        symbols=symbols,
        spread_bps=20.0,
        order_size=5,
        target_position=50,
    )
    sim.register_agent(mm, agentId="mm-1")
    for sym in symbols:
        exchange.position_records["mm-1"][sym] = 50

    mom = MomentumAgent(
        agent_id="mom-1",
        exchange=exchange,
        symbols=symbols,
        lookback_period=5,
        momentum_threshold=0.01,
        order_size=10,
    )
    sim.register_agent(mom, agentId="mom-1")
    for sym in symbols:
        exchange.position_records["mom-1"][sym] = 30

    for i in range(steps):
        while state.paused:
            time.sleep(0.1)

        st = sim.step()

        prices = st.get("prices", {})
        spreads = st.get("spreads", {})
        agent_vals = st.get("agent_values", {})

        news_items = []
        if news_gen.news_history:
            last_news = (
                news_gen.news_history[-len(symbols):]
                if len(news_gen.news_history) >= len(symbols)
                else news_gen.news_history[-1:]
            )
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

        with state._lock:
            state.step = i + 1
            state.prices = prices
            state.spreads = spreads
            state.trades = list(recent_trades[-20:])
            state.agent_values = agent_vals
            state.news = news_items

        asyncio.run(manager.broadcast(tick))
        time.sleep(0.05)

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
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(ws)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.server.main:app", host="0.0.0.0", port=8000, reload=True)
