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