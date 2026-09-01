"""선택 지역 원자료를 근거로 OpenAI 전략 보고서를 생성하는 테스트 AI 서버입니다."""

from __future__ import annotations

import asyncio
from datetime import date
from io import BytesIO
import json
import logging
import os
import re
from uuid import uuid4
from pathlib import Path
from typing import Any, Literal

import httpx
from dotenv import dotenv_values, load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .openai_responses import OpenAIResponseError, check_openai_readiness
from .offline_sample_report import build_offline_sample_report
from .proposal_document import create_strategy_proposal_document
from .proposal_presentation import create_strategy_proposal_presentation
from .raw_data_repository import read_region_tables
from .agents.report_orchestrator import orchestrate_strategy_report
from .agents.chat_assistant_agent import TourismChatAssistantAgent
from .agents.ml_learning_assistant_agent import MlLearningAssistantAgent
from .agents.project_learning_assistant_agent import ProjectLearningAssistantAgent
from .tourism_open_api import TourismOpenApiClient
from .planning_brief import PlanningBrief, brief_fingerprint, extract_brief_reference, without_reference_text
from .project_learning_catalog import ProjectLearningCatalog, build_project_learning_catalog
from .strategy_store import (
    initialize_strategy_store,
    list_interrupted_strategy_jobs,
    list_strategy_reports,
    read_document,
    read_strategy_job,
    read_strategy_report,
    save_strategy_job,
    save_strategy_report,
    update_strategy_job_state,
    write_document,
)
from ..ml.gangnam_data import load_latest_consumption_shares
from ..ml.region_service import predict_region_demand
from ..ml.region_registry import get_region_pipeline
from ..ml.region_catalog import list_region_data_catalog
from ..ml.planning_evidence import PlanningMlEvidence, build_planning_ml_evidence
from ..ml.learning_catalog import MlLearningCatalog, build_ml_learning_catalog

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / '.env', override=False)
# 실행 환경변수를 우선하고, 없는 값만 프로젝트 루트 .env에서 읽습니다.
ENV_VALUES = {**dotenv_values(PROJECT_ROOT / '.env'), **os.environ}
RAW_DATA_DIRECTORY = PROJECT_ROOT / 'data' / 'raw'
LOGGER = logging.getLogger(__name__)

app = FastAPI(title='STAY-UP AI Server', version='0.1.0')
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173', 'http://localhost:5175', 'http://127.0.0.1:5175', 'http://localhost:5176', 'http://127.0.0.1:5176'], allow_methods=['POST', 'GET', 'PUT'], allow_headers=['*'])


@app.on_event('startup')
async def initialize_mysql_strategy_store() -> None:
    """MySQL이 준비된 경우에만 기획안 저장 테이블을 생성합니다.

    DB 설정이 빠져도 지도·대시보드처럼 저장과 무관한 화면은 계속 사용할 수 있도록
    서버 시작 자체는 막지 않고, 저장 기능에서 명확한 오류를 안내합니다.
    """
    try:
        initialize_strategy_store()
        # 프로세스 재시작 전에 실행 중이던 작업은 MySQL 요청을 읽어 다시 예약합니다.
        # 첨부문서 본문은 저장하지 않으므로 첨부가 있던 작업은 안전하게 실패 처리합니다.
        for stored_job in list_interrupted_strategy_jobs():
            job_id = stored_job['job_id']
            if stored_job.get('had_transient_references'):
                message = 'AI 서버가 재시작되어 첨부문서가 있던 작업은 자동 재개할 수 없습니다. 다시 생성해 주세요.'
                update_strategy_job_state(job_id, 'failed', message, 'TRANSIENT_REFERENCE_LOST')
                STRATEGY_REPORT_JOBS[job_id] = {
                    **stored_job, 'status': 'failed', 'message': message, 'error': 'TRANSIENT_REFERENCE_LOST',
                }
                continue
            try:
                request = ReportRequest.model_validate(stored_job.get('request') or {})
            except ValueError:
                message = '저장된 작업 요청을 복구하지 못했습니다. 기획안을 다시 생성해 주세요.'
                update_strategy_job_state(job_id, 'failed', message, 'INVALID_PERSISTED_REQUEST')
                continue
            STRATEGY_REPORT_JOBS[job_id] = {
                'region_code': stored_job['region_code'], 'region_name': stored_job['region_name'],
                'status': 'queued', 'message': 'AI 서버 재시작 후 작업을 다시 이어갑니다.', 'error': '',
            }
            update_strategy_job_state(job_id, 'queued', 'AI 서버 재시작 후 작업을 다시 이어갑니다.')
            asyncio.create_task(_run_strategy_report_job(job_id, stored_job['region_code'], request))
    except Exception as exc:
        LOGGER.warning('MySQL strategy store is unavailable: %s', type(exc).__name__)


class ReportRequest(BaseModel):
    """선택 지역의 검증된 원자료로 종합 보고서를 생성합니다."""

    region_name: str
    planning_brief: PlanningBrief | None = None


class RegionOpenApiResource(BaseModel):
    """관광 Open API에서 온 관광자원 한 건을 화면에 안전하게 전달합니다."""

    title: str
    address: str = ''
    image_url: str = ''
    content_type: str = '관광자원'
    source_url: str


class RegionOpenApiInfoResponse(BaseModel):
    """지역 상세 팝업용 Open API 응답입니다.

    월간 방문·소비 수치는 이 응답에서 만들지 않습니다. 해당 수치는 별도 대시보드
    원자료 응답이 담당하고, 여기서는 관광자원 정보와 API 조회 상태만 제공합니다.
    """

    region_code: str
    region_name: str
    source_name: str
    source_url: str
    status: Literal['ready', 'empty', 'unavailable', 'not_configured']
    message: str
    resources: list[RegionOpenApiResource] = Field(default_factory=list)
    category_summary: list[dict[str, Any]] = Field(default_factory=list)


class ObservedFinding(BaseModel):
    metric: str
    value: str
    interpretation: str
    source: str


class ImplementationStep(BaseModel):
    """기획안에서 실제로 완료 여부를 확인할 수 있는 작업과 산출물 한 쌍입니다."""

    step: int
    schedule: str
    task: str
    deliverable: str


class Strategy(BaseModel):
    priority: int
    timeframe: str
    title: str
    problem_to_solve: str
    comparison_analysis: str
    solution: str
    implementation_steps: list[ImplementationStep]
    expected_effect: str
    budget: str
    kpi: str
    evidence: str
    visual_asset_source_ids: list[str] = Field(default_factory=list)


class MonthlyTrend(BaseModel):
    """보고서의 그래프는 LLM이 만든 값이 아니라 원본 ZIP에서 재계산한 값만 사용합니다."""

    month: str
    visitor_index: float | None
    spending_index: float | None
    visitors: int | None
    spending_krw: int | None
    # 원자료와 ML 예측 막대를 화면에서 확실히 구분하기 위한 표시용 값입니다.
    is_forecast: bool = False
    # 실제 데이터나 예측값이 아닌 오늘 위치 표시용 빈 월입니다.
    is_current_month: bool = False


class ExecutionScenario(BaseModel):
    """담당자가 화면에서 선택한 검토용 실행 목표입니다.

    정책 인과효과나 ML 예측값이 아니라 최근 월 원자료에 단순 환산하는
    목표 비교값이며, Word 문서에도 같은 기준을 전달합니다.
    """

    visitor_target_pct: float = Field(default=5, ge=0, le=20)
    spending_target_pct: float = Field(default=8, ge=0, le=30)


class ReportResponse(BaseModel):
    """React가 표로 바로 렌더링할 수 있는, 검증된 구조의 AI 응답입니다."""

    summary: str
    region_name: str
    period: str
    metrics_count: int
    observed_findings: list[ObservedFinding]
    monthly_trend: list[MonthlyTrend]
    strategies: list[Strategy]
    # 조사 공백은 내부 evidence pack·검수에만 남기고, 담당자 화면에는 출처 목록만 표시합니다.
    limitations: list[str] = Field(default_factory=list)
    quality_review: dict[str, Any] | None = None
    evidence_sources: list[dict[str, Any]] = Field(default_factory=list)
    research_gaps: list[str] = Field(default_factory=list)
    agent_trace: list[dict[str, Any]] = Field(default_factory=list)
    execution_scenario: ExecutionScenario | None = None
    generation_mode: Literal['openai', 'offline_sample'] = 'openai'
    # 생성 당시 조건을 고정 보관해 이후 초안 수정이 과거 보고서를 바꾸지 않게 합니다.
    planning_brief: PlanningBrief | None = None
    planning_brief_fingerprint: str = ''
    # AI가 새로 계산하지 않은, 생성 당시 모델 예측·검증 결과를 저장 보고서에도 보존합니다.
    ml_analysis: PlanningMlEvidence | None = None


class StrategyReportJobResponse(BaseModel):
    """페이지 이동과 무관하게 진행되는 전략기획 생성 작업의 상태입니다."""

    job_id: str
    region_code: str
    region_name: str
    status: Literal['queued', 'running', 'completed', 'failed']
    message: str
    report: ReportResponse | None = None
    error: str = ''


# 브라우저 요청과 별개로 실행되는 개발용 작업 저장소입니다.
# 완료 결과는 프런트엔드가 localStorage의 저장 기획서 목록으로 옮겨 보관합니다.
STRATEGY_REPORT_JOBS: dict[str, dict[str, Any]] = {}


class AssistantChatMessage(BaseModel):
    """브라우저가 전달하는 최근 대화 한 건입니다."""

    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=3000)


class AssistantChatRequest(BaseModel):
    """선택 지역 분석과 현재 기획안을 기준으로 묻는 챗봇 요청입니다."""

    region_name: str
    question: str = Field(min_length=1, max_length=3000)
    history: list[AssistantChatMessage] = Field(default_factory=list, max_length=8)
    current_report: dict[str, Any] | None = None
    enable_web_search: bool = True
    planning_brief: PlanningBrief | None = None


class AssistantSource(BaseModel):
    title: str
    url: str
    published_or_updated_at: str = ''


class AssistantChatResponse(BaseModel):
    answer: str
    mode: Literal['explain', 'research', 'revise']
    key_points: list[str] = Field(default_factory=list)
    sources: list[AssistantSource] = Field(default_factory=list)
    report_patch: dict[str, Any] | None = None
    generation_mode: Literal['openai', 'offline_sample'] = 'openai'


class MlLearningChatRequest(BaseModel):
    """학습 페이지에서 선택 지역의 ML 구현에 관해 묻는 요청입니다."""

    question: str = Field(min_length=1, max_length=2000)
    history: list[AssistantChatMessage] = Field(default_factory=list, max_length=6)


class MlLearningChatResponse(BaseModel):
    """ML 튜터 답변은 화면에서 항목별로 읽기 쉬운 고정 구조를 사용합니다."""

    answer: str
    key_points: list[str] = Field(default_factory=list, max_length=3)
    related_modules: list[str] = Field(default_factory=list, max_length=3)
    caution: str = ''
    generation_mode: Literal['openai'] = 'openai'


