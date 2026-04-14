import './ConnectionStatus.css'

interface Props {
  connected: boolean
  step: number
}

export default function ConnectionStatus({ connected, step }: Props) {
  return (
    <div className={`connection-status ${connected ? 'connected' : 'disconnected'}`}>
      <span className="status-dot" />
      <span className="status-text">
        {connected ? 'LIVE' : '离线'}
      </span>
      {step > 0 && <span className="status-step">Step {step}</span>}
    </div>
  )
}
