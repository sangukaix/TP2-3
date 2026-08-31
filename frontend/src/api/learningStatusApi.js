/**
 * 학습용 챗봇의 서버·OpenAI 연결 상태를 조회합니다.
 * 이 요청은 모델 답변을 생성하지 않아 토큰을 사용하지 않습니다.
 */
export async function getLearningAssistantStatus() {
  const response = await fetch('/ai/v1/learning/assistant-status')
  if (!response.ok) throw new Error('AI 서버에 연결하지 못했습니다.')
  return response.json()
}