class ProjectLearningChatRequest(BaseModel):
    """OpenAI·React 구조 학습 페이지의 질문입니다."""
    question: str = Field(min_length=1, max_length=2000)
    history: list[AssistantChatMessage] = Field(default_factory=list, max_length=6)


class ProjectLearningChatResponse(BaseModel):
    """구현 설명과 관련 파일을 분리한 학습 답변입니다."""
    answer: str
    key_points: list[str] = Field(default_factory=list, max_length=3)
    related_files: list[str] = Field(default_factory=list, max_length=3)
    caution: str = ''
    generation_mode: Literal['openai'] = 'openai'


class LearningAssistantStatusResponse(BaseModel):
    """학습 챗봇 배지에 필요한 최소 연결 상태만 브라우저에 전달합니다."""

    status: Literal['active', 'inactive']
    message: str


class DashboardMetric(BaseModel):
    """상단 요약 카드에 표시할 검증된 월간 수치입니다."""

    label: str
    value: str
    detail: str
    change_label: str
    change_value: str
    change_direction: Literal['up', 'down', 'same']
    accent: Literal['aqua', 'blue', 'purple']


class ConsumptionCategory(BaseModel):
    """선택 지역의 최신 월 외지인 관광소비 업종 비중입니다."""

    name: str
    share: float
    amount_krw: int


class TourismDiagnostic(BaseModel):
    """그래프 아래에서 소비 구조와 체류 전환을 함께 읽기 위한 원자료 요약입니다."""

    consumption_categories: list[ConsumptionCategory]
    lodging_rate: float
    average_lodging_nights: float
    lodging_nights_change: float
    # 업종별 값은 별도 업종 모델이 아니라 최신 관측 비중을 적용한 예상 분포일 수 있습니다.
    forecast_month: str = ''
    is_forecast: bool = False
    # 3개월 ML 예측 소비액의 평균. 업종별 분포 금액을 계산할 때 사용하는 기준값입니다.
    forecast_average_spending_krw: int | None = None
    assumption: str = ''


class ForecastInformation(BaseModel):
    """대시보드가 모델 예측임을 숨기지 않고 표시하기 위한 최소 메타데이터입니다."""

    model_version: str
    test_period: str
    visitor_mae: float
    spending_mae_krw: float
    limitation: str


class DashboardResponse(BaseModel):
    """선택 지역 원본을 읽기 전용으로 계산한 React 대시보드 테스트 응답입니다."""

    region_name: str
    latest_month: str
    source: str
    metrics: list[DashboardMetric]
    monthly_trend: list[MonthlyTrend]
    diagnostic: TourismDiagnostic
    forecast: ForecastInformation | None = None


class SidoComparisonItem(BaseModel):
    """같은 시도의 시군구를 동일한 최근 3개월로 비교한 원자료 평균입니다."""

    region_name: str
    visitors: int
    spending_krw: int
    lodging_rate: float
    average_lodging_nights: float


class SidoComparisonResponse(BaseModel):
    """시도 안에서 원본이 준비된 시군구만 비교하는 응답입니다."""

    sido_name: str
    period: str
    source: str
    regions: list[SidoComparisonItem]


def _normalize_region_name(value: str) -> str:
    return re.sub(r'\s+', '', value)


def _find_region_directory(region_name: str) -> Path:
    """브라우저의 지역명은 미리 발견한 원본 폴더와만 대응해 경로 주입을 막습니다."""
    requested_name = _normalize_region_name(region_name)
    # 전국 확장 카탈로그에 등록된 단일 ZIP·CSV 경로를 먼저 사용합니다.
    # 강남구처럼 시군구 하위 폴더 없이 ZIP 한 개로 받은 원본도 같은 보고서 흐름에 연결됩니다.
    try:
        for entry in list_region_data_catalog(enabled_only=True):
            if _normalize_region_name(entry.region_name) == requested_name and entry.raw_path.exists():
                return entry.raw_path
    except (FileNotFoundError, ValueError):
        pass
    for sido_directory in RAW_DATA_DIRECTORY.iterdir() if RAW_DATA_DIRECTORY.exists() else []:
        if not sido_directory.is_dir():
            continue
        for sigungu_directory in sido_directory.iterdir():
            if not sigungu_directory.is_dir():
                continue
            full_name = _normalize_region_name(f'{sido_directory.name} {sigungu_directory.name}')
            if full_name == requested_name:
                return sigungu_directory
    raise FileNotFoundError(f'{region_name} 원본 데이터 폴더를 찾지 못했습니다.')


def _find_sido_directory(sido_name: str) -> Path:
    """원본 폴더에 실제로 있는 시도만 비교 대상으로 허용합니다."""
    requested_name = _normalize_region_name(sido_name)
    for sido_directory in RAW_DATA_DIRECTORY.iterdir() if RAW_DATA_DIRECTORY.exists() else []:
        if sido_directory.is_dir() and _normalize_region_name(sido_directory.name) == requested_name:
            return sido_directory
    raise FileNotFoundError(f'{sido_name} 원본 데이터 폴더를 찾지 못했습니다.')


def _read_tables(region_directory: Path) -> dict[str, list[dict[str, str]]]:
    """호출부 호환용 함수입니다. 실제 읽기·변경 감지 캐시는 전용 Repository가 담당합니다."""
    return read_region_tables(region_directory)


def _find_table(tables: dict[str, list[dict[str, str]]], name_part: str) -> list[dict[str, str]]:
    matched_rows: list[dict[str, str]] = []
    for file_name, rows in tables.items():
        # 전국 비교 표는 같은 단어를 포함하지만 지역의 실제 월간 수치 표가 아니므로 제외합니다.
        if name_part in file_name and '전국 대비' not in file_name:
            matched_rows.extend(rows)
    if matched_rows:
        unique_rows: dict[tuple[tuple[str, str], ...], dict[str, str]] = {}
        for row in matched_rows:
            unique_rows[tuple(sorted(row.items()))] = row
        return list(unique_rows.values())
    raise KeyError(f'필수 원본 표를 찾지 못했습니다: {name_part}')


def _number(value: str) -> float:
    return float(value.replace(',', ''))


def _month_value(row: dict[str, str]) -> str:
    for key, value in row.items():
        if '기준' in key and '월' in key:
            matched = re.search(r'(20\d{4})', value)
            if matched:
                return matched.group(1)
    return ''


def _latest(rows: list[dict[str, str]], condition: Any = None) -> dict[str, str]:
    filtered = [row for row in rows if (condition(row) if condition else True) and _month_value(row)]
    if not filtered:
        raise ValueError('기준년월이 있는 원본 행을 찾지 못했습니다.')
    return max(filtered, key=_month_value)


def _value_by_contains(row: dict[str, str], name_part: str) -> str:
    for key, value in row.items():
        if name_part in key:
            return value
    raise KeyError(f'열을 찾지 못했습니다: {name_part}')


def _monthly_values(rows: list[dict[str, str]], value_column: str, condition: Any = None) -> dict[str, float]:
    """기준년월별 값을 읽어, 그래프에 쓸 공통 월간 시계열을 만듭니다."""
    values: dict[str, float] = {}
    for row in rows:
        month = _month_value(row)
        if not month or (condition and not condition(row)):
            continue
        values[month] = _number(_value_by_contains(row, value_column))
    return values


