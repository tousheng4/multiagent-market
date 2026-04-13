from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# 加载 .env 文件
_dotenv_path = Path(__file__).parent / ".env"
load_dotenv(_dotenv_path)

from src import Exchange, Simulation
from src.agents.SimpleAgents import MarketMakerAgent, MomentumAgent, RandomAgent
from src.data import DataFeed, DataLoader
from src.data.NewsGenerator import NewsGenerator
from src.environment.dispatchers import AuditWriter, Idem, RiskWatcher
from src.environment.event_hub import EV_AUDIT, EV_ORDER_CMD, EV_NEWS, EV_SNAPSHOT, EventHub


def main() -> None:
    hub = EventHub()

    exchange = Exchange(initial_cash=100000.0, hub=hub)
    symbols = ["AAPL", "TSLA", "SPY"]

    # 创建新闻生成器
    news_generator = NewsGenerator(hub=hub, symbols=symbols)

    sim = Simulation(
        exchange=exchange,
        symbols=symbols,
        initial_cash=100000.0,
        hub=hub,
        async_mode=False,
        news_generator=news_generator,
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

    # 监听新闻事件（可选，用于验证）
    def on_news(msg):
        payload = msg.get("payload") or {}
        print(f"[NEWS] step={payload.get('step')} {payload.get('symbol')}: {payload.get('news')}")

    sim.on(EV_NEWS, on_news, name="news_printer")

    # 注册规则型 Agent
    mm = MarketMakerAgent(
        agent_id="mm-1",
        exchange=exchange,
        symbols=symbols,
        spread_bps=20.0,
        order_size=5,
        target_position=50,
    )
    sim.register_agent(mm, agentId="mm-1")

    # 给做市商预设一些股票持仓
    for symbol in symbols:
        exchange.position_records["mm-1"][symbol] = 50

    mom = MomentumAgent(
        agent_id="mom-1",
        exchange=exchange,
        symbols=symbols,
        lookback_period=5,
        momentum_threshold=0.01,
        order_size=10,
    )
    sim.register_agent(mom, agentId="mom-1")

    for symbol in symbols:
        exchange.position_records["mom-1"][symbol] = 30

    # 如果配置了 MiniMax API Key，则注册 ReAct Agent
    if os.environ.get("MINIMAX_API_KEY"):
        try:
            from src.agents.ReActAgents import (
                EvaluatorAgent,
                NewsAgent,
                RiskAgent,
                StrategyAgent,
            )
            from src.agents.tool.create_tools import create_all_tools

            tools = create_all_tools(
                exchange=exchange,
                news_generator=news_generator,
                memory_store=None,
            )

            # NewsAgent
            news_agent = NewsAgent(
                agent_id="news-agent-1",
                exchange=exchange,
                symbols=symbols,
                tools=[t for t in tools if t.name in ("get_recent_news", "search_news_by_symbol")],
                news_generator=news_generator,
                memory_store=None,
            )
            sim.register_agent(news_agent, agentId="news-agent-1")

            # StrategyAgent
            strategy_agent = StrategyAgent(
                agent_id="strategy-agent-1",
                exchange=exchange,
                symbols=symbols,
                tools=[t for t in tools if t.name in ("get_market_data", "get_account", "submit_order", "get_trade_history", "read_memory", "write_memory")],
                memory_store=None,
            )
            sim.register_agent(strategy_agent, agentId="strategy-agent-1")

            # RiskAgent
            risk_agent = RiskAgent(
                agent_id="risk-agent-1",
                exchange=exchange,
                symbols=symbols,
                tools=[],
                hub=hub,
                memory_store=None,
            )
            # RiskAgent 不通过 register_agent（不走 step 循环），直接由 hub 管理
            # 但为了一致性，可以不注册它，只作为独立组件存在

            # EvaluatorAgent
            evaluator_agent = EvaluatorAgent(
                agent_id="evaluator-agent-1",
                exchange=exchange,
                symbols=symbols,
                tools=[t for t in tools if t.name in ("get_account", "read_memory", "write_memory")],
                memory_store=None,
            )
            sim.register_agent(evaluator_agent, agentId="evaluator-agent-1")

            print("[ReAct] All ReAct agents registered successfully")
        except Exception as e:
            print(f"[ReAct] Failed to register ReAct agents: {e}")
    else:
        print("[ReAct] MINIMAX_API_KEY not set, skipping ReAct agents")

    for _ in range(10):
        sim.step()

    sim.close()


if __name__ == "__main__":
    main()
