import { useEffect, useState } from 'react'
import { getAiRegionDashboard } from '../api/dashboardApi'

/** 현재 원자료 ZIP을 검증해 연결한 지역 목록입니다. */
export const SUPPORTED_TOURISM_REGIONS = [
  { code: '11680', name: '서울특별시 강남구' },
  { code: '28245', name: '인천광역시 계양구' },
  { code: '28260', name: '인천광역시 서구' },
  { code: '28720', name: '인천광역시 옹진군' },
]

export const DEFAULT_TOURISM_REGION = SUPPORTED_TOURISM_REGIONS[0]
const REGION_STORAGE_KEY = 'tour-insight-selected-region'

export function readWorkspaceRegion() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(REGION_STORAGE_KEY) || 'null')
    if (saved?.code && saved?.name) return saved
  } catch {
    // 저장값이 손상되면 검증된 기본 지역을 사용합니다.
  }
  return DEFAULT_TOURISM_REGION
}

export function saveWorkspaceRegion(region) { window.localStorage.setItem(REGION_STORAGE_KEY, JSON.stringify(region)) }

/** 선택 지역의 실제 최신 월 지표를 불러오는 공통 Hook입니다. */
export function useWorkspaceRegionData() {
  const [region, setRegion] = useState(readWorkspaceRegion)
  const [dashboard, setDashboard] = useState(null)
  const [state, setState] = useState('loading')
  useEffect(() => {
    let active = true
    getAiRegionDashboard(region.code, region.name)
      .then((data) => { if (active) { setDashboard(data); setState('ready') } })
      .catch(() => { if (active) { setDashboard(null); setState('error') } })
    return () => { active = false }
  }, [region])
  const chooseRegion = (code) => {
    const next = SUPPORTED_TOURISM_REGIONS.find((item) => item.code === code) || DEFAULT_TOURISM_REGION
    saveWorkspaceRegion(next); setDashboard(null); setState('loading'); setRegion(next)
  }
  return { region, chooseRegion, dashboard, state }
}

export function formatCompactWon(value) {
  const number = Number(value || 0)
  if (!Number.isFinite(number)) return '-'
  if (Math.abs(number) >= 100000000) return `${(number / 100000000).toFixed(1)}억 원`
  if (Math.abs(number) >= 10000) return `${Math.round(number / 10000).toLocaleString()}만 원`
  return `${Math.round(number).toLocaleString()}원`
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob); const anchor = document.createElement('a')
  anchor.href = url; anchor.download = filename; document.body.append(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url)
}

export function reportStorageKey(regionCode) { return `tour-insight-strategy-report-${regionCode}` }
const ACTIVE_STRATEGY_JOB_PREFIX = 'tour-insight-active-strategy-job-'
const SAVED_PLAN_INDEX_KEY = 'tour-insight-saved-plan-index'
const SAVED_PLAN_REPORT_PREFIX = 'tour-insight-saved-plan-report-'

function createSavedPlanId() {
  // 브라우저별 기록을 구분하는 ID입니다. 같은 지역도 생성 시점마다 별도 보관합니다.
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

function savedPlanReportKey(entryId) { return `${SAVED_PLAN_REPORT_PREFIX}${entryId}` }

/** 페이지·탭을 바꿔도 이어서 조회할 서버 작업 ID를 지역별로 보관합니다. */
export function readActiveStrategyJob(regionCode) {
  try {
    const value = JSON.parse(window.localStorage.getItem(`${ACTIVE_STRATEGY_JOB_PREFIX}${regionCode}`) || 'null')
    return value?.job_id && value?.region_code === regionCode ? value : null
  } catch {
    return null
  }
}

export function saveActiveStrategyJob(job) {
  if (!job?.job_id || !job?.region_code) return
  window.localStorage.setItem(`${ACTIVE_STRATEGY_JOB_PREFIX}${job.region_code}`, JSON.stringify(job))
}

export function clearActiveStrategyJob(regionCode) {
  window.localStorage.removeItem(`${ACTIVE_STRATEGY_JOB_PREFIX}${regionCode}`)
}

function readSavedPlanIndex() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(SAVED_PLAN_INDEX_KEY) || '[]')
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/** 게시판 행 또는 예전 지역 코드로 저장된 기획안 본문을 읽습니다. */
export function readSavedReport(reference) {
  try {
    if (reference && typeof reference === 'object' && reference.reportKey) {
      return JSON.parse(window.localStorage.getItem(reference.reportKey) || 'null')
    }
    const regionCode = typeof reference === 'string' ? reference : reference?.regionCode
    return JSON.parse(window.localStorage.getItem(reportStorageKey(regionCode)) || 'null')
  } catch {
    return null
  }
}

/**
 * 생성한 기획안은 지역별 최신본과 게시판용 개별 본문을 함께 보관합니다.
 * __savedEntryId가 있으면 AI 챗봇으로 수정한 현재 기록만 갱신하고,
 * 없으면 새 행을 추가해 이전 결과를 보존합니다.
 */
export function saveReport(regionCode, report) {
  const entryId = report?.__savedEntryId || createSavedPlanId()
  const storedReport = { ...report, __savedEntryId: entryId }
  window.localStorage.setItem(reportStorageKey(regionCode), JSON.stringify(storedReport))
  window.localStorage.setItem(savedPlanReportKey(entryId), JSON.stringify(storedReport))
  const strategy = storedReport?.strategies?.[0]
  const entry = {
    entryId,
    reportKey: savedPlanReportKey(entryId),
    regionCode,
    regionName: storedReport?.region_name || DEFAULT_TOURISM_REGION.name,
    title: strategy?.title || '관광 전략 기획안',
    summary: storedReport?.summary || '',
    savedAt: new Date().toISOString(),
  }
  const previous = readSavedPlanIndex().filter((item) => item.entryId !== entryId)
  window.localStorage.setItem(SAVED_PLAN_INDEX_KEY, JSON.stringify([entry, ...previous]))
  return storedReport
}

/** 이전 버전에서 저장된 지역별 최신 기획서도 게시판에서 복구해 보여 줍니다. */
export function listSavedReports() {
  const indexed = readSavedPlanIndex()
  const knownCodes = new Set(indexed.map((item) => item.regionCode))
  const recovered = []
  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index)
    if (!key?.startsWith('tour-insight-strategy-report-')) continue
    const regionCode = key.replace('tour-insight-strategy-report-', '')
    if (knownCodes.has(regionCode)) continue
    const report = readSavedReport(regionCode)
    if (!report) continue
    recovered.push({ regionCode, regionName: report.region_name || '선택 지역', title: report.strategies?.[0]?.title || '관광 전략 기획안', summary: report.summary || '', savedAt: new Date().toISOString() })
  }
  return [...indexed, ...recovered].sort((first, second) => String(second.savedAt).localeCompare(String(first.savedAt)))
}