def _build_monthly_trend(visitor_rows: list[dict[str, str]], spending_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """모든 지원 지역에서 동일하게 최신 12개월 방문자·관광소비 추세를 만듭니다."""
    visitor_by_month = _monthly_values(visitor_rows, '방문자수')
    spending_by_month = _monthly_values(spending_rows, '소비액(천원)', lambda row: row.get('업종대분류명') == '전체')
    # 지역별로 보유한 ZIP 기간이 달라도 최초 대시보드의 틀과 X축 개수를 같게 유지합니다.
    # 3년치 원본을 삭제하는 것이 아니라, 화면과 AI 분석 입력에는 가장 최근 12개월만 사용합니다.
    common_months = sorted(set(visitor_by_month) & set(spending_by_month))[-12:]
    if not common_months:
        raise ValueError('방문자와 관광소비의 공통 기준년월을 찾지 못했습니다.')
    base_visitor = visitor_by_month[common_months[0]]
    base_spending = spending_by_month[common_months[0]]
    return [
        {
            'month': f'{month[:4]}.{month[4:]}',
            'visitor_index': round(visitor_by_month[month] / base_visitor * 100, 1),
            'spending_index': round(spending_by_month[month] / base_spending * 100, 1),
            'visitors': round(visitor_by_month[month]),
            'spending_krw': round(spending_by_month[month] * 1000),
        }
        for month in common_months
    ]


def _registered_region_history(region_name: str) -> tuple[str, Any] | None:
    """등록 ML 지역이면 모델 학습과 동일한 최신 공식 월별 표를 반환합니다.

    일반 원본 묶음과 최신월 보완 ZIP을 따로 읽으면 AI 기획안의 관측 기준월과
    ML 기준월이 달라질 수 있습니다. 등록 지역은 학습 전처리 함수를 재사용해
    화면·관측 근거·ML 전망의 마지막 확정월을 맞춥니다.
    """
    requested_name = _normalize_region_name(region_name)
    for entry in list_region_data_catalog(enabled_only=True):
        if _normalize_region_name(entry.region_name) != requested_name:
            continue
        try:
            pipeline = get_region_pipeline(entry.region_code)
        except ValueError:
            return None
        if pipeline.load_history is None:
            return None
        history = pipeline.load_history()
        if history.empty:
            raise ValueError(f'{region_name} 등록 ML 원자료에 월별 관측값이 없습니다.')
        return entry.region_code, history
    return None


def _monthly_trend_from_registered_history(history: Any) -> list[dict[str, Any]]:
    """등록 지역의 공통 Target 표에서 최근 12개월 방문·소비 추세를 만듭니다."""
    records = history.tail(12).to_dict(orient='records')
    if not records:
        raise ValueError('등록 ML 원자료의 월별 추세가 비어 있습니다.')
    base_visitors = float(records[0]['visitors'])
    base_spending = float(records[0]['spending_krw'])
    if base_visitors <= 0 or base_spending <= 0:
        raise ValueError('등록 ML 원자료의 추세 기준값은 0보다 커야 합니다.')
    return [
        {
            'month': f"{str(row['year_month'])[:4]}.{str(row['year_month'])[4:]}",
            'visitor_index': round(float(row['visitors']) / base_visitors * 100, 1),
            'spending_index': round(float(row['spending_krw']) / base_spending * 100, 1),
            'visitors': round(float(row['visitors'])),
            'spending_krw': round(float(row['spending_krw'])),
        }
        for row in records
    ]


def _percent_change(current: float, previous: float) -> float:
    """직전 월이 0이 아닌 경우에만 전월 대비 증감률을 계산합니다."""
    if previous == 0:
        raise ValueError('전월 값이 0이라 증감률을 계산할 수 없습니다.')
    return (current - previous) / previous * 100


def _change_direction(value: float) -> Literal['up', 'down', 'same']:
    if value > 0.05:
        return 'up'
    if value < -0.05:
        return 'down'
    return 'same'


def _next_calendar_month() -> str:
    """화면의 대표 예측월을 현재 달의 다음 달로 정합니다."""
    current = date.today()
    year, month = current.year, current.month + 1
    if month == 13:
        year, month = year + 1, 1
    return f'{year}{month:02d}'


def _months_between(start_month: str, end_month: str) -> int:
    """YYYYMM 두 월 사이 간격을 구해 필요한 재귀 예측 길이를 계산합니다."""
    return (int(end_month[:4]) - int(start_month[:4])) * 12 + int(end_month[4:]) - int(start_month[4:])


def _select_display_forecasts(forecasts: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """차트의 전체 예측 중 현재 시점의 다음 달을 카드 대표값으로 고릅니다."""
    target_month = _next_calendar_month()
    for index, forecast in enumerate(forecasts):
        if forecast['month'] == target_month:
            return forecasts[index:index + 3], forecasts[index - 1] if index else None
    # 원자료 갱신이 늦어 현재 달보다 예측 범위가 과거일 때는, 가장 가까운 첫 예측을 보여 줍니다.
    return forecasts[:3], None


def _build_registered_ml_dashboard(region_code: str, region_name: str) -> DashboardResponse:
    """등록·검증된 어느 지역이든 최근 관측값과 저장 ML 전망을 같은 대시보드로 변환합니다.

    지도와 화면 구조는 지역에 따라 복사하지 않습니다. 지역별 차이는 등록표의 원자료 함수와
    Joblib 산출물뿐이며, 원자료 검증을 통과하지 않은 지역은 이 함수로 들어올 수 없습니다.
    """
    pipeline = get_region_pipeline(region_code)
    if pipeline.region_name != region_name or pipeline.load_history is None:
        raise ValueError('ML_REGION_MISMATCH: 등록 모델과 요청 지역이 다릅니다.')
    target_month = _next_calendar_month()
    history = pipeline.load_history()
    latest_observed_month = str(history['year_month'].iloc[-1])
    # 최신 원자료가 늦게 공개돼도, 다음 달부터 3개월을 끊김 없이 보여 줄 만큼만 재귀 예측합니다.
    required_horizon = max(4, _months_between(latest_observed_month, target_month) + 2)
    forecast_result = predict_region_demand(region_code, required_horizon)
    visible_forecasts, previous_forecast = _select_display_forecasts(forecast_result['forecasts'])
    if not visible_forecasts:
        raise ValueError('현재 달 다음의 예측값을 만들지 못했습니다.')
    next_forecast = visible_forecasts[0]
    latest_visitors = forecast_result['latest_observed_visitors']
    latest_spending = forecast_result['latest_observed_spending_krw']
    comparison_visitors = previous_forecast['visitors'] if previous_forecast else latest_visitors
    comparison_spending = previous_forecast['spending_krw'] if previous_forecast else latest_spending
    comparison_lodging = previous_forecast['lodging_nights'] if previous_forecast else forecast_result['latest_observed_lodging_nights']
    visitor_change = _percent_change(next_forecast['visitors'], comparison_visitors)
    spending_change = _percent_change(next_forecast['spending_krw'], comparison_spending)
    next_month_label = f"{int(next_forecast['month'][4:])}월"
    latest_lodging_rate = float(forecast_result['latest_observed_metrics']['lodging_rate_pct'])
    lodging_nights_change = next_forecast['lodging_nights'] - comparison_lodging
    comparison_label = (
        f"{int(previous_forecast['month'][4:])}월 예상 대비"
        if previous_forecast else f"{int(latest_observed_month[4:])}월 대비"
    )

    # 공식 원자료의 마지막 확정월은 7월이므로 8월은 모델이 계산한 현재월 추정값입니다.
    # 화면은 6·7월 실제값과 8·9·10월 예측값을 보여 주어 오늘 날짜(8월)가 축 안에 들어오게 합니다.
    forecast_rows = ([previous_forecast] if previous_forecast else []) + visible_forecasts[:2]
    trend_rows = [*forecast_result['recent_actuals'][-3:], *forecast_rows]
    first_visitor = trend_rows[0]['visitors']
    first_spending = trend_rows[0]['spending_krw']
    trend = [
        MonthlyTrend(
            month=f"{row['month'][:4]}.{row['month'][4:]}",
            visitor_index=round(row['visitors'] / first_visitor * 100, 1) if row['visitors'] is not None else None,
            spending_index=round(row['spending_krw'] / first_spending * 100, 1) if row['spending_krw'] is not None else None,
            visitors=row['visitors'],
            spending_krw=row['spending_krw'],
            is_forecast=bool(row['is_forecast']),
            is_current_month=bool(row.get('is_current_month')),
        )
        for row in trend_rows
    ]

    # 업종별 데이터는 별도 ML Target이 아닙니다. 총소비액의 향후 3개월 ML 평균에, 같은 지역
    # 원자료에서 확인한 최신 업종 비중만 적용합니다. 이 역할 분리를 모든 등록 지역에 동일하게 적용합니다.
    forecast_average_spending_krw = round(sum(row['spending_krw'] for row in visible_forecasts) / len(visible_forecasts))
    try:
        observed_categories = build_region_dashboard(region_name).diagnostic.consumption_categories
    except FileNotFoundError:
        # 강남구 초기 ZIP 묶음은 일반 대시보드가 요구하는 연인원 표를 포함하지 않습니다.
        # 해당 지역의 검증된 최신 소비 표에서만 비중을 읽는 호환 경로를 남깁니다.
        if region_code != '11680':
            raise
        observed_categories = [
            ConsumptionCategory(name=str(row['name']), share=float(row['share']), amount_krw=0)
            for row in load_latest_consumption_shares()[:4]
        ]
    consumption_categories = [
        ConsumptionCategory(
            name=str(category.name),
            share=float(category.share),
            amount_krw=round(forecast_average_spending_krw * float(category.share) / 100),
        )
        for category in observed_categories[:4]
    ]
    metadata = forecast_result['model']
    return DashboardResponse(
        region_name=region_name,
        latest_month=f"{next_forecast['month'][:4]}-{next_forecast['month'][4:]}",
        source=f'한국관광 데이터랩 {region_name} 공식 다운로드 원본 + 저장된 ML 예측 모델',
        metrics=[
            DashboardMetric(
                label=f'{next_month_label} 예상 방문자 수',
                value=f"{next_forecast['visitors']:,.0f}명",
                detail='',
                change_label=comparison_label,
                change_value=f'{visitor_change:+.1f}%',
                change_direction=_change_direction(visitor_change),
                accent='aqua',
            ),
            DashboardMetric(
                label=f'{next_month_label} 예상 관광소비액',
                value=f"₩{next_forecast['spending_krw'] / 100_000_000:,.0f}억",
                detail='',
                change_label=comparison_label,
                change_value=f'{spending_change:+.1f}%',
                change_direction=_change_direction(spending_change),
                accent='blue',
            ),
            DashboardMetric(
                label=f'{next_month_label} 예상 평균 숙박일수',
                value=f"{next_forecast['lodging_nights']:.2f}일",
                detail='',
                change_label=comparison_label,
                change_value=f'{lodging_nights_change:+.2f}일',
                change_direction='up' if lodging_nights_change > 0 else 'down' if lodging_nights_change < 0 else 'same',
                accent='purple',
            ),
        ],
        monthly_trend=trend,
        diagnostic=TourismDiagnostic(
            consumption_categories=consumption_categories,
            lodging_rate=latest_lodging_rate,
            average_lodging_nights=next_forecast['lodging_nights'],
            lodging_nights_change=lodging_nights_change,
            forecast_month=next_forecast['month'],
            is_forecast=True,
            forecast_average_spending_krw=forecast_average_spending_krw,
            assumption='향후 3개월 전체 관광소비액 ML 예측 평균값에 최신 업종 비중을 적용한 예상 분포',
        ),
        forecast=ForecastInformation(
            model_version=metadata['version'],
            test_period=metadata['test_period'],
            visitor_mae=float(metadata['evaluation']['visitors']['selected_model_metrics']['mae']),
            spending_mae_krw=float(metadata['evaluation']['spending_krw']['selected_model_metrics']['mae']),
            limitation=metadata['limitations'][0],
        ),
    )


def _build_gangnam_ml_dashboard() -> DashboardResponse:
    """기존 테스트·호출부 호환용 강남구 래퍼입니다."""
    return _build_registered_ml_dashboard('11680', '서울특별시 강남구')


def build_sido_comparison(sido_name: str) -> SidoComparisonResponse:
    """원본이 있는 시군구의 공통 최근 3개월 평균을 계산해 비교합니다."""
    sido_directory = _find_sido_directory(sido_name)
    regional_values: list[tuple[str, dict[str, float], dict[str, float], dict[str, float], dict[str, float]]] = []

    for sigungu_directory in sido_directory.iterdir():
        if not sigungu_directory.is_dir():
            continue
        try:
            tables = _read_tables(sigungu_directory)
            stay_rows = _find_table(tables, '순 방문자 수 및 숙박 비율')
            spending_rows = _find_table(tables, '관광소비 추이_외지인')
            lodging_nights_rows = _find_table(tables, '평균 숙박일')
            visitors_by_month = _monthly_values(stay_rows, '순 방문자수')
            spending_by_month = _monthly_values(
                spending_rows,
                '소비액(천원)',
                lambda row: row.get('업종대분류명') == '전체',
            )
            lodging_rate_by_month = _monthly_values(stay_rows, '숙박자 비율')
            lodging_nights_by_month = _monthly_values(lodging_nights_rows, '평균 숙박일수')
            shared_months = set(visitors_by_month) & set(spending_by_month) & set(lodging_rate_by_month) & set(lodging_nights_by_month)
            if shared_months:
                regional_values.append((sigungu_directory.name, visitors_by_month, spending_by_month, lodging_rate_by_month, lodging_nights_by_month))
        except (FileNotFoundError, KeyError, ValueError):
            # 원본 표가 불완전한 시군구는 비교 차트에서 제외하며, 수치를 임의로 채우지 않습니다.
            continue

    if len(regional_values) < 2:
        raise ValueError('비교 가능한 시군구 원본이 2개 이상 필요합니다.')

    common_months = set(regional_values[0][1]) & set(regional_values[0][2])
    common_months &= set(regional_values[0][3]) & set(regional_values[0][4])
    for _, visitors_by_month, spending_by_month, lodging_rate_by_month, lodging_nights_by_month in regional_values[1:]:
        common_months &= set(visitors_by_month) & set(spending_by_month) & set(lodging_rate_by_month) & set(lodging_nights_by_month)
    comparison_months = sorted(common_months)[-3:]
    if len(comparison_months) < 3:
        raise ValueError('최근 3개월 평균을 계산할 공통 기준년월이 부족합니다.')

    return SidoComparisonResponse(
        sido_name=sido_name,
        period=f'{comparison_months[0][:4]}.{comparison_months[0][4:]}~{comparison_months[-1][:4]}.{comparison_months[-1][4:]}',
        source=f'한국관광 데이터랩 {sido_name} 공식 다운로드 원본',
        regions=[
            SidoComparisonItem(
                region_name=region_name,
                visitors=round(sum(visitors_by_month[month] for month in comparison_months) / len(comparison_months)),
                spending_krw=round(sum(spending_by_month[month] for month in comparison_months) / len(comparison_months) * 1000),
                lodging_rate=round(sum(lodging_rate_by_month[month] for month in comparison_months) / len(comparison_months), 1),
                average_lodging_nights=round(sum(lodging_nights_by_month[month] for month in comparison_months) / len(comparison_months), 2),
            )
            for region_name, visitors_by_month, spending_by_month, lodging_rate_by_month, lodging_nights_by_month in regional_values
        ],
    )


def build_region_dashboard(region_name: str) -> DashboardResponse:
    """OpenAI를 호출하지 않고 선택 지역 원본에서 최신 월·전월 비교 카드를 계산합니다."""
    tables = _read_tables(_find_region_directory(region_name))
    visitor_rows = _find_table(tables, '방문자 수(연인원) 추이')
    # 현지인 소비가 섞일 수 있는 '내국인' 전체 대신, 외지인 관광소비 추이를 사용합니다.
    # 방문·숙박 지표와 동일하게 관광객 유입 관점에서 비교하기 위함입니다.
    spending_rows = _find_table(tables, '관광소비 추이_외지인')
    stay_rows = _find_table(tables, '순 방문자 수 및 숙박 비율')
    lodging_nights_rows = _find_table(tables, '평균 숙박일')
    trend = _build_monthly_trend(visitor_rows, spending_rows)
    if len(trend) < 2:
        raise ValueError('전월 대비 계산에 필요한 월간 원본 행이 부족합니다.')

    latest, previous = trend[-1], trend[-2]
    latest_key = latest['month'].replace('.', '')
    stay_by_month = _monthly_values(stay_rows, '숙박자 비율')
    unique_visitors_by_month = _monthly_values(stay_rows, '순 방문자수')
    if latest_key not in stay_by_month or latest_key not in unique_visitors_by_month:
        raise ValueError('최신 기준월의 순 방문자 수 또는 숙박 방문 비율을 찾지 못했습니다.')
    stay_months = sorted(stay_by_month)
    latest_stay_index = stay_months.index(latest_key)
    if latest_stay_index == 0:
        raise ValueError('숙박 방문 비율의 전월 값이 부족합니다.')
    previous_key = stay_months[latest_stay_index - 1]
    if previous_key not in unique_visitors_by_month:
        raise ValueError('전월 순 방문자 수를 찾지 못했습니다.')
    previous_stay = stay_by_month[previous_key]
    latest_stay = stay_by_month[latest_key]
    lodging_nights_by_month = _monthly_values(lodging_nights_rows, '평균 숙박일수')
    if latest_key not in lodging_nights_by_month or previous_key not in lodging_nights_by_month:
        raise ValueError('최신 기준월의 평균 숙박일수를 찾지 못했습니다.')
    latest_lodging_nights = lodging_nights_by_month[latest_key]
    previous_lodging_nights = lodging_nights_by_month[previous_key]

    # '전체' 행을 분모로 삼고, 같은 기준월의 업종대분류별 외지인 소비액을 비중으로 계산합니다.
    latest_spending_total = latest['spending_krw']
    category_rows = [
        row for row in spending_rows
        if _month_value(row) == latest_key and row.get('업종대분류명') != '전체'
    ]
    category_values = [
        (row.get('업종대분류명', '기타'), round(_number(_value_by_contains(row, '소비액(천원)')) * 1000))
        for row in category_rows
    ]
    consumption_categories = [
        ConsumptionCategory(
            name=name,
            share=round(amount / latest_spending_total * 100, 1),
            amount_krw=amount,
        )
        for name, amount in sorted(category_values, key=lambda item: item[1], reverse=True)[:4]
        if amount > 0
    ]

    # 상단 카드의 방문자 수는 숙박 비율과 같은 분모인 월간 순 방문자 수(고유 방문자)로 통일합니다.
    # 그래프도 같은 월간 순 방문자 수를 사용해 상단 카드와 숫자가 달라지지 않게 합니다.
    for point in trend:
        point_key = point['month'].replace('.', '')
        if point_key in unique_visitors_by_month:
            point['visitors'] = unique_visitors_by_month[point_key]
    latest_unique_visitors = unique_visitors_by_month[latest_key]
    previous_unique_visitors = unique_visitors_by_month[previous_key]
    visitor_change = _percent_change(latest_unique_visitors, previous_unique_visitors)
    spending_change = _percent_change(latest['spending_krw'], previous['spending_krw'])
    month_label = f"{int(latest_key[4:])}월"

    return DashboardResponse(
        region_name=region_name,
        latest_month=f'{latest_key[:4]}-{latest_key[4:]}',
        source=f'한국관광 데이터랩 {region_name} 공식 다운로드 원본',
        metrics=[
            DashboardMetric(
                label=f'{month_label} 방문자 수',
                value=f'{latest_unique_visitors:,.0f}명',
                # 카드에서는 수치만 간결하게 보여 주고, 집계 기준은 보고서·출처 화면에서 제공합니다.
                detail='',
                change_label='전월 대비',
                change_value=f'{visitor_change:+.1f}%',
                change_direction=_change_direction(visitor_change),
                accent='aqua',
            ),
            DashboardMetric(
                label=f'{month_label} 관광객 추정 소비액',
                value=f"₩{latest['spending_krw'] / 100_000_000:,.0f}억",
                detail='',
                change_label='전월 대비',
                change_value=f'{spending_change:+.1f}%',
                change_direction=_change_direction(spending_change),
                accent='blue',
            ),
            DashboardMetric(
                # 상단에서는 담당자가 바로 행동으로 해석하기 쉬운 평균 숙박일수를 보여 줍니다.
                # 숙박 방문 비율은 바로 아래 체류 진단에서 함께 제공합니다.
                label=f'{month_label} 평균 숙박일수',
                value=f'{latest_lodging_nights:.2f}일',
                detail='',
                change_label='전월 대비',
                change_value=f'{latest_lodging_nights - previous_lodging_nights:+.2f}일',
                # 숙박일수는 0.01일 변화도 의미가 있으므로 퍼센트 카드의 0.05 기준을 적용하지 않습니다.
                change_direction=(
                    'up' if latest_lodging_nights > previous_lodging_nights
                    else 'down' if latest_lodging_nights < previous_lodging_nights
                    else 'same'
                ),
                accent='purple',
            ),
        ],
        monthly_trend=[MonthlyTrend(**row) for row in trend],
        diagnostic=TourismDiagnostic(
            consumption_categories=consumption_categories,
            lodging_rate=latest_stay,
            average_lodging_nights=latest_lodging_nights,
            lodging_nights_change=latest_lodging_nights - previous_lodging_nights,
        ),
    )


def build_region_snapshot(region_name: str) -> dict[str, Any]:
    """OpenAI에 전달할 선택 지역의 최신 관측값을 원본에서 재현 가능하게 계산합니다."""
    region_directory = _find_region_directory(region_name)
    tables = _read_tables(region_directory)
    visitor_rows = _find_table(tables, '방문자 수(연인원) 추이')
    spending_rows = _find_table(tables, '관광소비 추이_외지인')
    stay_rows = _find_table(tables, '순 방문자 수 및 숙박 비율')
    unique_visitors_by_month = _monthly_values(stay_rows, '순 방문자수')
    monthly_trend = _build_monthly_trend(visitor_rows, spending_rows)
    for point in monthly_trend:
        point_key = point['month'].replace('.', '')
        if point_key in unique_visitors_by_month:
            point['visitors'] = unique_visitors_by_month[point_key]
    visitor = _latest(visitor_rows)
    spending = _latest(spending_rows, lambda row: row.get('업종대분류명') == '전체')
    navigation = _latest(_find_table(tables, '내비게이션 목적지 유형별 검색량'), lambda row: row.get('목적지 유형') == '전체')
    stay = _latest(stay_rows)
    nights = _latest(_find_table(tables, '평균 숙박일'))
    social = _latest(_find_table(tables, 'SNS 언급량'))
    visitors = _number(_value_by_contains(visitor, '방문자수'))
    spending_krw = _number(_value_by_contains(spending, '소비액(천원)')) * 1000
    latest_month = _month_value(visitor)
    latest_unique_visitors = unique_visitors_by_month.get(latest_month, visitors)
    visitor_yoy_change = _number(_value_by_contains(visitor, '방문자수증감률'))
    lodging_rate = _number(_value_by_contains(stay, '숙박자 비율'))
    lodging_nights = _number(_value_by_contains(nights, '평균 숙박일수'))
    navigation_searches = _number(_value_by_contains(navigation, '목적지 검색량'))

    # 등록 지역은 학습에 사용한 최신월 보완 원본까지 포함해 관측값과 ML 기준월을 일치시킵니다.
    registered = _registered_region_history(region_name)
    registered_region_code = ''
    if registered:
        registered_region_code, history = registered
        monthly_trend = _monthly_trend_from_registered_history(history)
        latest_history = history.iloc[-1]
        latest_month = str(latest_history['year_month'])
        latest_unique_visitors = float(latest_history['visitors'])
        spending_krw = float(latest_history['spending_krw'])
        lodging_rate = float(latest_history['lodging_rate_pct'])
        lodging_nights = float(latest_history['lodging_nights'])
        navigation_searches = float(latest_history['navigation_searches'])
        # 전년 동월이 있을 때만 같은 정의의 순 방문자 수로 증감률을 다시 계산합니다.
        previous_year_month = str(int(latest_month[:4]) - 1) + latest_month[4:]
        year_ago = history[history['year_month'].astype(str) == previous_year_month]
        if not year_ago.empty and float(year_ago.iloc[-1]['visitors']) > 0:
            visitor_yoy_change = _percent_change(latest_unique_visitors, float(year_ago.iloc[-1]['visitors']))
    # AI가 포괄적인 관광 일반론 대신 실제 소비 구조를 보고 기획하도록, 최신 월 업종대분류를 함께 제공합니다.
    consumption_by_category = sorted([
        {
            'category': row.get('업종대분류명', '기타'),
            'spending_krw': round(_number(_value_by_contains(row, '소비액(천원)')) * 1000),
            'share_percent': round(_number(_value_by_contains(row, '소비액(천원)')) * 1000 / spending_krw * 100, 1),
        }
        for row in spending_rows
        if _month_value(row) == latest_month and row.get('업종대분류명') != '전체'
    ], key=lambda item: item['spending_krw'], reverse=True)
    if registered_region_code == '11680':
        # 강남구는 최신 소비 ZIP의 업종 비중도 7월까지 있어 같은 관측월 금액으로 맞춥니다.
        consumption_by_category = [
            {
                'category': str(item['name']),
                'share_percent': float(item['share']),
                'spending_krw': round(spending_krw * float(item['share']) / 100),
            }
            for item in load_latest_consumption_shares()
        ]
    source_prefix = f'한국관광 데이터랩 · {region_name}'
    period = f"{monthly_trend[0]['month'].replace('.', '-')} ~ {monthly_trend[-1]['month'].replace('.', '-')}"
    regional_comparison: dict[str, Any]
    try:
        comparison = build_sido_comparison(region_directory.parent.name)
        selected = next(item for item in comparison.regions if item.region_name == region_directory.name)
        peers = [item for item in comparison.regions if item.region_name != region_directory.name]
        peer_visitors = sum(item.visitors for item in peers) / len(peers)
        peer_spending = sum(item.spending_krw for item in peers) / len(peers)
        peer_lodging_rate = sum(item.lodging_rate for item in peers) / len(peers)
        peer_lodging_nights = sum(item.average_lodging_nights for item in peers) / len(peers)
        regional_comparison = {
            'available': True,
            'scope': f'{region_directory.parent.name} 원본 보유 시군구 {len(comparison.regions)}곳',
            'period': comparison.period,
            'selected_region': selected.model_dump(),
            'peer_regions': [item.model_dump() for item in peers],
            'peer_average': {
                'visitors': round(peer_visitors),
                'spending_krw': round(peer_spending),
                'lodging_rate': round(peer_lodging_rate, 1),
                'average_lodging_nights': round(peer_lodging_nights, 2),
            },
            'selected_gap_from_peer_average': {
                'visitors_percent': round((selected.visitors - peer_visitors) / peer_visitors * 100, 1) if peer_visitors else None,
                'spending_percent': round((selected.spending_krw - peer_spending) / peer_spending * 100, 1) if peer_spending else None,
                'lodging_rate_percentage_points': round(selected.lodging_rate - peer_lodging_rate, 1),
                'average_lodging_nights': round(selected.average_lodging_nights - peer_lodging_nights, 2),
            },
            'limitation': '전국 평균이 아니라 data/raw에 같은 기간 원본이 있는 동일 시도 시군구만 비교한 값',
        }
    except (FileNotFoundError, KeyError, StopIteration, ValueError):
        regional_comparison = {
            'available': False,
            'reason': '같은 기간 원본을 갖춘 동일 시도 시군구가 2곳 미만이어서 비교하지 않음',
        }
    observation_month = f'{latest_month[:4]}-{latest_month[4:]}'
    social_month = _month_value(social)
    social_observation_month = f'{social_month[:4]}-{social_month[4:]}' if social_month else observation_month
    return {'region_name': region_name, 'period': period, 'latest_month': observation_month, 'monthly_trend': monthly_trend, 'consumption_by_category': consumption_by_category, 'regional_comparison': regional_comparison, 'observations': [
        {'metric': '월간 순 방문자 수', 'value': f'{latest_unique_visitors:,.0f}명', 'period': observation_month, 'source': f'{source_prefix} 순 방문자 수 및 숙박 비율 (이동통신 기반 외지인)'},
        {'metric': '전년동월 외지인 방문자 증감률', 'value': f'{visitor_yoy_change:.1f}%', 'period': observation_month, 'source': f'{source_prefix} 월간 순 방문자 수 (이동통신 기반 외지인)'},
        {'metric': '월간 외지인 관광소비 총액', 'value': f'{spending_krw:,.0f}원', 'period': observation_month, 'source': f'{source_prefix} 관광소비 추이_외지인'},
        {'metric': '외지인 숙박 방문 비율', 'value': f'{lodging_rate:.1f}%', 'period': observation_month, 'source': f'{source_prefix} 숙박방문자 비율 추이 (이동통신 기반 외지인)'},
        {'metric': '외지인 평균 숙박일수', 'value': f'{lodging_nights:.2f}일', 'period': observation_month, 'source': f'{source_prefix} 평균 숙박일 (이동통신 기반 외지인)'},
        {'metric': '내비게이션 목적지 검색량', 'value': f'{navigation_searches:,.0f}건', 'period': observation_month, 'source': f'{source_prefix} 내비게이션 목적지 유형별 검색량'},
        {'metric': 'SNS 언급량', 'value': f'{_number(_value_by_contains(social, "검색량(건)")):,.0f}건', 'period': social_observation_month, 'source': f'{source_prefix} SNS 언급량'},
    ]}


REPORT_SCHEMA = {'type': 'object', 'additionalProperties': False, 'properties': {
    'summary': {'type': 'string'},
    'observed_findings': {'type': 'array', 'minItems': 3, 'maxItems': 5, 'items': {'type': 'object', 'additionalProperties': False, 'properties': {'metric': {'type': 'string'}, 'value': {'type': 'string'}, 'interpretation': {'type': 'string'}, 'source': {'type': 'string'}}, 'required': ['metric', 'value', 'interpretation', 'source']}},
    'strategies': {'type': 'array', 'minItems': 1, 'maxItems': 1, 'items': {'type': 'object', 'additionalProperties': False, 'properties': {'priority': {'type': 'integer'}, 'timeframe': {'type': 'string'}, 'title': {'type': 'string'}, 'problem_to_solve': {'type': 'string'}, 'comparison_analysis': {'type': 'string'}, 'solution': {'type': 'string'}, 'implementation_steps': {'type': 'array', 'minItems': 5, 'maxItems': 5, 'items': {'type': 'object', 'additionalProperties': False, 'properties': {'step': {'type': 'integer'}, 'schedule': {'type': 'string'}, 'task': {'type': 'string'}, 'deliverable': {'type': 'string'}}, 'required': ['step', 'schedule', 'task', 'deliverable']}}, 'expected_effect': {'type': 'string'}, 'budget': {'type': 'string'}, 'kpi': {'type': 'string'}, 'evidence': {'type': 'string'}, 'visual_asset_source_ids': {'type': 'array', 'maxItems': 2, 'items': {'type': 'string'}}}, 'required': ['priority', 'timeframe', 'title', 'problem_to_solve', 'comparison_analysis', 'solution', 'implementation_steps', 'expected_effect', 'budget', 'kpi', 'evidence', 'visual_asset_source_ids']}},
}, 'required': ['summary', 'observed_findings', 'strategies']}


def _output_text(payload: dict[str, Any]) -> str:
    for item in payload.get('output') or []:
        for content in item.get('content') or []:
            if content.get('type') == 'output_text':
                return content.get('text') or ''
    raise ValueError('OpenAI 응답에서 보고서 텍스트를 찾지 못했습니다.')


async def generate_report(request: ReportRequest) -> ReportResponse:
    api_key = (ENV_VALUES.get('OPENAI_API_KEY') or '').strip()
    if not api_key:
        raise HTTPException(status_code=503, detail={'code': 'OPENAI_KEY_MISSING', 'message': 'AI 서버의 OpenAI 키가 설정되지 않았습니다.'})
    snapshot = build_region_snapshot(request.region_name)
    body = {
        # 보고서 전용 설정이 없으면 공통 모델 설정을 사용합니다. Codex 전용 모델명은 API 기본값으로 쓰지 않습니다.
        'model': (ENV_VALUES.get('OPENAI_REPORT_MODEL') or ENV_VALUES.get('OPENAI_MODEL') or 'gpt-5.6').strip(), 'store': False, 'max_output_tokens': 10000,
        # 단일 실행 기획안의 비교 진단과 단계별 집행안을 충분히 담을 수 있도록 출력 한도를 둡니다.
        'reasoning': {'effort': 'medium'},
        'instructions': '한국 지역관광 데이터 기반 실행 기획안을 작성한다. 입력 snapshot의 관측값과 출처만 사실로 사용하고, 출처 밖의 수치·관광지·정책·사례·성과·평균 숙박비를 만들지 마라. strategies에는 서로 분리된 기간별 전략이 아니라 하나의 통합 기획안만 작성한다. timeframe은 원칙적으로 향후 3~6개월로 정하되, 문제와 집행 단계상 다른 기간이 타당하면 짧게 이유가 드러나는 기간으로 조정한다. 기획안의 목표는 방문자 수 또는 관광소비액 개선이며, 반드시 문제 확인→솔루션→집행 방법 순서로 논리가 이어져야 한다. problem_to_solve은 월간 추세·소비 업종 구성·체류 지표 가운데 핵심 문제 1~2개를 수치와 함께 특정한다. comparison_analysis는 regional_comparison.available이 true일 때만 같은 기간·같은 시도 원본 보유 시군구 및 peer_average와 비교하고, 전국·시도 전체 평균이라고 확대 해석하지 마라. 비교 자료가 없으면 비교 불가 사유와 선택 지역 자체 추세에서 확인한 문제를 쓴다. solution은 문제의 원인으로 단정할 수 없는 부분은 검증 가설로 표시하고, 대상·방식·운영 범위를 구체화한다. 소비 업종은 consumption_by_category에 있는 이름만 사용한다. 실제 장소·업체·행사·숙박비가 snapshot에 없으면 이름이나 금액을 만들지 말고 후보 모집·현장조사·견적 확보 같은 선정 절차를 제안한다. implementation_steps는 3~5개로 만들고 step은 1부터 순서대로, schedule은 전체 기간 안의 주차 또는 월 범위, task는 실제 행동, deliverable은 완료를 확인할 수 있는 산출물을 쓴다. budget에는 근거 없는 원화 금액을 쓰지 말고 필요한 비용 항목·수량 기준·공식 단가 또는 비교견적 확보처·계산식을 제시한 뒤 견적 확보 후 확정이라고 쓴다. expected_effect는 검증할 변화 방향만 쓰고 성과 수치를 예측하지 마라. kpi는 방문자·소비·체류 원자료로 사전/집행/사후를 비교할 수 있게 기준월과 확인 주기를 명시한다. evidence에는 실제 사용한 snapshot 지표와 비교 기간을 적는다. "활성화", "강화", "확대", "노력"만으로 끝나는 문장을 피하고 모든 내용은 한국어로 간결하고 구체적으로 쓴다.',
        'input': json.dumps({'report_mode': '지역관광 데이터 기반 실행 기획안', 'snapshot': snapshot}, ensure_ascii=False),
        'text': {'verbosity': 'medium', 'format': {'type': 'json_schema', 'name': 'regional_tourism_plan', 'strict': True, 'schema': REPORT_SCHEMA}},
    }
    try:
        # 구조화된 보고서는 추론과 JSON 검증에 시간이 더 걸릴 수 있어 일반 조회 API보다 긴 제한을 둡니다.
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post('https://api.openai.com/v1/responses', headers={'Authorization': f'Bearer {api_key}'}, json=body)
    except httpx.TimeoutException as exc:
        LOGGER.warning('OpenAI Responses API timed out after 120 seconds')
        raise HTTPException(status_code=504, detail={'code': 'OPENAI_TIMEOUT', 'message': 'AI 보고서 생성 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.'}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail={'code': 'OPENAI_CONNECTION_ERROR', 'message': 'OpenAI API 서버에 연결하지 못했습니다.'}) from exc
    if response.status_code == 401:
        raise HTTPException(status_code=503, detail={'code': 'OPENAI_AUTH_ERROR', 'message': 'AI 서버의 OpenAI API 키 인증에 실패했습니다.'})
    if response.status_code >= 400:
        error_payload = response.json().get('error', {}) if response.headers.get('content-type', '').startswith('application/json') else {}
        LOGGER.warning(
            'OpenAI Responses API request failed: status=%s code=%s type=%s request_id=%s',
            response.status_code,
            error_payload.get('code'),
            error_payload.get('type'),
            response.headers.get('x-request-id'),
        )
        if response.status_code in (400, 404):
            raise HTTPException(status_code=502, detail={'code': 'OPENAI_MODEL_OR_REQUEST_ERROR', 'message': 'AI 보고서 모델 또는 요청 설정을 확인해 주세요.'})
        raise HTTPException(status_code=502, detail={'code': 'OPENAI_RESPONSE_ERROR', 'message': 'OpenAI가 보고서를 생성하지 못했습니다. 잠시 후 다시 시도해 주세요.'})
    try:
        response_payload = response.json()
        response_status = response_payload.get('status')
        if response_status != 'completed':
            error = response_payload.get('error') or {}
            incomplete_details = response_payload.get('incomplete_details') or {}
            LOGGER.warning(
                'OpenAI response was not completed: status=%s error_code=%s incomplete_reason=%s request_id=%s',
                response_status,
                error.get('code'),
                incomplete_details.get('reason'),
                response.headers.get('x-request-id'),
            )
            if response_status == 'incomplete':
                raise HTTPException(status_code=502, detail={'code': 'OPENAI_INCOMPLETE_RESPONSE', 'message': 'AI 보고서 생성이 출력 한도 안에 완료되지 않았습니다. 잠시 후 다시 시도해 주세요.'})
            raise HTTPException(status_code=502, detail={'code': 'OPENAI_GENERATION_FAILED', 'message': 'OpenAI가 보고서 생성을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.'})
        generated = json.loads(_output_text(response_payload))
        return ReportResponse(region_name=snapshot['region_name'], period=snapshot['period'], metrics_count=len(snapshot['observations']), monthly_trend=snapshot['monthly_trend'], **generated)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        LOGGER.warning('OpenAI report output validation failed: %s request_id=%s', type(exc).__name__, response.headers.get('x-request-id'))
        raise HTTPException(status_code=502, detail={'code': 'OPENAI_INVALID_OUTPUT', 'message': 'OpenAI 보고서 형식을 검증하지 못했습니다.'}) from exc


async def generate_orchestrated_report(region_code: str, request: ReportRequest) -> ReportResponse:
    """지역 근거→공식 사례→적합성→기획→품질 검토 Agent를 고정 순서로 실행합니다."""
    if request.planning_brief and request.planning_brief.region_code != region_code:
        raise HTTPException(status_code=422, detail={'code': 'BRIEF_REGION_MISMATCH', 'message': '기획 조건의 지역과 선택 지역이 다릅니다.'})
    brief = request.planning_brief.model_dump(mode='json') if request.planning_brief else None
    api_key = (ENV_VALUES.get('OPENAI_API_KEY') or '').strip()
    if not api_key:
        raise HTTPException(status_code=503, detail={'code': 'OPENAI_KEY_MISSING', 'message': 'AI 서버의 OpenAI 키가 설정되지 않았습니다.'})
    snapshot = build_region_snapshot(request.region_name)
    try:
        result = await orchestrate_strategy_report(
            project_root=PROJECT_ROOT,
            env_values=ENV_VALUES,
            region_code=region_code,
            snapshot=snapshot,
            report_schema=REPORT_SCHEMA,
            planning_brief=brief,
        )
        return ReportResponse(
            region_name=snapshot['region_name'],
            period=snapshot['period'],
            metrics_count=len(snapshot['observations']),
            monthly_trend=snapshot['monthly_trend'],
            quality_review=result['quality_review'],
            ml_analysis=result.get('ml_analysis'),
            evidence_sources=result['evidence_sources'],
            research_gaps=result['research_gaps'],
            agent_trace=result['agent_trace'],
            planning_brief=without_reference_text(request.planning_brief),
            planning_brief_fingerprint=brief_fingerprint(brief),
            **result['report'],
        )
    except OpenAIResponseError as exc:
        LOGGER.warning('Multi-agent report failed: code=%s message=%s', exc.code, exc.message)
        raise HTTPException(
            status_code=exc.status_code,
            detail={'code': exc.code, 'message': exc.message},
        ) from exc


def _job_error_message(exc: HTTPException) -> str:
    """작업 상태 API에는 내부 오류 객체 대신 안전한 사용자용 문구만 남깁니다."""
    detail = exc.detail
    if isinstance(detail, dict):
        return str(detail.get('message') or 'AI 전략기획서를 생성하지 못했습니다.')
    return str(detail or 'AI 전략기획서를 생성하지 못했습니다.')


def _persist_completed_strategy_report(job_id: str, region_code: str, report: ReportResponse) -> None:
    """완료된 기획안을 MySQL과 로컬 서버 문서 폴더에 한 번만 영구 저장합니다."""
    payload = report.model_dump(mode='json')
    save_strategy_report(job_id, region_code, payload)
    # 문서 생성 실패가 AI 기획안 본문 저장을 되돌리지는 않도록 파일 출력은 별도로 보호합니다.
    try:
        write_document(job_id, 'docx', create_strategy_proposal_document(payload).getvalue())
        write_document(job_id, 'pptx', create_strategy_proposal_presentation(payload).getvalue())
    except (KeyError, TypeError, ValueError, OSError) as exc:
        LOGGER.warning('Strategy document save failed: job_id=%s error=%s', job_id, type(exc).__name__)


def _strategy_job_response(job_id: str) -> StrategyReportJobResponse:
    job = STRATEGY_REPORT_JOBS[job_id]
    return StrategyReportJobResponse(
        job_id=job_id,
        region_code=job['region_code'],
        region_name=job['region_name'],
        status=job['status'],
        message=job['message'],
        report=job.get('report'),
        error=job.get('error', ''),
    )


def _job_persistence_payload(request: ReportRequest) -> tuple[dict[str, Any], bool]:
    """재시작용 요청에서 첨부문서 본문을 제거하고 첨부 존재 여부만 반환합니다."""
    had_transient_references = bool(request.planning_brief and request.planning_brief.references)
    persisted_request = request.model_dump(mode='json')
    if request.planning_brief:
        persisted_request['planning_brief'] = without_reference_text(request.planning_brief).model_dump(mode='json')
    return persisted_request, had_transient_references


def _persist_job_state_best_effort(job_id: str, job: dict[str, Any]) -> None:
    """MySQL 장애가 대시보드·현재 메모리 작업까지 중단시키지 않도록 상태 저장만 보호합니다."""
    try:
        update_strategy_job_state(job_id, job['status'], job['message'], job.get('error', ''))
    except Exception as exc:
        LOGGER.warning('Strategy job state persistence failed: job_id=%s error=%s', job_id, type(exc).__name__)


async def _run_strategy_report_job(job_id: str, region_code: str, request: ReportRequest) -> None:
    """긴 Agent 작업을 HTTP 요청 수명과 분리해 서버에서 끝까지 실행합니다."""
    job = STRATEGY_REPORT_JOBS[job_id]
    job.update(status='running', message='지역 원자료와 공식 근거를 확인하고 있습니다.', error='')
    _persist_job_state_best_effort(job_id, job)
    try:
        report = await generate_orchestrated_report(region_code, request)
    except HTTPException as exc:
        message = _job_error_message(exc)
        # 개발 중 크레딧·할당량 문제에서는 기존 화면 검토용 원자료 샘플을 사용합니다.
        # 실제 OpenAI 결과와 혼동되지 않도록 generation_mode는 offline_sample으로 유지됩니다.
        if re.search(r'credit|quota|billing|크레딧|잔액', message, flags=re.IGNORECASE):
            try:
                snapshot = build_region_snapshot(request.region_name)
                report = ReportResponse(**build_offline_sample_report(region_code, snapshot), planning_brief=without_reference_text(request.planning_brief))
            except (FileNotFoundError, KeyError, ValueError) as sample_exc:
                job.update(status='failed', message='기획서 생성을 완료하지 못했습니다.', error=str(sample_exc))
            else:
                job.update(status='completed', message='원자료 기반 오프라인 샘플 기획안을 만들었습니다.', report=report)
        else:
            job.update(status='failed', message='기획서 생성을 완료하지 못했습니다.', error=message)
    except Exception as exc:  # 예기치 못한 오류도 작업 상태로 돌려 UI가 무한 로딩하지 않게 합니다.
        LOGGER.exception('Background strategy job failed: job_id=%s', job_id)
        job.update(status='failed', message='기획서 생성을 완료하지 못했습니다.', error=f'{type(exc).__name__}: {exc}')
    else:
        job.update(status='completed', message='AI 전략기획서 생성이 완료되었습니다.', report=report)
    if job.get('status') == 'completed' and job.get('report'):
        try:
            _persist_completed_strategy_report(job_id, region_code, job['report'])
        except Exception as exc:
            # 저장 실패는 생성 결과를 없애지 않고, 서버 로그에서 DB 연결을 점검할 수 있게 남깁니다.
            LOGGER.exception('Strategy report persistence failed: job_id=%s error=%s', job_id, type(exc).__name__)
            job.update(message='기획안은 생성됐지만 MySQL 저장에 실패했습니다. 서버 DB 설정을 확인해 주세요.')
    _persist_job_state_best_effort(job_id, job)


@app.get('/ai/health')
async def health_check() -> dict[str, str]:
    return {'status': 'ok'}


@app.get('/ai/v1/strategy-reports')
async def read_saved_strategy_reports() -> list[dict[str, Any]]:
    """모든 팀원이 같은 MySQL 기록에서 저장된 기획서 목록을 확인합니다."""
    try:
        return list_strategy_reports()
    except Exception as exc:
        LOGGER.exception('Strategy report list failed: %s', type(exc).__name__)
        raise HTTPException(status_code=503, detail={'code': 'STRATEGY_STORE_UNAVAILABLE', 'message': '저장 기획서 DB에 연결하지 못했습니다. MySQL 설정을 확인해 주세요.'}) from exc


@app.get('/ai/v1/strategy-reports/{report_id}')
async def read_saved_strategy_report(report_id: str) -> dict[str, Any]:
    """게시판의 제목 클릭 시 MySQL에 저장된 원본 기획안을 반환합니다."""
    try:
        report = read_strategy_report(report_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail={'code': 'STRATEGY_STORE_UNAVAILABLE', 'message': '저장 기획서 DB에 연결하지 못했습니다.'}) from exc
    if not report:
        raise HTTPException(status_code=404, detail={'code': 'SAVED_STRATEGY_NOT_FOUND', 'message': '저장된 기획안을 찾지 못했습니다.'})
    return report


@app.put('/ai/v1/strategy-reports/{report_id}')
async def update_saved_strategy_report(report_id: str, region_code: str, report: ReportResponse) -> dict[str, str]:
    """챗봇 수정 후 사용자가 저장한 기획안을 같은 MySQL 기록에 반영합니다."""
    try:
        save_strategy_report(report_id, region_code, report.model_dump(mode='json'))
    except Exception as exc:
        LOGGER.exception('Strategy report update failed: %s', type(exc).__name__)
        raise HTTPException(status_code=503, detail={'code': 'STRATEGY_STORE_UNAVAILABLE', 'message': '기획안을 MySQL에 저장하지 못했습니다.'}) from exc
    return {'status': 'saved'}


@app.get('/ai/v1/strategy-reports/{report_id}/documents/{file_format}')
async def download_saved_strategy_document(report_id: str, file_format: Literal['docx', 'pptx']) -> StreamingResponse:
    """이미 저장한 Word/PPT 파일을 재생성하지 않고 서버 파일 저장소에서 내려보냅니다."""
    try:
        content = read_document(report_id, file_format)
        if content is None:
            report = read_strategy_report(report_id)
            if not report:
                raise HTTPException(status_code=404, detail={'code': 'SAVED_STRATEGY_NOT_FOUND', 'message': '저장된 기획안을 찾지 못했습니다.'})
            content = (
                create_strategy_proposal_document(report).getvalue()
                if file_format == 'docx'
                else create_strategy_proposal_presentation(report).getvalue()
            )
            write_document(report_id, file_format, content)
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception('Stored document download failed: %s', type(exc).__name__)
        raise HTTPException(status_code=503, detail={'code': 'SAVED_DOCUMENT_UNAVAILABLE', 'message': '저장된 문서를 준비하지 못했습니다.'}) from exc
    media_type = (
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        if file_format == 'docx'
        else 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
    )
    return StreamingResponse(BytesIO(content), media_type=media_type, headers={'Content-Disposition': f'attachment; filename="tourism-strategy-proposal.{file_format}"'})


@app.get('/ai/v1/ml/{region_code}/planning-evidence', response_model=PlanningMlEvidence)
async def read_planning_ml_evidence(region_code: str, region_name: str) -> PlanningMlEvidence:
    """유료 API 없이 기획 Agent에 전달될 ML 전망·오차·조사 질문을 확인합니다."""
    return await asyncio.to_thread(build_planning_ml_evidence, region_code, region_name)


@app.get('/ai/v1/ml/learning/catalog', response_model=MlLearningCatalog)
async def read_ml_learning_catalog() -> MlLearningCatalog:
    """학습용 화면에서 등록된 지역별 모델·함수·예측·평가를 한 번에 확인합니다."""
    return await asyncio.to_thread(build_ml_learning_catalog)


@app.post('/ai/v1/ml/learning/{region_code}/assistant', response_model=MlLearningChatResponse)
async def chat_with_ml_learning_assistant(
    region_code: str,
    request: MlLearningChatRequest,
) -> MlLearningChatResponse:
    """등록 모델·평가·함수 정보만 근거로 ML 학습 질문에 답합니다."""
    catalog = await asyncio.to_thread(build_ml_learning_catalog)
    region = next((item for item in catalog.regions if item.region_code == region_code), None)
    if region is None or region.status != 'available':
        raise HTTPException(
            status_code=404,
            detail={'code': 'ML_LEARNING_REGION_UNAVAILABLE', 'message': '선택 지역의 머신러닝 학습 정보를 찾지 못했습니다.'},
        )
    if not (ENV_VALUES.get('OPENAI_API_KEY') or '').strip():
        raise HTTPException(
            status_code=503,
            detail={'code': 'OPENAI_KEY_MISSING', 'message': 'ML 챗봇을 사용하려면 AI 서버의 OpenAI API 키가 필요합니다.'},
        )
    try:
        result = await MlLearningAssistantAgent(env_values=ENV_VALUES).answer(
            learning_region=region.model_dump(mode='json'),
            question=request.question,
            history=[message.model_dump() for message in request.history],
        )
        return MlLearningChatResponse(**result)
    except OpenAIResponseError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={'code': exc.code, 'message': exc.message},
        ) from exc


@app.get('/ai/v1/learning/assistant-status', response_model=LearningAssistantStatusResponse)
async def read_learning_assistant_status() -> LearningAssistantStatusResponse:
    """AI Server·OpenAI 키·선택 모델 연결을 확인해 학습 챗봇 배지에 제공합니다."""
    model = str(
        ENV_VALUES.get('OPENAI_LEARNING_CHAT_MODEL')
        or ENV_VALUES.get('OPENAI_ML_CHAT_MODEL')
        or ENV_VALUES.get('OPENAI_CHAT_MODEL')
        or ENV_VALUES.get('OPENAI_MODEL')
        or 'gpt-5.5'
    ).strip()
    status = await check_openai_readiness(
        api_key=str(ENV_VALUES.get('OPENAI_API_KEY') or ''), model=model,
    )
    return LearningAssistantStatusResponse(**status)


@app.get('/ai/v1/learning/{topic}', response_model=ProjectLearningCatalog)
async def read_project_learning_catalog(topic: Literal['openai', 'react']) -> ProjectLearningCatalog:
    """현재 프로젝트 파일을 다시 읽어 OpenAI 또는 React 학습 구조를 반환합니다."""
    try:
        return await asyncio.to_thread(build_project_learning_catalog, topic)
    except (OSError, ValueError, SyntaxError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail={'code': 'PROJECT_LEARNING_SCAN_FAILED', 'message': '프로젝트 학습 구조를 읽지 못했습니다.'},
        ) from exc


@app.post('/ai/v1/learning/{topic}/assistant', response_model=ProjectLearningChatResponse)
async def chat_with_project_learning_assistant(
    topic: Literal['openai', 'react'], request: ProjectLearningChatRequest,
) -> ProjectLearningChatResponse:
    """자동 탐색한 현재 구조를 근거로 OpenAI·React 학습 질문에 답합니다."""
    catalog = await asyncio.to_thread(build_project_learning_catalog, topic)
    if not (ENV_VALUES.get('OPENAI_API_KEY') or '').strip():
        raise HTTPException(
            status_code=503,
            detail={'code': 'OPENAI_KEY_MISSING', 'message': '학습 챗봇을 사용하려면 AI 서버의 OpenAI API 키가 필요합니다.'},
        )
    try:
        result = await ProjectLearningAssistantAgent(env_values=ENV_VALUES).answer(
            topic=topic, project_catalog=catalog.model_dump(mode='json'),
            question=request.question, history=[message.model_dump() for message in request.history],
        )
        return ProjectLearningChatResponse(**result)
    except OpenAIResponseError as exc:
        raise HTTPException(status_code=exc.status_code, detail={'code': exc.code, 'message': exc.message}) from exc


@app.get('/ai/v1/demo/sido-comparison', response_model=SidoComparisonResponse)
async def read_sido_comparison(sido_name: str) -> SidoComparisonResponse:
    """같은 시도에서 원본이 준비된 시군구의 최근 3개월 평균을 반환합니다."""
    try:
        return build_sido_comparison(sido_name)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=404,
            detail={'code': 'SIDO_COMPARISON_DATA_UNAVAILABLE', 'message': '비교 가능한 시군구 원본 데이터를 읽지 못했습니다.'},
        ) from exc


