import { SUPPORTED_TOURISM_REGIONS } from '../pages/tourismWorkspace'

/** bid3의 폼 필드처럼 모든 업무 화면에서 같은 분석 지역 선택 UI를 사용합니다. */
export default function RegionWorkspacePicker({ region, onChange, label = '분석 지역' }) {
  // 지역 목록은 tourismWorkspace 한 곳에서 관리합니다.
  // 각 페이지가 목록을 따로 적지 않아 지원 지역이 바뀌어도 선택 UI가 동일하게 유지됩니다.
  return <label className="work-region-picker"><span>{label}</span><select value={region.code} onChange={(event) => onChange(event.target.value)}>{SUPPORTED_TOURISM_REGIONS.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label>
}
