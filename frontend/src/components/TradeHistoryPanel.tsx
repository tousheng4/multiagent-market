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
