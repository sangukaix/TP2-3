import { useEffect, useState } from 'react'
import { getRegionReadinessAudit } from '../api/dashboardApi'

/** 자료 점검과 현재 연결을 함께 표시하며 조회 자체는 막지 않습니다. */
export default function RegionWorkspacePicker({ region, regions = [], onChange, label = '분석 지역' }) {
  const [audit, setAudit] = useState({ regions: [] })
  useEffect(() => {
    let active = true
    const refresh = () => getRegionReadinessAudit().then((value) => { if (active) setAudit(value) }).catch(() => { if (active) setAudit({ regions: [] }) })
    refresh()
    const timer = window.setInterval(refresh, 60000)
    return () => { active = false; window.clearInterval(timer) }
  }, [])
  const ready = (code) => audit.regions.some((row) => row.region_code === code && row.generation_ready)
  // 지역 목록은 AI 서버 카탈로그가 단일 기준입니다. 서버 연결 전에는 현재 선택값만
  // 남겨 선택 컴포넌트가 빈 값으로 깨지지 않게 합니다.
  const options = regions.length ? regions : [region]
  return <label className="work-region-picker"><span>{label}</span><select title="초록색: 자료 점검·로컬 연결 통과. 생성 중 응답 성공 보장은 아닙니다." style={{ color: ready(region.code) ? '#15803d' : undefined }} value={region.code} onChange={(event) => onChange(event.target.value)}>{options.map((item) => <option key={item.code} value={item.code} style={{ color: ready(item.code) ? '#15803d' : undefined }}>{item.name} · {ready(item.code) ? '준비됨' : '확인 필요'}</option>)}</select></label>
}
