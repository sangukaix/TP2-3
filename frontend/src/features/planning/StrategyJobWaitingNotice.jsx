import { Clock3 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { formatJobElapsed, resolveJobStart } from './strategyJobClock'

export default function StrategyJobWaitingNotice({ jobId, startedAt }) {
  const [start] = useState(() => resolveJobStart(jobId, startedAt))
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const refresh = () => setNow(Date.now())
    const timer = window.setInterval(refresh, 1000)
    document.addEventListener('visibilitychange', refresh)
    window.addEventListener('focus', refresh)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', refresh)
      window.removeEventListener('focus', refresh)
    }
  }, [])
  return <div className="strategy-job-waiting">
    <span className="strategy-job-waiting-note">최대 30분까지 소요될 수 있으니 페이지를 닫지 마세요.</span>
    <span className="strategy-job-elapsed" role="timer" aria-live="off" aria-label={`생성 경과 시간 ${formatJobElapsed(start, now)}`}>
      <Clock3 size={14} aria-hidden="true" /><span>경과 시간</span><strong>{formatJobElapsed(start, now)}</strong>
    </span>
    {now - start >= 30 * 60 * 1000 && <span className="strategy-job-delay">예상 시간을 넘겨 처리 중입니다. 아래에서 서버의 현재 진행 상태를 확인해 주세요.</span>}
  </div>
}
