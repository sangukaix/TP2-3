/** 화면 표시용 answer/metadata를 API의 role/content 계약으로 변환합니다. */
export function chatHistory(messages) {
  return messages.filter((item) => ['user', 'assistant'].includes(item.role))
    .map((item) => ({ role: item.role, content: String(item.content || item.answer || '').trim().slice(0, 3000) }))
    .filter((item) => item.content).slice(-8)
}
