import './ControlButtons.css'

interface Props {
  active: boolean
  paused: boolean
  onStart: () => void
  onPause: () => void
  onResume: () => void
}

export default function ControlButtons({ active, paused, onStart, onPause, onResume }: Props) {
  return (
    <div className="control-buttons">
      {!active && (
        <button className="btn btn-start" onClick={onStart}>
          <span className="btn-icon">&#9654;</span> 启动仿真
        </button>
      )}
      {active && !paused && (
        <button className="btn btn-pause" onClick={onPause}>
          <span className="btn-icon">&#10074;&#10074;</span> 暂停
        </button>
      )}
      {active && paused && (
        <button className="btn btn-resume" onClick={onResume}>
          <span className="btn-icon">&#9654;</span> 继续
        </button>
      )}
    </div>
  )
}
