import Plotly from 'react-plotly.js'
import './PriceChart.css'

interface DataPoint {
  x: number
  y: number
}

interface Props {
  data: Record<string, DataPoint[]>
}

const SYMBOL_COLORS: Record<string, string> = {
  AAPL: '#00f0ff',
  TSLA: '#f0f000',
  SPY: '#00ff88',
}

const LAYOUT = {
  paper_bgcolor: 'transparent',
  plot_bgcolor: 'transparent',
  font: { color: '#e0e0ff', family: 'JetBrains Mono, monospace', size: 11 },
  margin: { t: 10, r: 10, b: 40, l: 60 },
  xaxis: {
    title: { text: 'Step', font: { color: '#7070a0' } },
    gridcolor: '#1a1a2a',
    linecolor: '#00f0ff',
    tickcolor: '#00f0ff',
    zerolinecolor: '#2a2a4a',
  },
  yaxis: {
    title: { text: 'Price ($)', font: { color: '#7070a0' } },
    gridcolor: '#1a1a2a',
    linecolor: '#00f0ff',
    tickcolor: '#00f0ff',
    zerolinecolor: '#2a2a4a',
  },
  legend: {
    orientation: 'h',
    x: 0.5,
    xanchor: 'center',
    y: -0.15,
    bgcolor: 'rgba(0,0,0,0)',
    font: { color: '#e0e0ff' },
  },
  hovermode: 'x unified' as const,
  showlegend: true,
  hoverlabel: {
    bgcolor: '#0d0d1a',
    bordercolor: '#00f0ff',
    font: { color: '#e0e0ff', family: 'JetBrains Mono, monospace', size: 11 },
  },
} as Plotly.Layout

const CONFIG = {
  responsive: true,
  displayModeBar: true,
  modeBarButtonsToRemove: ['lasso2d', 'select2d'],
  displaylogo: false,
} as Plotly.Config

export default function PriceChart({ data }: Props) {
  const symbols = Object.keys(data)

  if (symbols.length === 0 || Object.values(data).every(arr => arr.length === 0)) {
    return (
      <div className="chart-empty">
        <span>等待数据...</span>
      </div>
    )
  }

  const traces: Plotly.Data[] = symbols.map(sym => ({
    x: data[sym].map(p => p.x),
    y: data[sym].map(p => p.y),
    type: 'scatter',
    mode: 'lines' as const,
    name: sym,
    line: { color: SYMBOL_COLORS[sym] || '#ffffff', width: 2 },
    hovertemplate: `<b>${sym}</b><br>Step %{x}<br>$%{y:.4f}<extra></extra>`,
  }))

  return (
    <div className="price-chart">
      <Plotly data={traces} layout={LAYOUT} config={CONFIG} useResizeHandler style={{ width: '100%', height: '100%' }} />
    </div>
  )
}
