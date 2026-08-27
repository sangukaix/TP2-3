import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ChevronDown,
  ChevronUp,
  Download,
  ExternalLink,
  FileText,
  Info,
  LoaderCircle,
  Search,
  X,
} from 'lucide-react'
import { divIcon } from 'leaflet'
import { GeoJSON, MapContainer, Marker, Tooltip, useMapEvents } from 'react-leaflet'
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  LabelList,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Cell,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { downloadAiStrategyPresentation, downloadAiStrategyProposal, getAiRegionDashboard, getAiRegionOpenApiInfo, getSidoBoundaries, getSigunguBoundaries } from '../api/dashboardApi'
import TourismAssistant from '../components/TourismAssistant'
import WorkspaceShell from '../components/WorkspaceShell'
import '../App.css'

// 섬이 많거나 길쭉한 시도는 도형의 가운데에 자동으로 이름을 찍으면 글자가 바다 쪽으로 밀릴 수 있습니다.
// 전국 지도를 한눈에 읽기 좋게 하기 위해 각 시도의 육지 중심에 가까운 표시 좌표를 따로 둡니다.
const SIDO_LABEL_POSITIONS = {
  11: [37.57, 126.98], 12: [34.9, 126.66], 26: [35.16, 129.08], 27: [35.87, 128.61],
  // 인천은 섬 쪽이 아닌 본토의 왼쪽, 강원은 긴 도형의 중앙에 둬 인접 지역명과 겹치지 않게 합니다.
  28: [37.48, 126.57], 30: [36.27, 127.43], 31: [35.55, 129.29], 36: [36.51, 127.14],
  // 충북·세종·대전은 면적이 작고 인접해 레이블이 겹치므로, 각 행정구역 안에서 읽기 쉬운 위치로 간격을 둡니다.
  // 세종은 남서쪽, 충북은 북동쪽으로 분리해 두 명칭이 겹치지 않게 표시합니다.
  41: [37.35, 127.08], 43: [36.84, 127.77], 44: [36.5, 126.88], 47: [36.38, 128.67],
  48: [35.33, 128.2], 50: [33.38, 126.48], 51: [37.72, 128.28], 52: [35.74, 127.13],
}

// 작은 인접 시도는 경계 안의 좌표가 가까워도 Tooltip 자체의 폭 때문에 글자가 겹칠 수 있습니다.
// 아래 값은 라벨만 미세하게 이동하는 픽셀 오프셋이며, 지도·경계 데이터에는 영향을 주지 않습니다.
const SIDO_LABEL_OFFSETS = {
  30: [0, 13], // 대전광역시: 아래쪽
  36: [-8, 19], // 세종특별자치시: 왼쪽 아래
  43: [8, -19], // 충청북도: 오른쪽 위
}

// 전국 지도가 기본 110% 크기로 보이도록 Leaflet 확대값과 표시 값을 함께 맞춥니다.
const MAP_DEFAULT_ZOOM = 7.25
const MAP_DEFAULT_PERCENT = 110

// 이미지 파일 없이 CSS로 만든 지도 핀입니다. 선택 지역의 위치를 한눈에 알 수 있게 합니다.
const selectedRegionMarkerIcon = divIcon({
  className: 'selected-region-marker-wrapper',
  html: '<span class="selected-region-marker" aria-hidden="true"><span></span></span>',
  iconSize: [34, 42],
  iconAnchor: [17, 40],
})

// 시도명은 Path Tooltip이 아니라 투명한 Marker에 연결합니다.
// 이렇게 하면 섬이 포함된 도형의 자동 중심점으로 레이블이 다시 이동하지 않습니다.
const regionLabelAnchorIcon = divIcon({
  className: 'region-label-anchor',
  html: '<span aria-hidden="true"></span>',
  iconSize: [1, 1],
  iconAnchor: [0, 0],
})

/** Leaflet의 실제 확대 단계를 React 화면의 확대 비율 표시에 전달합니다. */
function MapZoomSync({ onZoomChange }) {
  const map = useMapEvents({
    zoomend: () => onZoomChange(map.getZoom()),
  })

  useEffect(() => {
    onZoomChange(map.getZoom())
  }, [map, onZoomChange])

  return null
}

/** 시군구 원자료가 아직 없는 지역에도 마커를 놓기 위한 간단한 경계 중심점 계산입니다. */
function getFeatureCenter(feature) {
  const coordinates = feature?.geometry?.coordinates
  if (!coordinates) return null

  const points = []
  const collectPoints = (value) => {
    if (typeof value[0] === 'number') points.push(value)
    else value.forEach(collectPoints)
  }
  collectPoints(coordinates)
  if (!points.length) return null

  const longitudes = points.map(([longitude]) => longitude)
  const latitudes = points.map(([, latitude]) => latitude)
  return [
    (Math.min(...latitudes) + Math.max(...latitudes)) / 2,
    (Math.min(...longitudes) + Math.max(...longitudes)) / 2,
  ]
}

/**
 * 지역 선택 지도입니다.
 * React Leaflet 컴포넌트로 지도를 그려 React의 state(선택 지역)와 연결합니다.
 * Backend에서 받은 행정구역 GeoJSON을 표시합니다.
 */
/**
 * 참고 화면처럼 전국 지도를 고정해 둔 선택 지도입니다.
 * 시도는 청록색, 선택한 시군구는 주황색으로 겹쳐 표시합니다. 지도 확대·전환 없이 색상만 바뀝니다.
 */
function RegionMap({
  sidoBoundaries, selectedSidoCode, selectedSigungu, markerPosition, markerLabel, onSelectSido, onZoomChange, isLoading, error,
}) {
  const onEachSido = (feature, layer) => {
    const { region_code: regionCode } = feature.properties
    layer.on({
      // 마우스를 올린 시도는 옅은 청록색으로 보여 클릭 가능한 영역임을 알립니다.
      mouseover: () => layer.setStyle({ color: '#49b9c5', fillColor: '#d8f3f5', fillOpacity: 0.96, weight: 1.6 }),
      mouseout: () => layer.setStyle(sidoStyle(feature)),
      click: () => onSelectSido(regionCode),
    })
  }

  const sidoStyle = (feature) => {
    const isSelected = feature.properties.region_code === selectedSidoCode
    return {
      color: isSelected ? '#0e96a6' : '#9aa8b7',
      fillColor: isSelected ? '#16b7c7' : '#f8fafc',
      fillOpacity: isSelected ? 0.8 : 0.92,
      weight: isSelected ? 2.2 : 0.75,
    }
  }

  return (
    <MapContainer
      center={[36.3, 127.8]}
      // 기본 크기는 사용자가 요청한 110% 화면으로 시작합니다.
      zoom={MAP_DEFAULT_ZOOM}
      // Leaflet 기본 확대 단위(1단계) 대신 작은 단위로 조절해 + / - 버튼이 부드럽게 움직이게 합니다.
      zoomDelta={0.25}
      zoomSnap={0.25}
      minZoom={5.75}
      maxZoom={10}
      // 마우스 휠로도 확대·축소할 수 있게 합니다. 픽셀 기준을 키워 과도하게 민감하지 않게 조정합니다.
      scrollWheelZoom
      wheelPxPerZoomLevel={110}
      className="region-map"
      aria-label="전국 시도와 시군구 선택 지도"
    >
      {sidoBoundaries?.features?.length && (
        <>
          <GeoJSON key={`sido-${selectedSidoCode}`} data={sidoBoundaries} style={sidoStyle} onEachFeature={onEachSido} />
          {selectedSigungu && (
            <GeoJSON
              key={selectedSigungu.properties.region_code}
              data={selectedSigungu}
              style={{ color: '#c35c13', fillColor: '#f58a2a', fillOpacity: 0.94, weight: 2.5 }}
            />
          )}
          {sidoBoundaries.features.map((feature) => {
              const { region_code: regionCode, region_name: regionName } = feature.properties
              const labelPosition = SIDO_LABEL_POSITIONS[regionCode] ?? getFeatureCenter(feature)
              const labelOffset = SIDO_LABEL_OFFSETS[regionCode] ?? [0, 0]
              if (!labelPosition) return null

              return (
                <Marker key={`label-${regionCode}`} position={labelPosition} icon={regionLabelAnchorIcon} interactive={false} keyboard={false}>
                  <Tooltip permanent direction="center" className={`region-label region-label--${regionCode}`} offset={labelOffset} opacity={1}>{regionName}</Tooltip>
                </Marker>
            )
          })}
        </>
      )}
      {markerPosition && <Marker position={markerPosition} icon={selectedRegionMarkerIcon} alt={`${markerLabel} 선택 위치`} />}
      <MapZoomSync onZoomChange={onZoomChange} />
      {isLoading && <div className="leaflet-map-message">행정구역 경계를 불러오는 중입니다.</div>}
      {error && <div className="leaflet-map-message leaflet-map-message--error">경계 서버에 연결하지 못했습니다. Backend를 실행한 뒤 새로고침하세요.</div>}
    </MapContainer>
  )
}

