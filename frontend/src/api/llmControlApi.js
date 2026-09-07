/** 관리자 학습 화면이 LLM 상태·라우팅·실제 trace만 AI Server에서 읽습니다. */
async function readJson(url, options) {
  const response = await fetch(url, options)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail?.message || 'LLM Control Center 요청에 실패했습니다.')
  return payload
}

export const getLlmStatus = () => readJson('/ai/v1/llm/status')
export const getLlmConfig = () => readJson('/ai/v1/llm/config')
export const getLlmTrace = () => readJson('/ai/v1/llm/trace')
export const saveLlmConfig = (config, adminToken) => readJson('/ai/v1/llm/config', {
  method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-LLM-Admin-Token': adminToken }, body: JSON.stringify(config),
})
export const resetLlmConfig = (adminToken) => readJson('/ai/v1/llm/config/reset', {
  method: 'POST', headers: { 'X-LLM-Admin-Token': adminToken },
})