@app.get('/ai/v1/demo/{region_code}/dashboard', response_model=DashboardResponse)
async def read_region_dashboard(region_code: str, region_name: str) -> DashboardResponse:
    """선택 지역의 관측 대시보드 또는 강남구 저장 모델 예측 대시보드를 반환합니다."""
    try:
        # 등록·검증된 지역은 같은 ML 대시보드를 사용하고, 아직 등록되지 않은 지역은 관측 원자료만 표시합니다.
        try:
            pipeline = get_region_pipeline(region_code)
        except ValueError:
            pipeline = None
        if pipeline and _normalize_region_name(region_name) == _normalize_region_name(pipeline.region_name):
            return _build_registered_ml_dashboard(region_code, pipeline.region_name)
        return build_region_dashboard(region_name)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=404,
            detail={'code': 'REGION_DASHBOARD_DATA_UNAVAILABLE', 'message': '선택 지역의 대시보드 원본 데이터를 읽지 못했습니다.'},
        ) from exc


@app.get('/ai/v1/demo/{region_code}/region-info', response_model=RegionOpenApiInfoResponse)
async def read_region_open_api_info(region_code: str, region_name: str) -> RegionOpenApiInfoResponse:
    """선택 지역의 관광자원을 서버에서만 Open API로 조회합니다.

    공공 API 인증키는 이 서버의 .env에서만 읽습니다. API가 미신청·일시 장애여도
    지역 선택 화면 전체를 실패시키지 않고, 팝업에서 상태를 정직하게 안내합니다.
    """
    source_url = str(
        ENV_VALUES.get('TOUR_INFO_API_BASE_URL')
        or 'https://apis.data.go.kr/B551011/KorService2'
    )
    api_key = str(
        ENV_VALUES.get('TOUR_CONTENT_LAB_API_KEY')
        or ENV_VALUES.get('TOUR_API_SERVICE_KEY')
        or ENV_VALUES.get('DATA_GO_KR_SERVICE_KEY')
        or ''
    ).strip()
    base_response = {
        'region_code': region_code,
        'region_name': region_name,
        'source_name': '한국관광공사 국문 관광정보 Open API',
        'source_url': source_url,
    }
    if not api_key:
        return RegionOpenApiInfoResponse(
            **base_response,
            status='not_configured',
            message='서버의 관광 Open API 인증키가 아직 설정되지 않아 관광자원 정보를 조회하지 못했습니다.',
        )

    try:
        resources = await TourismOpenApiClient(api_key=api_key, base_url=source_url).collect_region_resources(region_name, limit=18)
    except Exception as exc:  # 외부 공공 API 오류가 지역 대시보드를 멈추지 않도록 분리합니다.
        LOGGER.info('Region Open API lookup failed for %s: %s', region_name, type(exc).__name__)
        return RegionOpenApiInfoResponse(
            **base_response,
            status='unavailable',
            message='관광 Open API에 일시적으로 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.',
        )

    content_type_labels = {
        '12': '관광지', '14': '문화시설', '15': '행사·공연', '25': '여행코스',
        '28': '레포츠', '32': '숙박', '38': '쇼핑', '39': '음식점',
    }
    formatted_resources = [
        RegionOpenApiResource(
            title=str(resource.get('title') or '관광자원'),
            address=str(resource.get('address') or ''),
            image_url=str(resource.get('image_url') or ''),
            content_type=content_type_labels.get(str(resource.get('content_type_id') or ''), '관광자원'),
            source_url=str(resource.get('source_url') or source_url),
        )
        for resource in resources
    ]
    category_counts: dict[str, int] = {}
    for resource in formatted_resources:
        category_counts[resource.content_type] = category_counts.get(resource.content_type, 0) + 1
    category_summary = [
        {'name': category, 'count': count}
        for category, count in sorted(category_counts.items(), key=lambda item: (-item[1], item[0]))
    ]

    if not formatted_resources:
        return RegionOpenApiInfoResponse(
            **base_response,
            status='empty',
            message='현재 선택 지역명으로 반환된 관광자원 정보가 없습니다. API의 지역 코드·서비스 활용신청 상태를 확인해 주세요.',
        )
    return RegionOpenApiInfoResponse(
        **base_response,
        status='ready',
        message=f'관광 Open API에서 {len(formatted_resources)}건의 관광자원 정보를 확인했습니다.',
        resources=formatted_resources,
        category_summary=category_summary,
    )