/** 카드 하나를 재사용하기 위한 컴포넌트입니다. 같은 UI를 반복 작성하지 않는 React 컴포넌트화 예시입니다. */
function MetricCard({ label, value, detail, changeLabel, changeValue, changeDirection = 'same', accent }) {
  // "17,963,441명"처럼 뒤에 붙은 단위만 작게 그려 숫자의 크기를 한눈에 읽게 합니다.
  const valueMatch = String(value).match(/^(.*?)(명|억|일|%p|%)$/)
  return (
      <article className={`metric-card metric-card--${accent}`}>
        <p>{label}</p>
        <strong>{valueMatch ? <><em>{valueMatch[1]}</em><small>{valueMatch[2]}</small></> : value}</strong>
        {/* 기준 설명이 있을 때만 별도 줄을 만들어, 빈 여백이 생기지 않게 합니다. */}
        {detail && <span className="metric-detail">{detail}</span>}
      {changeValue && <div className={`metric-card-change metric-card-change--${changeDirection}`}>
        <b>{changeValue}</b><span>{changeLabel}</span>
      </div>}
    </article>
  )
}

/**
 * 최신 월 원자료에서 계산한 소비 업종 비중입니다.
 * 숫자는 AI가 생성하지 않으며, 선택 지역 데이터랩 ZIP의 외지인 관광소비 표에서만 읽습니다.
 */
function ConsumptionCompositionDonut({ categories }) {
  const colors = ['#23b8c8', '#4d80d5', '#8061ca', '#df9950', '#dce6ed']
  const coveredShare = categories.reduce((total, category) => total + category.share, 0)
  const otherShare = Math.max(0, 100 - coveredShare)
  const chartData = [...categories, { name: '기타 업종', share: otherShare }]

  return (
    <section className="consumption-composition" aria-label="관광소비 업종 구성 도넛 그래프">
      <div className="consumption-donut-wrap">
        <ResponsiveContainer width="100%" height={164}>
          <PieChart>
            <Pie data={chartData} dataKey="share" nameKey="name" innerRadius={38} outerRadius={54} paddingAngle={2} stroke="none">
              {chartData.map((category, index) => <Cell key={category.name} fill={colors[index]} />)}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="consumption-donut-center"><b>기타</b><strong>{otherShare.toFixed(1)}%</strong></div>
      </div>
      <div className="consumption-donut-legend" aria-label="도넛 그래프 업종 범례">
        {chartData.map((category, index) => <span key={category.name}><i style={{ background: colors[index] }} />{category.name}</span>)}
      </div>
    </section>
  )
}

function TourismConsumptionStayDiagnostic({ diagnostic, latestMonth }) {
  const formatAmount = (value) => `₩${Math.round(Number(value) / 100_000_000).toLocaleString('ko-KR')}억`
  const monthLabel = latestMonth?.replace('-', '.') ?? '최신 월'

  if (!diagnostic) {
    return (
      <article className="tourism-diagnosis tourism-diagnosis--pending" id="consumption-diagnosis" aria-labelledby="tourism-diagnosis-title">
        <div className="tourism-diagnosis-heading"><h3 id="tourism-diagnosis-title">관광소비</h3></div>
        <div className="tourism-diagnosis-body">
          <section className="consumption-breakdown" aria-label="관광소비 업종 비중 준비 상태">
            <div className="diagnostic-subheading"><span>관광소비 업종 비중</span><small>원자료 연결 대기</small></div>
            <div className="consumption-category-list">
              {Array.from({ length: 4 }, (_, index) => (
                <div className="consumption-category consumption-category--empty" key={index}>
                  <span><i>{index + 1}</i>데이터 준비 중</span>
                  <b>—</b>
                  <small>—</small>
                </div>
              ))}
            </div>
          </section>
          <section className="consumption-composition consumption-composition--empty" aria-label="소비 구성 준비 상태">
            <div className="consumption-empty-donut" aria-hidden="true"><b>데이터</b><small>대기</small></div>
            <p>관광소비 원자료가 연결되면 업종별 비중을 표시합니다.</p>
          </section>
        </div>
      </article>
    )
  }

  return (
    <article className="tourism-diagnosis" id="consumption-diagnosis" aria-labelledby="tourism-diagnosis-title">
      <div className="tourism-diagnosis-heading">
        <h3 id="tourism-diagnosis-title">관광소비</h3>
      </div>
      <div className="tourism-diagnosis-body">
        <section className="consumption-breakdown" aria-label="관광소비 업종 비중">
          <div className="diagnostic-subheading"><span>관광소비 업종 비중</span><small>기준: {monthLabel}</small></div>
          <div className="consumption-category-list">
            {diagnostic.consumption_categories.map((category, index) => (
              <div className="consumption-category" key={category.name}>
                <span><i>{index + 1}</i>{category.name}</span>
                <b>{category.share.toFixed(1)}%</b>
                <small>{formatAmount(category.amount_krw)}</small>
              </div>
            ))}
          </div>
        </section>
        <ConsumptionCompositionDonut categories={diagnostic.consumption_categories} />
      </div>
    </article>
  )
}

/**
 * 시연용 AI 보고서입니다.
 * 실제 서비스에서는 /ai/reports API가 근거 URL, 데이터 기준월, 추천안을 구조화된 JSON으로 전달합니다.
 */
const REPORT_SOURCE_TYPE_LABELS = {
  dataset: '관광데이터랩',
  open_api: '관광 Open API',
  official_web: '공식 문서',
  rag: '공식 자료',
  benchmark_case: '공식 성공사례',
}

const EVIDENCE_STRENGTH_LABELS = { high: '근거 강함', medium: '근거 보통', low: '추가 확인 필요' }

