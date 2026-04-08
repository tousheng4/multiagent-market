from __future__ import annotations

from src import Exchange, Simulation
from src.agents.SimpleAgents import MarketMakerAgent, MomentumAgent, RandomAgent
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
        async_mode=False,
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
    sim.register_agent(mm, agentId="mm-1")

    # 给做市商预设一些股票持仓，这样它才会挂卖单
    for symbol in symbols:
        exchange.position_records["mm-1"][symbol] = 50

    # 添加一个动量Agent作为对手盘，促进交易
    mom = MomentumAgent(
        agent_id="mom-1",
        exchange=exchange,
        symbols=symbols,
        lookback_period=5,
        momentum_threshold=0.01,
        order_size=10,
    )
    sim.register_agent(mom, agentId="mom-1")

    # 给 MOM 预设一些股票持仓，这样它才能参与交易
    for symbol in symbols:
        exchange.position_records["mom-1"][symbol] = 30

    for _ in range(10):
        sim.step()

    sim.close()


if __name__ == "__main__":
    main()