@app.post('/ai/v1/planning/reference')
async def read_planning_reference(request: Request, filename: str) -> dict:
    """유료 호출 없이 문서의 텍스트만 추출합니다. 본문 스트림도 크기를 제한합니다."""
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 2_000_000:
            raise HTTPException(status_code=413, detail={'code': 'REFERENCE_TOO_LARGE', 'message': '2MB 이하 파일만 첨부할 수 있습니다.'})
    try:
        return extract_brief_reference(filename, bytes(content))
    except Exception as exc:
        message = str(exc) if isinstance(exc, ValueError) else '문서 텍스트를 읽지 못했습니다. TXT 또는 정상 DOCX를 사용해 주세요.'
        raise HTTPException(status_code=422, detail={'code': 'REFERENCE_INVALID', 'message': message}) from exc


@app.post('/ai/v1/demo/{region_code}/strategy-report/jobs', response_model=StrategyReportJobResponse, status_code=202)
async def start_region_strategy_report_job(region_code: str, request: ReportRequest) -> StrategyReportJobResponse:
    """AI 전략기획 생성을 백그라운드에 등록하고 즉시 작업 ID를 반환합니다."""
    if request.planning_brief and request.planning_brief.region_code != region_code:
        raise HTTPException(status_code=422, detail={'code': 'BRIEF_REGION_MISMATCH', 'message': '기획 조건의 지역과 선택 지역이 다릅니다.'})
    # 실행 조건은 작업마다 복사합니다. 다른 사용자의 같은 지역 작업을 차단하지 않습니다.
    request = request.model_copy(deep=True)
    job_id = uuid4().hex
    STRATEGY_REPORT_JOBS[job_id] = {
        'region_code': region_code,
        'region_name': request.region_name,
        'status': 'queued',
        'message': 'AI 전략기획서 생성 요청을 등록했습니다.',
        'error': '',
    }
    # 첨부 본문은 메모리에서만 Agent에 전달합니다. MySQL에는 첨부를 제거한 조건과
    # 재시작 가능 여부만 저장해 개인정보·참고문서 비저장 원칙을 지킵니다.
    persisted_request, had_transient_references = _job_persistence_payload(request)
    try:
        save_strategy_job(
            job_id, region_code, request.region_name, 'queued',
            'AI 전략기획서 생성 요청을 등록했습니다.',
            request_payload=persisted_request,
            had_transient_references=had_transient_references,
        )
    except Exception as exc:
        LOGGER.warning('Strategy job initial persistence failed: job_id=%s error=%s', job_id, type(exc).__name__)
    asyncio.create_task(_run_strategy_report_job(job_id, region_code, request))
    return _strategy_job_response(job_id)


