/** OpenAI·React 학습 페이지는 서버가 현재 소스에서 자동 생성한 구조를 사용합니다. */
export async function getProjectLearningCatalog(topic) {
  const response = await fetch(`/ai/v1/learning/${encodeURIComponent(topic)}`)
  if (!response.ok) throw new Error('프로젝트 학습 구조를 불러오지 못했습니다.')
  return response.json()
}

/** OpenAI 키와 프로젝트 설명 프롬프트는 AI Server에만 보관합니다. */
export async function chatWithProjectLearningAssistant(topic, options) {
  const response = await fetch(`/ai/v1/learning/${encodeURIComponent(topic)}/assistant`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(options),
  })
  if (!response.ok) {
    const error = await response.json().catch(() => null)
    throw new Error(error?.detail?.message || '학습 챗봇이 답변하지 못했습니다.')
  }
  return response.json()
}