function StrategyReport({ region, visible, report, isLoading, error, onClose, onDownload, onDownloadPptx, isDownloading, isPresentationDownloading, downloadError, executionScenario, onExecutionScenarioChange }) {
  const [isCollapsed, setIsCollapsed] = useState(false)
  const orderedStrategies = report ? [...report.strategies].sort((a, b) => a.priority - b.priority) : []
  const strategy = orderedStrategies[0]
  const benchmarkSources = report?.evidence_sources?.filter((source) => source.source_type === 'benchmark_case') ?? []

  if (!visible || (!report && !isLoading && !error)) return null

  return (
    <div className="strategy-modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="report-preview strategy-modal" role="dialog" aria-modal="true" aria-label="AI 전략기획서" onMouseDown={(event) => event.stopPropagation()}>
      <button type="button" className="strategy-modal-close" onClick={onClose} aria-label="AI 전략기획서 닫기"><X size={18} /></button>
      {report && <div className="report-heading">
        <div>
          <p className="eyebrow">관광 전략 기획안</p>
          <h2>{region.name} 관광객 유치 · 소비 확대 제안</h2>
        </div>
        <button
          type="button"
          className="report-collapse-toggle"
          onClick={() => setIsCollapsed((collapsed) => !collapsed)}
          aria-expanded={!isCollapsed}
          aria-controls="strategy-report-content"
        >
          {isCollapsed ? '기획안 펼치기' : '기획안 접기'}
        </button>
      </div>}

      <div id="strategy-report-content" hidden={isCollapsed}>
          {error && <p className="report-error">{error}</p>}
          {!report && isLoading && (
            <div className="strategy-report-loading" role="status" aria-live="polite">
              <span className="strategy-report-loading-icon"><LoaderCircle size={22} /></span>
              <div><strong>AI 전략기획서를 생성하고 있습니다.</strong><p>{region.name} 원자료와 근거를 바탕으로 실행 전략을 구성하는 중입니다.</p></div>
            </div>
          )}
          {report && <>
            {report.generation_mode === 'offline_sample' && <div className="offline-sample-notice" role="status"><b>오프라인 테스트 결과</b><span>실제 지역 원자료로 화면을 구성했으며, 공식 웹 조사와 OpenAI 작성·검수는 실행하지 않았습니다.</span></div>}
            <div className="report-summary"><div><span>핵심 제안</span><p>{report.summary}</p></div></div>
            {benchmarkSources.length > 0 && (
              <section className="report-case-studies" aria-labelledby="report-case-studies-title">
                <div className="report-case-studies-heading">
                  <div><span className="eyebrow">타 지역 공식 자료</span><h3 id="report-case-studies-title">전략 설계에 참고한 사례</h3></div>
                  <small>현지 조건에 맞게 범위·예산·지표를 다시 설계합니다.</small>
                </div>
                <div className="report-case-study-grid">
                  {benchmarkSources.slice(0, 3).map((source) => (
                    <a className="report-case-study-card" href={source.source_url} target="_blank" rel="noreferrer" key={source.source_id}>
                      <span>{EVIDENCE_STRENGTH_LABELS[source.evidence_strength] ?? '공식 자료'}</span>
                      <b>{source.title}</b>
                      <small>{source.summary}</small>
                    </a>
                  ))}
                </div>
              </section>
            )}
            <section className="report-trend-section" aria-labelledby="report-trend-title">
                <div className="report-trend-heading"><div><span className="eyebrow">원자료 기반 추세 그래프</span><h3 id="report-trend-title">월간 방문자 수·관광소비액 변화</h3></div><p>좌: 방문자 수 · 우: 관광소비액</p></div>
              <StrategyReportTrendChart trend={report.monthly_trend} />
                <p className="report-note">공식 원자료 기준 · 좌 방문자 수 / 우 관광소비액</p>
            </section>
            <div className="report-interaction-grid">
              <ReportActionRoadmap strategy={strategy} trend={report.monthly_trend} executionScenario={executionScenario} onExecutionScenarioChange={onExecutionScenarioChange} />
            </div>
            <section className="report-document-cta" aria-labelledby="proposal-download-title">
              <div><span className="eyebrow">Word 기획서</span><h3 id="proposal-download-title">회의용 기획안으로 정리</h3><p>핵심 지표, 실행 단계, 목표 비교 그래프, 예산 산정과 근거를 최대 5쪽으로 제공합니다.</p></div>
              <div className="report-download-actions">
                <button type="button" onClick={onDownload} disabled={isDownloading || isPresentationDownloading}>{isDownloading ? <LoaderCircle className="strategy-button-spinner" size={17} /> : <Download size={17} />}{isDownloading ? 'Word 생성 중…' : 'Word 다운로드'}</button>
                <button type="button" className="is-pptx" onClick={onDownloadPptx} disabled={isDownloading || isPresentationDownloading}>{isPresentationDownloading ? <LoaderCircle className="strategy-button-spinner" size={17} /> : <FileText size={17} />}{isPresentationDownloading ? 'PPT 생성 중…' : 'PowerPoint 다운로드'}</button>
              </div>
            </section>
            {downloadError && <p className="report-error">{downloadError}</p>}
            {report.evidence_sources?.length > 0 && <details className="report-evidence-list">
              <summary>사용한 근거 출처 보기 ({report.evidence_sources.length}건)</summary>
              <ul>{report.evidence_sources.slice(0, 10).map((source) => <li key={source.source_id}><span>{REPORT_SOURCE_TYPE_LABELS[source.source_type] ?? '공식 자료'}</span><a href={source.source_url} target="_blank" rel="noreferrer">{source.title}</a></li>)}</ul>
            </details>}
          </>}
      </div>
      </section>
    </div>
  )
}

/** 비교 진단에서 솔루션과 집행 순서로 이어지는 단일 기획안을 표시합니다. */
function ReportActionRoadmap({ strategy, trend, executionScenario, onExecutionScenarioChange }) {
  const implementationSteps = strategy?.implementation_steps ?? []

  if (!strategy) return null

  return (
    <section className="report-roadmap" aria-labelledby="report-roadmap-title">
      <div className="report-card-heading"><div><span className="eyebrow">AI 실행 요약</span><h3 id="report-roadmap-title">{strategy.title}</h3></div><span>{strategy.timeframe}</span></div>
      <div className="strategy-brief-grid">
        <section className="strategy-brief strategy-brief--problem"><span>문제 / 제안</span><p>{strategy.problem_to_solve}</p><div className="strategy-evidence"><b>이렇게 판단한 이유</b><small>{strategy.comparison_analysis}</small></div></section>
        <section className="strategy-brief strategy-brief--solution"><span>해결 방법</span><p>{strategy.solution}</p></section>
      </div>
      {implementationSteps.length > 0 && <div className="execution-plan"><div className="execution-plan-heading"><span>5단계 실행 방법</span><small>기간 · 해야 할 일 · 결과물</small></div><ol>{implementationSteps.map((step, index) => <li key={`${strategy.timeframe}-${index}`}><i>{step.step ?? index + 1}</i><div><em>{step.schedule}</em><b>{step.task}</b><small>완성되는 것 · {step.deliverable}</small></div></li>)}</ol><ExecutionTimeline steps={implementationSteps} /></div>}
      <ReportExecutionComparison trend={trend} executionScenario={executionScenario} onExecutionScenarioChange={onExecutionScenarioChange} />
      <div className="roadmap-result"><span>기대할 수 있는 변화</span><p>{strategy.expected_effect}</p></div>
    </section>
  )
}

/** 5단계와 각 소요 기간을 한눈에 보여 주는 프로젝트 타임라인입니다. */
function ExecutionTimeline({ steps }) {
  return <div className="execution-timeline" aria-label="5단계 프로젝트 일정"><div className="execution-timeline-line" />{steps.map((step, index) => <div className="execution-timeline-step" key={`timeline-${index}`}><span>{index + 1}</span><b>{step.schedule}</b><small>{step.deliverable}</small></div>)}</div>
}