@app.get('/ai/v1/demo/{region_code}/strategy-report/jobs/{job_id}', response_model=StrategyReportJobResponse)
async def read_region_strategy_report_job(region_code: str, job_id: str) -> StrategyReportJobResponse:
    """페이지를 이동했다 돌아와도 같은 작업 ID로 결과와 진행 상태를 다시 읽습니다."""
    job = STRATEGY_REPORT_JOBS.get(job_id)
    if not job:
        try:
            stored_job = read_strategy_job(job_id)
        except Exception:
            stored_job = None
        if stored_job:
            report = None
            if stored_job['status'] == 'completed':
                try:
                    stored_report = read_strategy_report(job_id)
                    report = ReportResponse.model_validate(stored_report) if stored_report else None
                except Exception:
                    report = None
            job = {
                'region_code': stored_job['region_code'], 'region_name': stored_job['region_name'],
                'status': stored_job['status'], 'message': stored_job['message'],
                'error': stored_job['error'], 'report': report,
            }
            STRATEGY_REPORT_JOBS[job_id] = job
    if not job or job.get('region_code') != region_code:
        raise HTTPException(status_code=404, detail={'code': 'STRATEGY_JOB_NOT_FOUND', 'message': '진행 중인 전략기획 작업을 찾지 못했습니다.'})
    return _strategy_job_response(job_id)


