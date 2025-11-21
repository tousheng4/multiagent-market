from src import Exchange, Simulation
from src.data import DataLoader, DataFeed
from src.agents.SimpleAgents import MarketMakerAgent


def main():
    # 初始化交易所与仿真
    exchange = Exchange(initialCash=100000.0)
    symbols = ["AAPL", "TSLA", "SPY"]
    sim = Simulation(exchange=exchange, symbols=symbols, initialCash=100000.0)

    # 配置数据管线：从 data/raw 加载并驱动行情
    loader = DataLoader()
    sim.dataFeed = DataFeed(exchange, symbols, loader)

    # 注册一个简单做市商以验证数据驱动与下单
    mm = MarketMakerAgent(agentId="mm-1", exchange=exchange, symbols=symbols, spreadBps=20.0, orderSize=5, targetPosition=50)
    sim.registerAgent(mm, agentId="mm-1")

    # 订阅当前仿真实例的市场快照事件用于打印
    def on_snapshot(sender, **kwargs):
        try:
            payload = kwargs.get("payload") or {}
            print({k: v for k, v in payload.items() if k in ("prices", "spreads", "step", "agent_values")})
        except Exception as e:
            print(f"Snapshot print error: {e}")
    sim.sig_snapshot.connect(on_snapshot, weak=False)

    # 演示推进若干步（含Agent，事件驱动）
    for _ in range(10):
        sim.step()


if __name__ == "__main__":
    main()
