/** bid3의 폼 필드처럼 모든 업무 화면에서 같은 분석 지역 선택 UI를 사용합니다. */
export default function RegionWorkspacePicker({ region, regions = [], onChange, label = '분석 지역' }) {
  // 지역 목록은 AI 서버 카탈로그가 단일 기준입니다. 서버 연결 전에는 현재 선택값만
  // 남겨 선택 컴포넌트가 빈 값으로 깨지지 않게 합니다.
  const options = regions.length ? regions : [region]
  return <label className="work-region-picker"><span>{label}</span><select value={region.code} onChange={(event) => onChange(event.target.value)}>{options.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label>
}