@app.post('/ai/v1/demo/{region_code}/strategy-report', response_model=ReportResponse)
async def create_region_strategy_report(region_code: str, request: ReportRequest) -> ReportResponse:
    """선택 지역 근거와 공식 성공사례를 다섯 Agent가 처리한 전략 보고서를 생성합니다."""
    try:
        return await generate_orchestrated_report(region_code, request)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=404,
            detail={'code': 'REGION_REPORT_DATA_UNAVAILABLE', 'message': '선택 지역의 전략 보고서 원본 데이터를 읽지 못했습니다.'},
        ) from exc


@app.post('/ai/v1/demo/{region_code}/strategy-report/sample', response_model=ReportResponse)
async def create_offline_sample_strategy_report(region_code: str, request: ReportRequest) -> ReportResponse:
    """개발 중 화면·Word 형식을 확인하는 원자료 기반 샘플입니다. OpenAI를 호출하지 않습니다."""
    if str(ENV_VALUES.get('APP_ENV') or 'development').lower() == 'production':
        raise HTTPException(status_code=404, detail={'code': 'OFFLINE_SAMPLE_DISABLED', 'message': '운영 환경에서는 오프라인 샘플을 제공하지 않습니다.'})
    try:
        snapshot = build_region_snapshot(request.region_name)
        return ReportResponse(**build_offline_sample_report(region_code, snapshot), planning_brief=without_reference_text(request.planning_brief))
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=404,
            detail={'code': 'OFFLINE_SAMPLE_DATA_UNAVAILABLE', 'message': '오프라인 샘플을 만들 지역 원본 데이터를 읽지 못했습니다.'},
        ) from exc