/** 실행 여부를 비교하는 검토용 목표 그래프입니다. 검증된 ML 예측이 아닌 목표값 환산임을 명확히 표시합니다. */
function ReportExecutionComparison({ trend, executionScenario, onExecutionScenarioChange }) {
  const [planMonths, setPlanMonths] = useState(6)
  const [visibleSeries, setVisibleSeries] = useState({ baseline: true, execution: true })
  const presets = {
    보수: { visitor_target_pct: 3, spending_target_pct: 5 },
    목표: { visitor_target_pct: 5, spending_target_pct: 8 },
    확대: { visitor_target_pct: 8, spending_target_pct: 12 },
  }
  const target = executionScenario ?? presets.목표
  const selectedPreset = Object.entries(presets).find(([, value]) => value.visitor_target_pct === target.visitor_target_pct && value.spending_target_pct === target.spending_target_pct)?.[0]
  const latest = trend.at(-1)
  const baselineVisitors = latest?.visitors ?? 0
  const baselineSpending = latest?.spending_krw ?? 0
  const targetVisitors = Math.round(baselineVisitors * (1 + target.visitor_target_pct / 100))
  const targetSpending = Math.round(baselineSpending * (1 + target.spending_target_pct / 100))
  const additionalSpending = targetSpending - baselineSpending
  const makePlanMonth = (offset) => {
    const [year, month] = String(latest?.month ?? '').split('.').map(Number)
    const date = new Date(year || 2026, (month || 7) - 1 + offset, 1)
    return `${date.getFullYear()}.${String(date.getMonth() + 1).padStart(2, '0')}`
  }
  // 정책 인과효과를 추정하지 않고, 담당자가 고른 목표율을 계획 기간에 점진적으로 배분합니다.
  const scenarioData = Array.from({ length: planMonths + 1 }, (_, index) => {
    const progress = index / planMonths
    return {
      month: makePlanMonth(index),
      baseline_visitors: baselineVisitors,
      execution_visitors: Math.round(baselineVisitors * (1 + (target.visitor_target_pct / 100) * progress)),
      baseline_spending: baselineSpending,
      execution_spending: Math.round(baselineSpending * (1 + (target.spending_target_pct / 100) * progress)),
    }
  })
  const paddedDomain = (values) => {
    const minimum = Math.min(...values)
    const maximum = Math.max(...values)
    const padding = Math.max((maximum - minimum) * 0.32, Math.abs(maximum) * 0.006, 1)
    return [Math.max(0, Math.floor(minimum - padding)), Math.ceil(maximum + padding)]
  }
  const visitorValues = scenarioData.flatMap((row) => [
    ...(visibleSeries.baseline ? [row.baseline_visitors] : []),
    ...(visibleSeries.execution ? [row.execution_visitors] : []),
  ])
  const spendingValues = scenarioData.flatMap((row) => [
    ...(visibleSeries.baseline ? [row.baseline_spending] : []),
    ...(visibleSeries.execution ? [row.execution_spending] : []),
  ])
  if (!visitorValues.length) visitorValues.push(...scenarioData.flatMap((row) => [row.baseline_visitors, row.execution_visitors]))
  if (!spendingValues.length) spendingValues.push(...scenarioData.flatMap((row) => [row.baseline_spending, row.execution_spending]))
  const visitorDomain = paddedDomain(visitorValues)
  const spendingDomain = paddedDomain(spendingValues)
  const formatVisitors = (value) => `${Math.round(value).toLocaleString('ko-KR')}명`
  const formatSpending = (value) => `₩${Math.round(value / 100_000_000).toLocaleString('ko-KR')}억`
  const formatVisitorAxis = (value) => `${Math.round(value / 10_000).toLocaleString('ko-KR')}만`
  const formatSpendingAxis = (value) => `₩${Math.round(value / 100_000_000).toLocaleString('ko-KR')}억`
  const toggleSeries = (key) => setVisibleSeries((current) => ({ ...current, [key]: !current[key] }))

  return (
    <section className="execution-comparison" aria-labelledby="execution-comparison-title">
      <div className="execution-comparison-heading"><div><span>계획 기간 목표 추이</span><h4 id="execution-comparison-title">실행하면 무엇이 달라지나</h4></div><div className="scenario-presets" aria-label="실행 목표 수준">{Object.entries(presets).map(([preset, value]) => <button type="button" key={preset} className={selectedPreset === preset ? 'is-active' : ''} onClick={() => onExecutionScenarioChange(value)}>{preset}</button>)}</div></div>
      <div className="scenario-chart-controls"><div role="group" aria-label="계획 기간"><button type="button" className={planMonths === 3 ? 'is-active' : ''} onClick={() => setPlanMonths(3)}>3개월</button><button type="button" className={planMonths === 6 ? 'is-active' : ''} onClick={() => setPlanMonths(6)}>6개월</button></div><div role="group" aria-label="비교 선 표시"><button type="button" className={visibleSeries.baseline ? 'is-active baseline' : 'baseline'} onClick={() => toggleSeries('baseline')}>미실행</button><button type="button" className={visibleSeries.execution ? 'is-active execution' : 'execution'} onClick={() => toggleSeries('execution')}>실행 목표</button></div></div>
      <div className="execution-comparison-chart"><ResponsiveContainer width="100%" height={270}><ComposedChart data={scenarioData} margin={{ top: 22, right: 12, left: 8, bottom: 2 }}><CartesianGrid stroke="#dce7ef" vertical={false} /><XAxis dataKey="month" tick={{ fill: '#63778d', fontSize: 10 }} tickLine={false} axisLine={false} /><YAxis yAxisId="visitors" domain={visitorDomain} allowDataOverflow width={50} tick={{ fill: '#75869a', fontSize: 9 }} tickLine={false} axisLine={false} tickFormatter={formatVisitorAxis} /><YAxis yAxisId="spending" domain={spendingDomain} allowDataOverflow orientation="right" width={52} tick={{ fill: '#75869a', fontSize: 9 }} tickLine={false} axisLine={false} tickFormatter={formatSpendingAxis} /><ChartTooltip formatter={(value, name) => [name.includes('visitors') ? formatVisitors(value) : formatSpending(value), name.includes('visitors') ? (name.startsWith('execution') ? '실행 목표 방문자 수' : '미실행 방문자 수') : (name.startsWith('execution') ? '실행 목표 관광소비액' : '미실행 관광소비액')]} /><Legend wrapperStyle={{ fontSize: 10, paddingTop: 4 }} formatter={(value) => value} />{visibleSeries.baseline && <><Line yAxisId="visitors" type="monotone" dataKey="baseline_visitors" name="미실행 방문자 수" stroke="#92a4b7" strokeWidth={2} strokeDasharray="5 4" dot={false} /><Line yAxisId="spending" type="monotone" dataKey="baseline_spending" name="미실행 관광소비액" stroke="#b6a9d7" strokeWidth={2} strokeDasharray="5 4" dot={false} /></>}{visibleSeries.execution && <><Line yAxisId="visitors" type="monotone" dataKey="execution_visitors" name="실행 목표 방문자 수" stroke="#22aebf" strokeWidth={3} dot={{ r: 3, fill: '#fff', stroke: '#22aebf', strokeWidth: 2 }} /><Line yAxisId="spending" type="monotone" dataKey="execution_spending" name="실행 목표 관광소비액" stroke="#805dca" strokeWidth={3} dot={{ r: 3, fill: '#fff', stroke: '#805dca', strokeWidth: 2 }} /></>}</ComposedChart></ResponsiveContainer></div>
      <div className="execution-metric-grid"><div><span>방문자 수</span><b>{formatVisitors(baselineVisitors)} <i>→</i> {formatVisitors(targetVisitors)}</b><small>+{target.visitor_target_pct}% 목표</small></div><div><span>관광소비액</span><b>{formatSpending(baselineSpending)} <i>→</i> {formatSpending(targetSpending)}</b><small>+{target.spending_target_pct}% 목표</small></div><div className="execution-delta"><span>추가 관광소비</span><b>+{formatSpending(additionalSpending)}</b><small>실행 목표 − 미실행</small></div></div>
    </section>
  )
}

/** 보고서의 월간 그래프는 AI 응답이 아닌 서버가 원본 ZIP에서 계산한 실제 시계열을 표시합니다. */
function StrategyReportTrendChart({ trend }) {
  return <MonthlyActualTrendChart trend={trend} height={290} />
}

// shadcn/ui Charts처럼 데이터 키, 표시 이름, 색상을 한 곳에 모읍니다.
// 다른 관광 차트를 추가할 때도 이 설정을 재사용하면 범례·툴팁의 표현이 일관됩니다.
const TOURISM_CHART_CONFIG = {
  visitors: { label: '방문자 수', color: '#30bfd0' },
  spending_krw: { label: '관광소비액', color: '#8560cc' },
}

/** Recharts 기본 툴팁 대신 담당자가 단위와 기준월을 바로 읽는 카드형 툴팁입니다. */
function TourismChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null

  return (
    <div className="tourism-chart-tooltip">
      <p>{label} 기준</p>
      {payload.map((entry) => {
        const series = TOURISM_CHART_CONFIG[entry.dataKey]
        const isVisitor = entry.dataKey === 'visitors'
        const value = Number(entry.value)
        return (
          <div className="tourism-chart-tooltip-row" key={entry.dataKey}>
            <span><i style={{ background: series?.color ?? entry.color }} />{series?.label ?? entry.name}</span>
            <b>{isVisitor ? `${value.toLocaleString('ko-KR')}명` : `₩${value.toLocaleString('ko-KR')}`}</b>
          </div>
        )
      })}
    </div>
  )
}

