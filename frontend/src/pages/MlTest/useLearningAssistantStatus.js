import { useCallback, useEffect, useState } from 'react'
import { getLearningAssistantStatus } from '../../api/learningStatusApi'

const INITIAL_STATUS = { status: 'checking', message: 'AI 연결 상태를 확인하고 있습니다.' }

/**
 * AI Server가 내려가거나 OpenAI 연결이 실패했을 때 배지를 실제 상태로 바꿉니다.
 * 30초 간격 확인은 즉시성·네트워크 요청량 사이의 균형을 위한 값입니다.
 */
export default function useLearningAssistantStatus() {
  const [assistantStatus, setAssistantStatus] = useState(INITIAL_STATUS)

  const refreshStatus = useCallback(async () => {
    try {
      const response = await getLearningAssistantStatus()
      setAssistantStatus(response)
    } catch (error) {
      setAssistantStatus({ status: 'inactive', message: error.message || 'AI 서버에 연결하지 못했습니다.' })
    }
  }, [])

  useEffect(() => {
    // Effect 본문에서는 구독만 설정하고, 실제 상태 요청은 다음 microtask에서 시작합니다.
    void Promise.resolve().then(refreshStatus)
    const timer = window.setInterval(refreshStatus, 30000)
    return () => window.clearInterval(timer)
  }, [refreshStatus])

  // 실제 답변 성공·실패도 즉시 반영해 다음 자동 점검을 기다리지 않게 합니다.
  const markActive = useCallback(() => setAssistantStatus({ status: 'active', message: 'AI 챗봇이 정상적으로 답변했습니다.' }), [])
  const markInactive = useCallback((error) => setAssistantStatus({
    status: 'inactive', message: error?.message || 'OpenAI 응답을 받지 못했습니다.',
  }), [])

  return { assistantStatus, markActive, markInactive }
}