def _offline_assistant_response(snapshot: dict[str, Any]) -> AssistantChatResponse:
    """API 크레딧 없이도 챗봇 화면과 실제 원자료 전달 여부를 검증하는 안전한 응답입니다."""
    observations = snapshot.get('observations') or []
    key_points = [
        f"{item.get('metric')}: {item.get('value')} ({item.get('period')})"
        for item in observations[:3]
    ]
    return AssistantChatResponse(
        answer=(
            f"{snapshot['region_name']}의 공식 원자료는 정상적으로 읽었습니다. "
            "현재는 OpenAI API 크레딧이 없어 해석·웹 조사·기획안 수정은 실행하지 않았습니다. "
            "아래 값으로 대화 화면과 데이터 연결을 확인할 수 있습니다."
        ),
        mode='explain',
        key_points=key_points,
        sources=[],
        report_patch=None,
        generation_mode='offline_sample',
    )


@app.post('/ai/v1/demo/{region_code}/assistant-chat', response_model=AssistantChatResponse)
async def chat_with_tourism_assistant(region_code: str, request: AssistantChatRequest) -> AssistantChatResponse:
    """지역 원자료·현재 기획안·공식 웹 자료를 근거로 설명하거나 수정안을 제안합니다."""
    try:
        snapshot = build_region_snapshot(request.region_name)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=404,
            detail={'code': 'REGION_ASSISTANT_DATA_UNAVAILABLE', 'message': '선택 지역의 챗봇용 원자료를 읽지 못했습니다.'},
        ) from exc

    api_key = (ENV_VALUES.get('OPENAI_API_KEY') or '').strip()
    if not api_key:
        return _offline_assistant_response(snapshot)

    try:
        result = await TourismChatAssistantAgent(env_values=ENV_VALUES).answer(
            snapshot=snapshot,
            question=request.question,
            history=[message.model_dump() for message in request.history],
            current_report=request.current_report,
            enable_web_search=request.enable_web_search,
            planning_brief=(request.current_report or {}).get('planning_brief') if request.current_report else (
                request.planning_brief.model_dump(mode='json') if request.planning_brief else None
            ),
        )
        return AssistantChatResponse(**result, generation_mode='openai')
    except OpenAIResponseError as exc:
        # 개발 중 크레딧이 소진되어도 UI·원자료 연결 검증은 계속할 수 있게 명확히 구분된 샘플을 반환합니다.
        if any(word in exc.message.lower() for word in ('credit', 'quota', 'billing')):
            return _offline_assistant_response(snapshot)
        raise HTTPException(status_code=exc.status_code, detail={'code': exc.code, 'message': exc.message}) from exc


@app.post('/ai/v1/demo/{region_code}/strategy-proposal.docx')
async def download_region_strategy_proposal(region_code: str, report: ReportResponse) -> StreamingResponse:
    """이미 검증된 OpenAI 보고서를 최대 5쪽의 도표 중심 Word 기획서로 내려보냅니다."""
    try:
        document = create_strategy_proposal_document(report.model_dump())
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail={'code': 'PROPOSAL_DOCUMENT_ERROR', 'message': 'Word 기획서를 생성하지 못했습니다.'}) from exc
    return StreamingResponse(
        document,
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers={'Content-Disposition': 'attachment; filename="tourism-strategy-proposal.docx"'},
    )


@app.post('/ai/v1/demo/{region_code}/strategy-proposal.pptx')
async def download_region_strategy_presentation(region_code: str, report: ReportResponse) -> StreamingResponse:
    """같은 구조화 보고서를 지도·그래프·로드맵 중심의 5장 PowerPoint로 내려보냅니다."""
    try:
        presentation = create_strategy_proposal_presentation(report.model_dump())
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail={'code': 'PROPOSAL_PRESENTATION_ERROR', 'message': 'PowerPoint 기획서를 생성하지 못했습니다.'}) from exc
    return StreamingResponse(
        presentation,
        media_type='application/vnd.openxmlformats-officedocument.presentationml.presentation',
        headers={'Content-Disposition': 'attachment; filename="tourism-strategy-proposal.pptx"'},
    )