/** 차트 하단 범례도 Recharts의 기본 문구 대신 서비스 색상표와 같은 형식으로 그립니다. */
function TourismChartLegend({ payload }) {
  if (!payload?.length) return null

  return (
    <ul className="tourism-chart-legend" aria-label="그래프 항목">
      {payload.map((entry) => {
        const series = TOURISM_CHART_CONFIG[entry.dataKey]
        return <li key={entry.dataKey}><i style={{ background: series?.color ?? entry.color }} />{series?.label ?? entry.value}{entry.dataKey === 'visitors' && <small>(만 단위)</small>}</li>
      })}
    </ul>
  )
}

/**
 * 서로 단위가 다른 방문자 수와 소비액을 양쪽 축으로 분리합니다.
 * 상대지수로 변환하지 않아 담당자가 월별 실제 규모를 바로 읽을 수 있습니다.
 */
function MonthlyActualTrendChart({ trend, height = 278, emptyMessage = '월간 원자료를 불러오는 중입니다.' }) {
  const formatVisitorTick = (value) => `${Math.round(value / 10_000).toLocaleString('ko-KR')}만`
  const formatSpendingTick = (value) => `${Math.round(value / 100_000_000).toLocaleString('ko-KR')}억`
  const renderVisitorBarLabel = ({ x, y, width, height: barHeight, value }) => {
    const amount = Number(value)
    // 매우 낮은 막대는 두 줄 라벨이 겹칠 수 있어 표시하지 않습니다.
    if (!Number.isFinite(amount) || Number(barHeight) < 32) return null
    const number = amount >= 100_000_000
      ? (amount / 100_000_000).toFixed(1)
      : Math.round(amount / 10_000).toLocaleString('ko-KR')
    const centerX = Number(x) + Number(width) / 2
    const centerY = Number(y) + Number(barHeight) / 2
    return (
      <text x={centerX} y={centerY} fill="#fff" fontSize={10} fontWeight={500} textAnchor="middle">
        <tspan x={centerX} dy=".35em">{number}</tspan>
      </text>
    )
  }
  // 최대값의 약 1.5배를 축 상한으로 잡아, 가장 큰 막대·선이 상단에 붙지 않게 합니다.
  // 지역별 수치 규모가 달라도 읽기 좋은 약 2/3 높이를 유지합니다.
  const paddedAxisMax = (dataMax) => {
    const target = Number(dataMax) * 1.5
    if (!Number.isFinite(target) || target <= 0) return 1
    const halfMagnitude = 10 ** Math.floor(Math.log10(target)) / 2
    return Math.ceil(target / halfMagnitude) * halfMagnitude
  }

  if (!trend?.length) return <div className="trend-empty-state">{emptyMessage}</div>

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={trend} margin={{ top: 28, right: 20, left: 14, bottom: 10 }}>
        <CartesianGrid stroke="#dfe5ea" strokeDasharray="0" vertical={false} />
        <XAxis dataKey="month" axisLine={{ stroke: '#2f3640' }} tickLine={{ stroke: '#2f3640' }} tick={{ fill: '#424b58', fontSize: 11 }} />
        <YAxis yAxisId="visitors" axisLine={{ stroke: '#2f3640' }} tickLine={{ stroke: '#2f3640' }} tick={{ fill: '#424b58', fontSize: 10 }} width={54} tickFormatter={formatVisitorTick} domain={[0, paddedAxisMax]} />
        <YAxis yAxisId="spending" orientation="right" axisLine={{ stroke: '#2f3640' }} tickLine={{ stroke: '#2f3640' }} tick={{ fill: '#424b58', fontSize: 10 }} width={54} tickFormatter={formatSpendingTick} domain={[0, paddedAxisMax]} />
        <ChartTooltip cursor={{ fill: '#1fbac80d' }} content={<TourismChartTooltip />} />
        <Legend verticalAlign="bottom" content={<TourismChartLegend />} />
        <Bar yAxisId="visitors" dataKey="visitors" name={TOURISM_CHART_CONFIG.visitors.label} fill={TOURISM_CHART_CONFIG.visitors.color} barSize={25} radius={[4, 4, 0, 0]}>
          {/* 막대 내부 중앙에 두 줄로 표시해 어떤 화면 크기에서도 라벨이 막대 밖으로 튀지 않게 합니다. */}
          <LabelList content={renderVisitorBarLabel} />
        </Bar>
        <Line yAxisId="spending" type="monotone" dataKey="spending_krw" name={TOURISM_CHART_CONFIG.spending_krw.label} stroke={TOURISM_CHART_CONFIG.spending_krw.color} strokeWidth={3.5} dot={{ r: 4, fill: '#fff', stroke: TOURISM_CHART_CONFIG.spending_krw.color, strokeWidth: 2 }} activeDot={{ r: 6 }} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

function TourismTrendChart({ trend, emptyMessage }) {
  return <div className="trend-chart-wrap"><MonthlyActualTrendChart trend={trend} emptyMessage={emptyMessage} /></div>
}

/** 실제 관광 원자료가 아직 없는 시군구를 선택했을 때, 다른 지역의 시연값을 잘못 보여주지 않기 위한 빈 대시보드입니다. */
function createPendingRegion(regionCode, regionName) {
  return {
    code: regionCode,
    name: regionName,
    metrics: { visitors: '연동 준비', spending: '연동 준비', stayRate: '연동 준비', perVisit: '연동 준비' },
    trend: ['1월', '2월', '3월', '4월', '5월', '6월'].map((month) => ({ month, '방문객 지수': 0, '관광소비 지수': 0 })),
    insights: [
      { icon: '◎', title: '관광 관심도', value: '자료 연결 대기', description: '내비게이션·검색 자료 확인 필요', tone: 'aqua' },
      { icon: '◒', title: '유입 권역', value: '자료 연결 대기', description: '방문자 기준지역 자료 확인 필요', tone: 'blue' },
      { icon: '⌂', title: '체류 전환', value: '자료 연결 대기', description: '숙박·체류시간 자료 확인 필요', tone: 'purple' },
      { icon: '▦', title: '관광 인프라', value: '자료 연결 대기', description: '관광지·교통 자료 확인 필요', tone: 'orange' },
    ],
    forecast: { visitors: '데이터 연동 후 산출', spending: '데이터 연동 후 산출', signal: '월간 원자료·모델 준비 필요' },
    report: {
      observation: '선택한 시군구의 검증된 관광 원자료가 아직 연결되지 않았습니다.',
      direction: '방문자·관광소비·체류·관심도 파일을 지역 코드와 기준월 기준으로 연결한 뒤 전략을 생성합니다.',
      actions: [
        { priority: '1', action: '월간 방문자 자료 연결', evidence: '한국관광 데이터랩 공식 원자료', metric: '월별 방문 관광객' },
        { priority: '2', action: '관광소비 자료 연결', evidence: '내국인 카드 관광지출액 원자료', metric: '방문자 1인당 소비액' },
        { priority: '3', action: '체류·관심도 자료 연결', evidence: '숙박체류·내비게이션 지표', metric: '체류 비율·관심도' },
      ],
    },
  }
}

/**
 * 지역 대시보드의 수치와 관광 Open API 자원을 한 팝업에서 분리해 보여줍니다.
 * 방문·소비 수치는 원자료 요약이고, 아래 관광자원 목록은 Open API 응답입니다.
 */
function RegionInfoModal({ visible, onClose, region, dashboard, info, state, error }) {
  if (!visible) return null

  const metrics = dashboard?.metrics ?? []
  const resources = info?.resources ?? []
  const categories = info?.category_summary ?? []
  const isLoading = state === 'loading'

  return (
    <div className="region-info-modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="region-info-modal" role="dialog" aria-modal="true" aria-labelledby="region-info-modal-title" onMouseDown={(event) => event.stopPropagation()}>
        <button type="button" className="region-info-modal-close" onClick={onClose} aria-label="지역 정보 상세보기 닫기"><X size={18} /></button>
        <header className="region-info-modal-heading">
          <span><Info size={15} /> 지역 정보 상세보기</span>
          <h2 id="region-info-modal-title">{region.name} 관광 현황</h2>
          <p>월간 수치는 관광데이터랩 원자료, 관광자원은 한국관광공사 Open API에서 각각 확인합니다.</p>
        </header>

        <section className="region-info-data-summary" aria-label="관광데이터랩 원자료 요약">
          <div className="region-info-section-title"><span>관광데이터랩 원자료</span><small>{dashboard?.latest_month ? `${dashboard.latest_month.replace('-', '.')} 기준` : '자료 연결 상태'}</small></div>
          {metrics.length > 0 ? (
            <div className="region-info-metric-grid">
              {metrics.slice(0, 3).map((metric) => <div key={metric.label}><span>{metric.label}</span><b>{metric.value}</b></div>)}
            </div>
          ) : <p className="region-info-empty">이 지역의 월간 원자료가 아직 연결되지 않았습니다.</p>}
        </section>

        <section className="region-info-open-api" aria-label="관광 Open API 관광자원">
          <div className="region-info-section-title">
            <span>관광자원 · 연계 정보</span>
            {info?.source_url && <a href={info.source_url} target="_blank" rel="noreferrer">공식 API 보기 <ExternalLink size={12} /></a>}
          </div>
          {isLoading && <div className="region-info-loading"><LoaderCircle size={20} />관광 Open API 정보를 불러오는 중입니다.</div>}
          {!isLoading && error && <p className="region-info-error">{error}</p>}
          {!isLoading && !error && info && (
            <>
              <p className={`region-info-api-message region-info-api-message--${info.status}`}>{info.message}</p>
              {categories.length > 0 && <div className="region-info-category-chips">{categories.map((category) => <span key={category.name}>{category.name}<b>{category.count}</b></span>)}</div>}
              {resources.length > 0 && (
                <div className="region-info-resource-grid">
                  {resources.slice(0, 8).map((resource) => (
                    <article key={`${resource.title}-${resource.address}`} className="region-info-resource-card">
                      {resource.image_url ? <img src={resource.image_url} alt="" loading="lazy" /> : <div className="region-info-resource-image"><span>{resource.content_type}</span></div>}
                      <div><span>{resource.content_type}</span><h3>{resource.title}</h3><p>{resource.address || '주소 정보 없음'}</p></div>
                    </article>
                  ))}
                </div>
              )}
            </>
          )}
        </section>

        <footer className="region-info-modal-note">관광자원 정보는 Open API의 반환 결과이며, 월간 방문자·관광소비 수치와는 집계 기준이 다를 수 있습니다.</footer>
      </section>
    </div>
  )
}

function DashboardApp() {
  // useState는 화면에서 바뀌는 값(현재 선택한 시군구, 보고서 열림 여부)을 기억하는 React 기본 기능입니다.
  // 첫 화면은 특정 시군구가 아닌 서울특별시 전체를 기본 선택합니다.
  const [selectedCode, setSelectedCode] = useState('11680')
  const [selectedSidoCode, setSelectedSidoCode] = useState('11')
  const [isReportVisible, setIsReportVisible] = useState(false)
  const [strategyReport, setStrategyReport] = useState(null)
  // AI 전략기획은 전용 페이지에서 생성합니다. 이 대시보드에서는 생성 상태를 만들지 않습니다.
  const isStrategyReportLoading = false
  const [strategyReportError, setStrategyReportError] = useState('')
  const [isProposalDownloading, setIsProposalDownloading] = useState(false)
  const [isPresentationDownloading, setIsPresentationDownloading] = useState(false)
  const [proposalDownloadError, setProposalDownloadError] = useState('')
  // 목표 비교는 정책 효과 예측이 아니라 담당자가 검토할 실행 목표값입니다.
  // 같은 값을 Word 기획서에도 전달해 화면과 문서의 기준이 달라지지 않게 합니다.
  const [executionScenario, setExecutionScenario] = useState({ visitor_target_pct: 5, spending_target_pct: 8 })
  const [mapZoom, setMapZoom] = useState(MAP_DEFAULT_ZOOM)
  const [sidoBoundaries, setSidoBoundaries] = useState(null)
  const [sigunguBoundaries, setSigunguBoundaries] = useState(null)
  const [isBoundaryLoading, setIsBoundaryLoading] = useState(true)
  const [boundaryError, setBoundaryError] = useState(false)
  const [regionDashboard, setRegionDashboard] = useState(null)
  const [regionDashboardState, setRegionDashboardState] = useState('idle')
  const [regionSearch, setRegionSearch] = useState('')
  const [regionSearchMessage, setRegionSearchMessage] = useState('')
  const [isRegionInfoVisible, setIsRegionInfoVisible] = useState(false)
  const [regionInfo, setRegionInfo] = useState(null)
  const [regionInfoState, setRegionInfoState] = useState('idle')
  const [regionInfoError, setRegionInfoError] = useState('')
  const [showScrollTop, setShowScrollTop] = useState(false)
  const [isAssistantOpen, setIsAssistantOpen] = useState(false)

  useEffect(() => {
    const updateScrollTopVisibility = () => setShowScrollTop(window.scrollY > 360)
    updateScrollTopVisibility()
    window.addEventListener('scroll', updateScrollTopVisibility, { passive: true })
    return () => window.removeEventListener('scroll', updateScrollTopVisibility)
  }, [])

  const selectedBoundary = useMemo(
    () => sigunguBoundaries?.features?.find((feature) => feature.properties.region_code === selectedCode) ?? null,
    [selectedCode, sigunguBoundaries],
  )

  const selectedSido = useMemo(
    () => sidoBoundaries?.features?.find((feature) => feature.properties.region_code === selectedSidoCode) ?? null,
    [selectedSidoCode, sidoBoundaries],
  )

  // 경계 이름만 화면 메타데이터로 사용합니다. 실제 지표는 AI Server 응답이 성공한 경우에만 채웁니다.
  // 이렇게 하면 미지원 지역에서 개발용 예시 숫자가 실제 값처럼 노출되지 않습니다.
  const selectedRegion = useMemo(
    () => (selectedBoundary
      ? createPendingRegion(selectedCode, selectedBoundary.properties.region_name)
      : selectedCode === '11680'
        ? createPendingRegion('11680', '서울특별시 강남구')
      : selectedSido
        ? createPendingRegion(selectedSidoCode, selectedSido.properties.region_name)
        : createPendingRegion(selectedSidoCode, selectedSidoCode === '11' ? '서울특별시' : '선택 지역')),
    [selectedBoundary, selectedCode, selectedSido, selectedSidoCode],
  )

  // 다른 업무 페이지에서도 같은 시군구를 이어서 검토할 수 있도록, 실제 시군구 선택만 저장합니다.
  useEffect(() => {
    if (selectedCode && selectedRegion.name) {
      window.localStorage.setItem('tour-insight-selected-region', JSON.stringify({ code: selectedCode, name: selectedRegion.name }))
    }
  }, [selectedCode, selectedRegion.name])

  // 원본이 검증된 지원 지역만 FastAPI 응답으로 최신월·전월 대비 값을 표시합니다.
  const dashboardMetrics = useMemo(() => {
    if (regionDashboard) {
      // FastAPI(Pydantic)는 snake_case로 JSON을 보내므로 React 카드 props의 camelCase로 한 번만 변환합니다.
      return regionDashboard.metrics.map((metric) => ({
        ...metric,
        changeLabel: metric.change_label,
        changeValue: metric.change_value,
        changeDirection: metric.change_direction,
      }))
    }

    return [
      { label: '최근 월 방문자 수', value: selectedRegion.metrics.visitors, detail: '외지인 · 이동통신 기반', changeLabel: '전월 대비', changeValue: '자료 연결 대기', accent: 'aqua' },
      { label: '최근 월 관광소비액', value: selectedRegion.metrics.spending, detail: '내국인 · 카드 기반 관광소비', changeLabel: '전월 대비', changeValue: '자료 연결 대기', accent: 'blue' },
      { label: '최근 월 숙박 방문 비율', value: selectedRegion.metrics.stayRate, detail: '외지인 · 이동통신 기반', changeLabel: '전월 대비', changeValue: '자료 연결 대기', accent: 'purple' },
    ]
  }, [regionDashboard, selectedRegion])

  const sigunguInSelectedSido = useMemo(
    () => selectedSidoCode
      ? (sigunguBoundaries?.features?.filter((feature) => feature.properties.region_code.startsWith(selectedSidoCode)) ?? [])
      : [],
    [selectedSidoCode, sigunguBoundaries],
  )

  const selectedMarkerPosition = useMemo(
    () => getFeatureCenter(selectedBoundary)
      ?? SIDO_LABEL_POSITIONS[selectedSidoCode]
      ?? null,
    [selectedBoundary, selectedSidoCode],
  )

  // useCallback으로 함수를 고정해 지도 이벤트가 불필요하게 다시 연결되지 않게 합니다.
  const handleMapZoomChange = useCallback((zoom) => setMapZoom(zoom), [])
  // + / - 한 단계(0.25)마다 10%씩 표시해 현재 배율을 쉽게 파악할 수 있게 합니다.
  const zoomPercent = MAP_DEFAULT_PERCENT + Math.round((mapZoom - MAP_DEFAULT_ZOOM) * 40)

  // 화면을 처음 열 때에만 Backend에 경계 GeoJSON을 요청합니다.
  // 경계가 준비되기 전에는 빈 배경과 안내문만 보여 기본 타일 지도가 잠깐 노출되지 않게 합니다.
  useEffect(() => {
    let isActive = true

    // 시도 경계가 먼저 도착하면 1단계 지도를 바로 표시하고, 시군구 경계는 뒤에서 준비합니다.
    getSidoBoundaries()
      .then((geoJson) => {
        if (isActive) setSidoBoundaries(geoJson)
      })
      .catch(() => {
        if (isActive) setBoundaryError(true)
      })
      .finally(() => {
        if (isActive) setIsBoundaryLoading(false)
      })

    return () => { isActive = false }
  }, [])

  // 브라우저에는 현재 시도의 시군구만 전달해 전국 상세 경계 수십 MB를 한꺼번에 파싱하지 않습니다.
  useEffect(() => {
    let isActive = true
    if (!selectedSidoCode) return () => { isActive = false }

    getSigunguBoundaries(selectedSidoCode)
      .then((geoJson) => {
        if (isActive) setSigunguBoundaries(geoJson)
      })
      .catch(() => {
        // 시도 지도는 계속 사용할 수 있게 두고, 시군구 선택만 준비 상태로 남깁니다.
      })

    return () => { isActive = false }
  }, [selectedSidoCode])

  // 이 요청은 OpenAI를 호출하지 않고 선택 지역 공식 원본의 최신 월·직전 월만 계산합니다.
  useEffect(() => {
    let isActive = true

    if (!selectedCode) {
      return () => { isActive = false }
    }

    getAiRegionDashboard(selectedCode, selectedRegion.name)
      .then((data) => {
        if (isActive) {
          setRegionDashboard(data)
          setRegionDashboardState('ready')
        }
      })
      .catch(() => {
        if (isActive) {
          setRegionDashboard(null)
          setRegionDashboardState('unavailable')
        }
      })

    return () => { isActive = false }
  }, [selectedCode, selectedRegion.name])

  // 지역 선택 이벤트에서만 이전 지역(현재는 강남구)의 AI 문서를 초기화합니다.
  // useEffect가 아니라 선택 처리 함수에서 실행해 불필요한 추가 렌더링을 막습니다.
  const clearStrategyReport = () => {
    setStrategyReport(null)
    setStrategyReportError('')
    setProposalDownloadError('')
    setExecutionScenario({ visitor_target_pct: 5, spending_target_pct: 8 })
    // 지역을 바꾸면 이전 지역의 Open API 상세 정보도 함께 닫아 혼동을 막습니다.
    setIsRegionInfoVisible(false)
    setRegionInfo(null)
    setRegionInfoState('idle')
    setRegionInfoError('')
  }

  const selectSido = (sidoCode) => {
    clearStrategyReport()
    setRegionDashboard(null)
    setRegionDashboardState('idle')
    setSigunguBoundaries(null)
    setSelectedSidoCode(sidoCode)
    // 시도가 바뀌면 기존 시군구 선택은 해제해 "해당 시도 전체" 상태로 돌아갑니다.
    setSelectedCode('')
  }

  const selectSigungu = (sigunguCode) => {
    clearStrategyReport()
    setRegionDashboard(null)
    setRegionDashboardState(sigunguCode ? 'loading' : 'idle')
    setSelectedCode(sigunguCode)
  }

  const searchRegion = (event) => {
    event.preventDefault()
    const query = regionSearch.replace(/\s+/g, '').toLowerCase()
    if (!query) return

    const sidoFeatures = sidoBoundaries?.features ?? []
    const sigunguFeatures = sigunguBoundaries?.features ?? []
    const matchedSido = sidoFeatures.find((feature) => feature.properties.region_name.replace(/\s+/g, '').toLowerCase().includes(query))
    const matchedSigungu = sigunguFeatures.find((feature) => {
      const sidoName = sidoFeatures.find((sido) => feature.properties.region_code.startsWith(sido.properties.region_code))?.properties.region_name ?? ''
      const regionName = feature.properties.region_name.replace(/\s+/g, '').toLowerCase()
      const fullName = `${sidoName}${feature.properties.region_name}`.replace(/\s+/g, '').toLowerCase()
      return regionName.includes(query) || fullName.includes(query)
    })

    if (matchedSido) {
      selectSido(matchedSido.properties.region_code)
      setRegionSearch(matchedSido.properties.region_name)
      setRegionSearchMessage('')
      return
    }
    if (matchedSigungu) {
      clearStrategyReport()
      setRegionDashboard(null)
      setRegionDashboardState('loading')
      setSelectedSidoCode(matchedSigungu.properties.region_code.slice(0, 2))
      setSelectedCode(matchedSigungu.properties.region_code)
      setRegionSearch(matchedSigungu.properties.region_name)
      setRegionSearchMessage('')
      return
    }
    setRegionSearchMessage('일치하는 도·시·군·구를 찾지 못했습니다.')
  }

  const openRegionInfo = async () => {
    setIsRegionInfoVisible(true)
    setRegionInfo(null)
    setRegionInfoState('loading')
    setRegionInfoError('')
    try {
      // 이 요청은 OpenAI를 사용하지 않고, 서버가 관광 Open API 인증키로 관광자원만 조회합니다.
      const info = await getAiRegionOpenApiInfo(selectedRegion.code, selectedRegion.name)
      setRegionInfo(info)
      setRegionInfoState('ready')
    } catch (requestError) {
      setRegionInfoError(requestError.message || '지역 상세 정보를 불러오지 못했습니다.')
      setRegionInfoState('error')
    }
  }

  const downloadStrategyProposal = async () => {
    if (!strategyReport) return

    setIsProposalDownloading(true)
    setProposalDownloadError('')
    try {
      const documentBlob = await downloadAiStrategyProposal(selectedRegion.code, { ...strategyReport, execution_scenario: executionScenario })
      const downloadUrl = URL.createObjectURL(documentBlob)
      const anchor = document.createElement('a')
      anchor.href = downloadUrl
      anchor.download = `${selectedRegion.name.replaceAll(' ', '-')}-관광-전략-기획안.docx`
      document.body.append(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(downloadUrl)
    } catch (requestError) {
      setProposalDownloadError(requestError.message)
    } finally {
      setIsProposalDownloading(false)
    }
  }

  const downloadStrategyPresentation = async () => {
    if (!strategyReport) return
    setIsPresentationDownloading(true)
    setProposalDownloadError('')
    try {
      const presentationBlob = await downloadAiStrategyPresentation(selectedRegion.code, { ...strategyReport, execution_scenario: executionScenario })
      const downloadUrl = URL.createObjectURL(presentationBlob)
      const anchor = document.createElement('a')
      anchor.href = downloadUrl
      anchor.download = `${selectedRegion.name.replaceAll(' ', '-')}-관광-전략-기획안.pptx`
      document.body.append(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(downloadUrl)
    } catch (requestError) {
      setProposalDownloadError(requestError.message)
    } finally {
      setIsPresentationDownloading(false)
    }
  }

  // 챗봇의 수정안은 자동 저장하지 않고 사용자가 적용 버튼을 눌렀을 때만 현재 보고서에 합칩니다.
  const applyAssistantReportPatch = (patch) => {
    if (!strategyReport || !patch) return
    setStrategyReport((current) => {
      const firstStrategy = current?.strategies?.[0]
      if (!firstStrategy) return current
      const updatedStrategy = {
        ...firstStrategy,
        title: patch.strategy_title || firstStrategy.title,
        problem_to_solve: patch.problem_to_solve || firstStrategy.problem_to_solve,
        comparison_analysis: patch.comparison_analysis || firstStrategy.comparison_analysis,
        solution: patch.solution || firstStrategy.solution,
        expected_effect: patch.expected_effect || firstStrategy.expected_effect,
        implementation_steps: patch.implementation_steps?.length ? patch.implementation_steps : firstStrategy.implementation_steps,
      }
      return {
        ...current,
        summary: patch.summary || current.summary,
        strategies: [updatedStrategy, ...current.strategies.slice(1)],
      }
    })
  }

  return (
    <WorkspaceShell onOpenAssistant={() => setIsAssistantOpen(true)}>
    <div className="app-shell">
      <main id="top">
        <section className="dashboard-section dashboard-section--hero" id="dashboard">
          <div className="selected-region-title">
            <div className="selected-region-heading">
              <h2>{selectedRegion.name}</h2>
            </div>
            <button type="button" className="selected-region-detail-button" onClick={openRegionInfo}>
              <Info size={16} />
              지역 정보 상세보기
            </button>
          </div>

          <div className="dashboard-top-grid dashboard-top-grid--map-first">
            <div className="dashboard-left">
              <div className="metric-grid" aria-label={`${selectedRegion.name} 핵심 지표`}>
                {dashboardMetrics.map((metric) => <MetricCard key={metric.label} {...metric} />)}
              </div>

              <article className="panel trend-panel">
                <div className="trend-panel-heading">
                  <h3 className="chart-title">방문자수 | 소비액</h3>
                </div>
                {/* 지역마다 원본 보유 기간이 달라도 Backend가 최신 12개월만 반환해 같은 차트 틀을 유지합니다. */}
                <TourismTrendChart
                  trend={regionDashboard?.monthly_trend}
                  emptyMessage={
                    regionDashboardState === 'unavailable'
                      ? '이 지역의 검증된 월간 원자료가 아직 연결되지 않았습니다.'
                      : regionDashboardState === 'idle'
                        ? '시군구를 선택하면 최근 12개월 원자료를 표시합니다.'
                        : '선택한 지역의 월간 원자료를 불러오는 중입니다.'
                  }
                />
              </article>
              <div id="diagnosis"><TourismConsumptionStayDiagnostic diagnostic={regionDashboard?.diagnostic} latestMonth={regionDashboard?.latest_month} /></div>
            </div>

            <article className="panel map-panel">
              <div className="map-selection-controls">
                <form className="map-region-search" onSubmit={searchRegion}>
                  <Search size={14} aria-hidden="true" />
                  <input
                    list="region-search-options"
                    value={regionSearch}
                    onChange={(event) => { setRegionSearch(event.target.value); setRegionSearchMessage('') }}
                    placeholder="지역을 검색하세요"
                    aria-label="지역 검색"
                  />
                  <button type="submit">검색</button>
                </form>
                <label className="region-select-label">
                  <span>시도</span>
                  <select value={selectedSidoCode} onChange={(event) => selectSido(event.target.value)}>
                    <option value="">시도 선택</option>
                    {sidoBoundaries?.features?.map((feature) => (
                      <option key={feature.properties.region_code} value={feature.properties.region_code}>{feature.properties.region_name}</option>
                    ))}
                  </select>
                  <ChevronDown size={16} aria-hidden="true" />
                </label>
                <label className="region-select-label">
                  <span>시군구</span>
                  <select
                    disabled={!selectedSidoCode}
                    value={sigunguInSelectedSido.some((feature) => feature.properties.region_code === selectedCode) ? selectedCode : ''}
                    onChange={(event) => selectSigungu(event.target.value)}
                  >
                    <option value="">시군구 전체</option>
                    {sigunguInSelectedSido.map((feature) => (
                      <option key={feature.properties.region_code} value={feature.properties.region_code}>
                        {feature.properties.display_name ?? feature.properties.region_name}
                      </option>
                    ))}
                  </select>
                  <ChevronDown size={16} aria-hidden="true" />
                </label>
                <datalist id="region-search-options">
                  {(sidoBoundaries?.features ?? []).map((feature) => <option key={feature.properties.region_code} value={feature.properties.region_name} />)}
                  {(sigunguBoundaries?.features ?? []).map((feature) => <option key={feature.properties.region_code} value={feature.properties.region_name} />)}
                </datalist>
                {regionSearchMessage && <p className="map-region-search-message" role="status">{regionSearchMessage}</p>}
              </div>
              <div className="map-frame">
                <RegionMap
                  sidoBoundaries={sidoBoundaries}
                  selectedSidoCode={selectedSidoCode}
                  selectedSigungu={selectedBoundary}
                  markerPosition={selectedMarkerPosition}
                  markerLabel={selectedRegion.name}
                  onSelectSido={selectSido}
                  onZoomChange={handleMapZoomChange}
                  isLoading={isBoundaryLoading}
                  error={boundaryError}
                />
                <span className="map-zoom-percent" aria-label={`기본 배율 대비 ${zoomPercent}% 확대`}>{zoomPercent}%</span>
              </div>
              <div className="map-caption">
                <span className="map-dot" />
                <span>
                  현재 선택: <strong>{selectedBoundary?.properties.region_name ?? selectedSido?.properties.region_name ?? '전국'}</strong>
                  {selectedBoundary ? ' · 주황색 표시' : selectedSido ? ' · 시도 전체(청록색) 표시' : ''}
                </span>
              </div>
            </article>
          </div>
        </section>

      </main>

      <div id="strategy" />
      <div id="proposal" />
      <RegionInfoModal
        visible={isRegionInfoVisible}
        onClose={() => setIsRegionInfoVisible(false)}
        region={selectedRegion}
        dashboard={regionDashboard}
        info={regionInfo}
        state={regionInfoState}
        error={regionInfoError}
      />
      <StrategyReport key={`${selectedRegion.code}-${strategyReport?.summary ?? 'loading'}`} region={selectedRegion} visible={isReportVisible} report={strategyReport} isLoading={isStrategyReportLoading} error={strategyReportError} onClose={() => setIsReportVisible(false)} onDownload={downloadStrategyProposal} onDownloadPptx={downloadStrategyPresentation} isDownloading={isProposalDownloading} isPresentationDownloading={isPresentationDownloading} downloadError={proposalDownloadError} executionScenario={executionScenario} onExecutionScenarioChange={setExecutionScenario} />
      <TourismAssistant open={isAssistantOpen} onClose={() => setIsAssistantOpen(false)} region={selectedRegion} report={strategyReport} onApplyPatch={applyAssistantReportPatch} />

      <button
        type="button"
        className={`scroll-top-button${showScrollTop ? ' is-visible' : ''}`}
        aria-label="맨 위로 이동"
        title="맨 위로"
        onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
      >
        <ChevronUp size={20} aria-hidden="true" />
      </button>

    </div>
    </WorkspaceShell>
  )
}

export default DashboardApp
