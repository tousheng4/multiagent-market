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
    setPriceHistory({})
    setTrades([])
    setAgentValues({})
    setNews([])
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
