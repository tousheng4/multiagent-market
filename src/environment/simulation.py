from typing import List, Dict, Optional, Any
from collections import defaultdict
import time

from ..market import Exchange, OrderType, OrderSide
from ..data.pipeline import DataFeed
from blinker import Namespace


class Simulation:
    """
    仿真环境类 - 协调市场和多个Agent的交互

    功能：
    - 管理仿真的时间步进
    - 协调Agent与交易所的交互
    - 收集和记录仿真数据
    - 提供事件通知机制
    """

    def __init__(
        self,
        exchange: Exchange,
        symbols: List[str],
        initialCash: float = 100000.0
    ):
        """
        初始化仿真环境

        Args:
            exchange: 交易所实例
            symbols: 交易的股票代码列表
            initialCash: 每个Agent的初始现金
        """
        self.exchange = exchange
        self.symbols = symbols
        self.initialCash = initialCash

        # 注册的Agent列表
        self.agents: List[Any] = []
        self.agentIdMap: Dict[str, Any] = {}

        # 仿真状态
        self.currentStep = 0
        self.isRunning = False

        # 数据记录
        self.priceHistory: Dict[str, List[float]] = defaultdict(list)
        self.volumeHistory: Dict[str, List[int]] = defaultdict(list)
        self.spreadHistory: Dict[str, List[float]] = defaultdict(list)

        # 性能指标
        self.agentPnL: Dict[str, List[float]] = defaultdict(list)

        # 初始化交易所的股票
        for symbol in symbols:
            self.exchange.addSymbol(symbol)

        # 可选的数据feed（由外部设置）
        self.dataFeed: Optional[DataFeed] = None
        self._signal_ns = Namespace()
        self.sig_data = self._signal_ns.signal("data")
        self.sig_snapshot = self._signal_ns.signal("market_snapshot")
        self._receivers: Dict[str, Dict[str, Any]] = {}

    def registerAgent(self, agent: Any, agentId: Optional[str] = None) -> str:
        """
        注册Agent到仿真环境

        Args:
            agent: Agent实例（需要有step方法）
            agentId: Agent ID（如果不指定则自动生成）

        Returns:
            Agent ID
        """
        if agentId is None:
            agentId = f"agent_{len(self.agents)}"

        if agentId in self.agentIdMap:
            raise ValueError(f"Agent {agentId} already registered")

        # 在交易所注册Agent
        self.exchange.registerAgent(agentId, self.initialCash)

        # 保存Agent引用
        self.agents.append(agent)
        self.agentIdMap[agentId] = agent

        # 设置Agent的ID（如果Agent有这个属性）
        if hasattr(agent, 'agentId'):
            agent.agentId = agentId
        if hasattr(agent, 'exchange'):
            agent.exchange = self.exchange
        recv_data = None
        recv_snapshot = None
        if hasattr(agent, 'onEvent'):
            recv_data = lambda sender, **kwargs: agent.onEvent({"type": "data", "payload": kwargs.get("payload")})
            self.sig_data.connect(recv_data, weak=False)
        if hasattr(agent, 'onSnapshot'):
            recv_snapshot = lambda sender, **kwargs: agent.onSnapshot(kwargs.get("payload"))
            self.sig_snapshot.connect(recv_snapshot, weak=False)
        self._receivers[agentId] = {"data": recv_data, "snapshot": recv_snapshot}

        return agentId

    def unregisterAgent(self, agentId: str) -> None:
        if agentId not in self.agentIdMap:
            return
        agent = self.agentIdMap.pop(agentId)
        if agent in self.agents:
            self.agents.remove(agent)
        recvs = self._receivers.pop(agentId, None)
        if recvs:
            if recvs.get("data") is not None:
                try:
                    self.sig_data.disconnect(recvs["data"])
                except Exception:
                    pass
            if recvs.get("snapshot") is not None:
                try:
                    self.sig_snapshot.disconnect(recvs["snapshot"])
                except Exception:
                    pass

    def step(self) -> Dict[str, Any]:
        """
        执行一个仿真步

        Returns:
            本步的统计信息
        """
        stepStartTime = time.time()

        # 0. 先推进数据feed（更新行情与时间）
        if self.dataFeed:
            try:
                feed_snapshot = self.dataFeed.step()
            except Exception as e:
                print(f"DataFeed error: {e}")
            else:
                if feed_snapshot is not None:
                    try:
                        self.sig_data.send(self, payload=feed_snapshot)
                    except Exception as e:
                        print(f"Event dispatch error: {e}")

        # 1. 让每个Agent执行决策
        for agent in self.agents:
            try:
                # Agent的step方法应该调用exchange的submitOrder
                if hasattr(agent, 'step'):
                    agent.step()
            except Exception as e:
                print(f"Error in agent {getattr(agent, 'agentId', 'unknown')}: {e}")

        # 2. 如果未使用dataFeed，仍保证时间推进
        if not self.dataFeed:
            self.exchange.step()

        # 3. 收集市场数据
        stepStats = self._collectStepData()

        # 4. 更新步数
        self.currentStep += 1

        stepStats['step'] = self.currentStep
        stepStats['elapsed_time'] = time.time() - stepStartTime

        try:
            self.sig_snapshot.send(self, payload=stepStats)
        except Exception as e:
            print(f"Snapshot dispatch error: {e}")
        return stepStats

    def _collectStepData(self) -> Dict[str, Any]:
        """收集当前步的数据"""
        stats = {
            'prices': {},
            'spreads': {},
            'volumes': {},
            'agent_values': {}
        }

        # 收集市场数据
        for symbol in self.symbols:
            marketData = self.exchange.getMarketData(symbol)

            lastPrice = marketData['last_price']
            spread = marketData['spread']

            # 记录历史
            if lastPrice is not None:
                self.priceHistory[symbol].append(lastPrice)
                stats['prices'][symbol] = lastPrice

            if spread is not None:
                self.spreadHistory[symbol].append(spread)
                stats['spreads'][symbol] = spread

            # 计算本步成交量
            trades = self.exchange.getTradeHistory(symbol=symbol)
            if trades:
                recentTrades = [t for t in trades if t.timestamp == self.exchange.currentTime - 1]
                volume = sum(t.quantity for t in recentTrades)
                self.volumeHistory[symbol].append(volume)
                stats['volumes'][symbol] = volume

        # 收集Agent数据
        for agentId in self.agentIdMap.keys():
            account = self.exchange.getAccount(agentId)
            portfolioValue = account['portfolio_value']
            self.agentPnL[agentId].append(portfolioValue)
            stats['agent_values'][agentId] = portfolioValue

        return stats

    def run(self, steps: int, verbose: bool = True) -> List[Dict[str, Any]]:
        """
        运行仿真

        Args:
            steps: 运行的步数
            verbose: 是否打印进度

        Returns:
            每步的统计信息列表
        """
        self.isRunning = True
        allStats = []

        startTime = time.time()

        for i in range(steps):
            stepStats = self.step()
            allStats.append(stepStats)

            if verbose and (i + 1) % 100 == 0:
                elapsed = time.time() - startTime
                print(f"Step {i + 1}/{steps} | "
                      f"Time: {elapsed:.2f}s | "
                      f"Speed: {(i + 1) / elapsed:.2f} steps/s")

        self.isRunning = False

        if verbose:
            totalTime = time.time() - startTime
            print(f"\nSimulation completed: {steps} steps in {totalTime:.2f}s "
                  f"({steps / totalTime:.2f} steps/s)")

        return allStats

    def getAgentPerformance(self, agentId: str) -> Dict[str, Any]:
        """
        获取Agent的性能指标

        Args:
            agentId: Agent ID

        Returns:
            性能指标字典
        """
        if agentId not in self.agentIdMap:
            raise ValueError(f"Agent {agentId} not found")

        account = self.exchange.getAccount(agentId)
        pnlHistory = self.agentPnL[agentId]

        if not pnlHistory:
            return {
                'current_value': self.initialCash,
                'total_return': 0.0,
                'max_drawdown': 0.0,
                'num_trades': 0
            }

        currentValue = pnlHistory[-1]
        totalReturn = (currentValue - self.initialCash) / self.initialCash

        # 计算最大回撤
        maxDrawdown = 0.0
        peak = self.initialCash
        for value in pnlHistory:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak
            if drawdown > maxDrawdown:
                maxDrawdown = drawdown

        # 统计交易次数
        trades = self.exchange.getTradeHistory(agentId=agentId)

        return {
            'agent_id': agentId,
            'initial_value': self.initialCash,
            'current_value': currentValue,
            'total_return': totalReturn,
            'total_return_pct': totalReturn * 100,
            'max_drawdown': maxDrawdown,
            'max_drawdown_pct': maxDrawdown * 100,
            'num_trades': len(trades),
            'cash': account['cash'],
            'positions': account['positions']
        }

    def getAllPerformance(self) -> Dict[str, Dict[str, Any]]:
        """获取所有Agent的性能指标"""
        return {
            agentId: self.getAgentPerformance(agentId)
            for agentId in self.agentIdMap.keys()
        }

    def reset(self) -> None:
        """重置仿真环境"""
        # 创建新的交易所
        self.exchange = Exchange(initialCash=self.initialCash)

        # 重新注册股票
        for symbol in self.symbols:
            self.exchange.addSymbol(symbol)

        # 重新注册Agents
        oldAgentIdMap = self.agentIdMap.copy()
        self.agentIdMap.clear()

        for agentId, agent in oldAgentIdMap.items():
            self.exchange.registerAgent(agentId, self.initialCash)
            self.agentIdMap[agentId] = agent
            if hasattr(agent, 'agentId'):
                agent.agentId = agentId
            if hasattr(agent, 'exchange'):
                agent.exchange = self.exchange
            if hasattr(agent, 'reset'):
                agent.reset()

        # 清空数据记录
        self.currentStep = 0
        self.priceHistory.clear()
        self.volumeHistory.clear()
        self.spreadHistory.clear()
        self.agentPnL.clear()

    def getMarketSnapshot(self) -> Dict[str, Any]:
        """获取市场快照"""
        snapshot = {
            'step': self.currentStep,
            'symbols': {}
        }

        for symbol in self.symbols:
            marketData = self.exchange.getMarketData(symbol)
            orderbook = self.exchange.getOrderBook(symbol)

            snapshot['symbols'][symbol] = {
                'last_price': marketData['last_price'],
                'best_bid': marketData['best_bid'],
                'best_ask': marketData['best_ask'],
                'mid_price': marketData['mid_price'],
                'spread': marketData['spread'],
                'num_trades': len(orderbook.tradeHistory)
            }

        return snapshot

    def __repr__(self) -> str:
        return (f"Simulation(step={self.currentStep}, "
                f"agents={len(self.agents)}, "
                f"symbols={self.symbols})")
