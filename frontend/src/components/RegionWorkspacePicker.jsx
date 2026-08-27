import { SUPPORTED_TOURISM_REGIONS } from '../pages/tourismWorkspace'

/** bid3의 폼 필드처럼 모든 업무 화면에서 같은 분석 지역 선택 UI를 사용합니다. */
export default function RegionWorkspacePicker({ region, onChange }) {
  return <label className="work-region-picker"><span>분석 지역</span><select value={region.code} onChange={(event) => onChange(event.target.value)}>{SUPPORTED_TOURISM_REGIONS.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label>
}
