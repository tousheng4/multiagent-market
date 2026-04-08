from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from ..data.pipeline import DataFeed
from ..market import Exchange
from ..market.client import AgentClient
from .dispatchers import QueueDispatcher
from .event_hub import EV_DATA, EV_SNAPSHOT, EventHub


class Simulation:
    def __init__(
        self,
        exchange: Exchange,
        symbols: List[str],
        initial_cash: float = 100000.0,
        hub: Optional[EventHub] = None,
        async_mode: bool = False,
        queue_size: int = 4096,
    ):
        self.exchange = exchange
        self.symbols = symbols
        self.initial_cash = initial_cash

        self._own_hub = hub is None
        self.hub = hub or EventHub()
        self.exchange.set_hub(self.hub)
        self.exchange.start_order_consumer()

        self._own_dispatch = async_mode
        self.dispatch = (
            QueueDispatcher(self.hub, maxsize=queue_size) if async_mode else None
        )

        self.agents: List[Any] = []
        self.agent_id_map: Dict[str, Any] = {}

        self.current_step = 0
        self.is_running = False

        self.price_history: Dict[str, List[float]] = defaultdict(list)
        self.volume_history: Dict[str, List[int]] = defaultdict(list)
        self.spread_history: Dict[str, List[float]] = defaultdict(list)
        self.agent_pnl: Dict[str, List[float]] = defaultdict(list)

        for symbol in symbols:
            self.exchange.add_symbol(symbol)

        self.data_feed: Optional[DataFeed] = None
        self._recv: Dict[str, Dict[str, Optional[str]]] = {}
        self._recv_src: Dict[str, str] = {}
        self._last_trade_ts: Optional[float] = None

    def on(self, ev: str, fn, *, name: Optional[str] = None) -> str:
        if self.dispatch:
            sid = self.dispatch.on(ev, fn, name=name)
            self._recv_src[sid] = "dispatch"
            return sid
        sid = self.hub.on(ev, fn, name=name)
        self._recv_src[sid] = "hub"
        return sid

    def off(self, ev: str, sid: str) -> None:
        src = self._recv_src.pop(sid, "hub")
        if src == "dispatch" and self.dispatch:
            self.dispatch.off(sid)
            return
        self.hub.off(ev, sid)

    def register_agent(self, agent: Any, agentId: Optional[str] = None) -> str:
        if agentId is None:
            agentId = f"agent_{len(self.agents)}"

        if agentId in self.agent_id_map:
            raise ValueError(f"Agent {agentId} already registered")

        self.exchange.register_agent(agentId, self.initial_cash)
        self.agents.append(agent)
        self.agent_id_map[agentId] = agent

        if hasattr(agent, "agentId"):
            agent.agentId = agentId
        if hasattr(agent, "exchange"):
            agent.exchange = self.exchange

        agent.market = AgentClient(self.exchange, agentId)

        sid_data = None
        sid_snap = None

        if hasattr(agent, "on_event"):

            def on_data(msg, ag=agent):
                ag.on_event({"type": EV_DATA, "payload": msg.get("payload"), "msg": msg})

            sid_data = self.on(EV_DATA, on_data, name=f"{agentId}_data")

        if hasattr(agent, "on_snapshot"):
            sid_snap = self.on(
                EV_SNAPSHOT,
                lambda msg, ag=agent: ag.on_snapshot(msg.get("payload")),
                name=f"{agentId}_snapshot",
            )

        self._recv[agentId] = {"data": sid_data, "snapshot": sid_snap}
        return agentId

    def unregister_agent(self, agentId: str) -> None:
        if agentId not in self.agent_id_map:
            return

        agent = self.agent_id_map.pop(agentId)
        if agent in self.agents:
            self.agents.remove(agent)

        rec = self._recv.pop(agentId, None)
        if rec:
            if rec.get("data"):
                self.off(EV_DATA, rec["data"])
            if rec.get("snapshot"):
                self.off(EV_SNAPSHOT, rec["snapshot"])

    def step(self) -> Dict[str, Any]:
        t0 = time.time()
        row = None
        advanced = False

        if self.data_feed:
            try:
                row = self.data_feed.step()
            except Exception as exc:
                print(f"DataFeed error: {exc}")
            else:
                if row is not None:
                    advanced = True
                    key = str(row.get("date") or self.exchange.current_time)
                    self.hub.emit(EV_DATA, row, key=key, src="simulation")

        for agent in self.agents:
            if hasattr(agent, "step"):
                try:
                    agent.step()
                except Exception as exc:
                    print(
                        f"Error in agent {getattr(agent, 'agentId', 'unknown')}: {exc}"
                    )

        if not advanced:
            self.exchange.step()

        now = self.exchange.current_time
        self._last_trade_ts = now if advanced else max(0, now - 1)

        stats = self._collect_step_data()
        self.current_step += 1

        stats["step"] = self.current_step
        stats["elapsed_time"] = time.time() - t0

        key = str((row or {}).get("date") or self.exchange.current_time)
        self.hub.emit(EV_SNAPSHOT, stats, key=key, src="simulation")
        return stats

    def _collect_step_data(self) -> Dict[str, Any]:
        stats = {
            "prices": {},
            "spreads": {},
            "volumes": {},
            "agent_values": {},
        }

        for symbol in self.symbols:
            md = self.exchange.get_market_data(symbol)
            last = md["last_price"]
            spread = md["spread"]

            if last is not None:
                self.price_history[symbol].append(last)
                stats["prices"][symbol] = last

            if spread is not None:
                self.spread_history[symbol].append(spread)
                stats["spreads"][symbol] = spread

            trades = self.exchange.get_trade_history(symbol=symbol)
            if trades:
                ts = self._last_trade_ts
                step_trades = [t for t in trades if ts is None or t.timestamp == ts]
                vol = sum(t.quantity for t in step_trades)
                self.volume_history[symbol].append(vol)
                stats["volumes"][symbol] = vol

        for aid in self.agent_id_map.keys():
            acc = self.exchange.get_account(aid)
            pv = acc["portfolio_value"]
            self.agent_pnl[aid].append(pv)
            stats["agent_values"][aid] = pv

        return stats

    def run(self, steps: int, verbose: bool = True) -> List[Dict[str, Any]]:
        self.is_running = True
        out = []
        t0 = time.time()

        for i in range(steps):
            st = self.step()
            out.append(st)

            if verbose and (i + 1) % 100 == 0:
                elapsed = time.time() - t0
                print(
                    f"Step {i + 1}/{steps} | "
                    f"Time: {elapsed:.2f}s | "
                    f"Speed: {(i + 1) / max(elapsed, 1e-9):.2f} steps/s"
                )

        self.is_running = False

        if verbose:
            total = time.time() - t0
            print(
                f"\nSimulation completed: {steps} steps in {total:.2f}s "
                f"({steps / max(total, 1e-9):.2f} steps/s)"
            )

        return out

    def getAgentPerformance(self, agentId: str) -> Dict[str, Any]:
        if agentId not in self.agent_id_map:
            raise ValueError(f"Agent {agentId} not found")

        account = self.exchange.get_account(agentId)
        pnl = self.agent_pnl[agentId]

        if not pnl:
            return {
                "current_value": self.initial_cash,
                "total_return": 0.0,
                "max_drawdown": 0.0,
                "num_trades": 0,
            }

        cur = pnl[-1]
        ret = (cur - self.initial_cash) / self.initial_cash

        mdd = 0.0
        peak = self.initial_cash
        for v in pnl:
            if v > peak:
                peak = v
            dd = (peak - v) / peak
            if dd > mdd:
                mdd = dd

        trades = self.exchange.get_trade_history(agentId=agentId)

        return {
            "agent_id": agentId,
            "initial_value": self.initial_cash,
            "current_value": cur,
            "total_return": ret,
            "total_return_pct": ret * 100,
            "max_drawdown": mdd,
            "max_drawdown_pct": mdd * 100,
            "num_trades": len(trades),
            "cash": account["cash"],
            "positions": account["positions"],
        }

    def getAllPerformance(self) -> Dict[str, Dict[str, Any]]:
        return {aid: self.getAgentPerformance(aid) for aid in self.agent_id_map.keys()}

    def reset(self) -> None:
        self.exchange = Exchange(initial_cash=self.initial_cash, hub=self.hub)
        self.exchange.start_order_consumer()

        for symbol in self.symbols:
            self.exchange.add_symbol(symbol)

        old = self.agent_id_map.copy()
        self.agent_id_map.clear()

        for aid, agent in old.items():
            self.exchange.register_agent(aid, self.initial_cash)
            self.agent_id_map[aid] = agent
            if hasattr(agent, "agentId"):
                agent.agentId = aid
            if hasattr(agent, "exchange"):
                agent.exchange = self.exchange
            agent.market = AgentClient(self.exchange, aid)
            if hasattr(agent, "reset"):
                agent.reset()

        self.current_step = 0
        self.price_history.clear()
        self.volume_history.clear()
        self.spread_history.clear()
        self.agent_pnl.clear()
        self._last_trade_ts = None

        if self.data_feed:
            self.data_feed.exchange = self.exchange
            if hasattr(self.data_feed, "reset"):
                self.data_feed.reset()

    def getMarketSnapshot(self) -> Dict[str, Any]:
        snapshot = {
            "step": self.current_step,
            "symbols": {},
        }

        for symbol in self.symbols:
            md = self.exchange.get_market_data(symbol)
            book = self.exchange.get_order_book(symbol)

            snapshot["symbols"][symbol] = {
                "last_price": md["last_price"],
                "best_bid": md["best_bid"],
                "best_ask": md["best_ask"],
                "mid_price": md["mid_price"],
                "spread": md["spread"],
                "num_trades": len(book.trade_history),
            }

        return snapshot

    def close(self) -> None:
        for aid in list(self._recv.keys()):
            self.unregister_agent(aid)
        self.exchange.stop_order_consumer()
        if self._own_dispatch and self.dispatch:
            self.dispatch.close()
        if self._own_hub:
            self.hub.clear()

    def __repr__(self) -> str:
        return (
            f"Simulation(step={self.current_step}, "
            f"agents={len(self.agents)}, "
            f"symbols={self.symbols})"
        )
