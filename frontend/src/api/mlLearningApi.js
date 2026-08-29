/**
 * AI 서버가 등록 모델에서 자동으로 만든 학습용 카탈로그를 읽습니다.
 * 브라우저에는 모델 파일이나 비밀 키를 내려주지 않습니다.
 */
export async function getMlLearningCatalog() {
  const response = await fetch('/ai/v1/ml/learning/catalog')
  if (!response.ok) throw new Error('머신러닝 학습 정보를 불러오지 못했습니다.')
  return response.json()
}

/**
 * 선택 지역의 실제 모델 카탈로그를 근거로 ML 질문을 보냅니다.
 * OpenAI 키와 프롬프트는 AI Server에만 있고 브라우저에는 노출하지 않습니다.
 */
export async function chatWithMlLearningAssistant(regionCode, options) {
  const response = await fetch(`/ai/v1/ml/learning/${encodeURIComponent(regionCode)}/assistant`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options),
  })
  if (!response.ok) {
    const error = await response.json().catch(() => null)
    throw new Error(error?.detail?.message || 'ML 챗봇이 답변하지 못했습니다.')
  }
  return response.json()
}
