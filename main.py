from __future__ import annotations

from src import Exchange, Simulation
from src.agents.SimpleAgents import MarketMakerAgent
from src.data import DataFeed, DataLoader
from src.environment.dispatchers import AuditWriter, Idem, RiskWatcher
from src.environment.event_hub import EV_AUDIT, EV_ORDER_CMD, EV_SNAPSHOT, EventHub


def main() -> None:
    hub = EventHub()

    exchange = Exchange(initial_cash=100000.0, hub=hub)
    symbols = ["AAPL", "TSLA", "SPY"]
    sim = Simulation(
        exchange=exchange,
        symbols=symbols,
        initial_cash=100000.0,
        hub=hub,
        async_mode=True,
    )

    loader = DataLoader()
    sim.data_feed = DataFeed(exchange, symbols, loader)

    audit = AuditWriter("data/processed/audit.jsonl")
    risk = RiskWatcher()

    sim.on(EV_AUDIT, Idem(audit.write), name="audit_sink")
    sim.on(EV_ORDER_CMD, Idem(risk.on_order), name="risk_watch")

    def print_snapshot(msg):
        payload = msg.get("payload") or {}
        print({k: v for k, v in payload.items() if k in ("step", "prices", "spreads", "agent_values")})

    sim.on(EV_SNAPSHOT, print_snapshot, name="snapshot_printer")

    mm = MarketMakerAgent(
        agent_id="mm-1",
        exchange=exchange,
        symbols=symbols,
        spread_bps=20.0,
        order_size=5,
        target_position=50,
    )
    sim.register_agent(mm, agent_id="mm-1")

    for _ in range(10):
        sim.step()

    sim.close()


if __name__ == "__main__":
    main()
