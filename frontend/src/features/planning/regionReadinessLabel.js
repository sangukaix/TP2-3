export function regionReadinessLabel(audit, code) {
  const row = audit.regions?.find((item) => item.region_code === code)
  if (row?.data_ready) return '자료 준비됨'
  if (row) return row.readiness_reason || '자료 확인 필요'
  return '준비 상태 미확인'
}
