"""확정한 12장 기획서 양식에 검증된 보고서 JSON을 채우는 PPT 생성기.

사용자가 직접 지정한 최신 편집형 템플릿의 레이아웃과 네이티브 차트를 유지한다.
관측값은 MySQL/원자료, 자연추세는 저장 ML, 사업 목표는 사용자가 입력한 검토값으로
분리한다. 사용자가 요청한 참고 견적은 가정 단가·수량을 명시하며 성과 예측과
혼합하지 않는다. 전체 출처는 11장부터 같은 레이아웃의 부록으로 이어진다.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path
import re
from typing import Any

from pptx import Presentation
from pptx.chart.data import ChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_LEGEND_POSITION

from . import proposal_presentation_v3 as base
from .presentation_theme import download_images, select_image_sources
from .report_projection import select_report_forecast
from .report_review_status import review_label


PRESENTATION_TEMPLATE_PATH = (
    Path(__file__).resolve().parent / "templates" / "tourism_strategy_12_slide_template_v6.pptx"
)
PRESENTATION_RENDER_VERSION = "pptx-user35-v6-exact-ml-kpi-full-sources-r2"
FINAL_SLIDE_COUNT = 12

BLUE = RGBColor(0x00, 0x4E, 0xA2)
CYAN = RGBColor(0x00, 0xB7, 0xC9)
ORANGE = RGBColor(0xFF, 0x6B, 0x00)
SLATE = RGBColor(0x59, 0x63, 0x6E)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)


def _short_region(value: Any) -> str:
    parts = str(value or "").split()
    return parts[-1] if parts else "선택 지역"


def _format_people(value: Any) -> str:
    number = base._as_float(value)
    if not number:
        return "자료 없음"
    return f"{number / 10_000:,.0f}만 명"


def _format_money(value: Any) -> str:
    number = base._as_float(value)
    if not number:
        return "자료 없음"
    return f"{number / 100_000_000:,.0f}억 원"


def _selected_candidate(report: dict[str, Any]) -> dict[str, Any]:
    decision = report.get("planning_decision") or {}
    selected_id = decision.get("selected_candidate_id")
    return next((candidate for candidate in decision.get("design_candidates") or []
                 if isinstance(candidate, dict) and candidate.get("candidate_id") == selected_id), {})


def _selected_case(report: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """선정한 공식 사례와 그 사례의 지역 적용 판단을 연결한다."""
    decision = report.get("planning_decision") or {}
    candidate = _selected_candidate(report)
    preferred_ids = [*(candidate.get("case_source_ids") or []),
                     *(decision.get("recommended_case_ids") or [])]
    cases = [source for source in report.get("evidence_sources") or []
             if isinstance(source, dict) and str(source.get("source_type") or "").lower()
             in {"benchmark_case", "case_study", "official_case"}]
    by_id = {str(source.get("source_id") or ""): source for source in cases}
    source = next((by_id[source_id] for source_id in preferred_ids if source_id in by_id),
                  cases[0] if cases else {})
    assessment = next((item for item in decision.get("candidate_assessments") or []
                       if isinstance(item, dict) and item.get("case_source_id") == source.get("source_id")), {})
    return source, assessment


def _metric_finding(report: dict[str, Any], *, spending: bool = False) -> dict[str, str]:
    """지표 배열의 순서가 바뀌어도 방문자와 관광소비 금액을 정확히 선택한다."""
    for index, item in enumerate(report.get("observed_findings") or []):
        metric = str(item.get("metric") or "")
        if spending:
            matches = "소비" in metric and any(word in metric for word in ("액", "총액")) and "비중" not in metric
        else:
            matches = "방문" in metric and any(word in metric for word in ("수", "명")) and not any(word in metric for word in ("비율", "증감", "숙박"))
        if matches:
            return base._finding(report, index, "관광소비액" if spending else "방문자 수")
    # Agent가 대표 소견에 증감률만 골랐어도 저장된 월별 사실은 소실되지 않는다.
    from .report_projection import _month, _number
    key = "spending_krw" if spending else "visitors"
    observed = [row for row in report.get("monthly_trend") or []
                if not row.get("is_forecast") and _month(row.get("month"))
                and _number(row.get(key)) is not None]
    if observed:
        row = max(observed, key=lambda item: _month(item["month"]))
        return {"metric": "월 관광소비액" if spending else "월간 순 방문자 수",
                "value": f"{row[key]:,.0f}" + ("원" if spending else "명"),
                "interpretation": f"{_month(row['month'])[:4]}년 {_month(row['month'])[4:]}월 관측값 · 예측과 구분",
                "source": "저장 보고서의 한국관광 데이터랩 월별 원자료"}
    return {"metric": "관광소비액" if spending else "방문자 수", "value": "자료 없음",
            "interpretation": "해당 관측 지표 미제공", "source": "보고서 원자료"}


def _is_offline_sample(report: dict[str, Any]) -> bool:
    """교육·레이아웃 점검용 샘플만 명시적으로 구분한다."""
    return report.get("generation_mode") == "offline_sample"


def _sample_scenario() -> dict[str, Any]:
    """저장 ML이 없을 때 오프라인 샘플에만 쓰는 비사실적 예시값이다.

    실제 보고서에서는 절대 호출하지 않는다. 화면·PPT 레이아웃 검토 때
    'ML 미지원' 차트만 보이지 않도록 하기 위한 더미 시나리오이며,
    슬라이드 안에서 모두 예시값이라고 표기한다.
    """
    visitors = [18_150_000, 18_480_000, 18_730_000]
    spending = [476_000_000_000, 491_000_000_000, 506_000_000_000]
    return {
        "categories": ["9월", "10월", "11월"],
        "baseline_visitors": visitors,
        "baseline_spending": spending,
        "target_visitors": [round(value * 1.02) for value in visitors],
        "target_spending": [round(value * 1.025) for value in spending],
        "visitor_target_pct": 2.0,
        "spending_target_pct": 2.5,
        "visitor_gap": sum(round(value * 1.02) for value in visitors) - sum(visitors),
        "spending_gap": sum(round(value * 1.025) for value in spending) - sum(spending),
        "horizon": 3,
        "has_target": True,
        "source_period": "SAMPLE DATA",
        "period": "2026년 9~11월 예시",
        "notes": ["교육용 더미 시나리오"],
    }


def _scenario_for_display(report: dict[str, Any]) -> tuple[dict[str, Any] | None, bool]:
    """실제 저장 ML을 우선하며, 오프라인 샘플만 명시적 더미값을 허용한다."""
    scenario = base._scenario_rows(report)
    if scenario:
        return scenario, False
    if _is_offline_sample(report):
        return _sample_scenario(), True
    return None, False


def _short_metric(metric: Any) -> str:
    """비교 슬라이드의 좁은 차트 라벨을 읽기 쉬운 말로 바꾼다."""
    text = str(metric or "관측 지표")
    if "방문" in text and any(word in text for word in ("증감", "증가율", "감소율")):
        return "방문자 증감률"
    if "내비게이션" in text:
        return "내비게이션 검색량"
    if "소비" in text and "비중" in text:
        return "관광소비 비중"
    if "소비" in text:
        return "월 관광소비액"
    if "숙박" in text:
        return "평균 숙박일수" if "일" in text and "비율" not in text else "숙박 방문 비율"
    if "체류" in text:
        return "평균 체류시간"
    if "방문" in text:
        return "월 방문자 수"
    return base._compact(text, limit=12)


def _card_value(metric: str, value: str) -> str:
    """이미 단위가 붙은 억원/만원/만명을 원·명으로 오독하지 않는다."""
    text = str(value)
    if re.search(r"[\d.]\s*%", text):
        number = re.search(r"[+-]?\d[\d,]*(?:\.\d+)?", text)
        return _display_percent(float(number[0].replace(',', ''))) if number else text
    if re.search(r"(?:조|억|만)\s*(?:원|명)", text):
        return text
    return base._metric_card_value(metric, text)


def _public_copy(value: Any) -> str:
    """본문에서는 내부 사례 ID만 제거하고 실제 출처는 부록에 보존한다."""
    return re.sub(r"\(?case:[A-Za-z0-9_:-]+\)?", "", str(value or ""))


def _display_percent(value: float, *, signed: bool = False) -> str:
    """1% 이상은 정수, 그 미만은 소수 둘째 자리까지 표시한다."""
    precision = 0 if abs(value) >= 1 else 2
    rounded = Decimal(str(value)).quantize(Decimal("1") if precision == 0 else Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(rounded, f"{'+' if signed else ''}.{precision}f") + "%"


def _visitor_yoy(report: dict[str, Any]) -> float | None:
    """동일 지역의 전년동월 방문 증감률이 있을 때만 상대 지수로 표시한다."""
    for item in report.get("observed_findings") or []:
        metric = str(item.get("metric") or "")
        if "방문" not in metric or "전년" not in metric or not any(word in metric for word in ("증감", "증가", "감소")):
            continue
        if any(word in metric for word in ("소비", "숙박", "비중")):
            continue
        match = re.search(r"([+-]?\d[\d,]*(?:\.\d+)?)\s*%", str(item.get("value") or ""))
        if match:
            value = float(match.group(1).replace(",", ""))
            if value >= -100:
                return value
    return None


def _visual_source_priority(source: dict[str, Any], selected_ids: set[str]) -> tuple[int, int, str]:
    """대표 사진은 관광명소 성격과 전략 선택 여부를 함께 고려해 정렬한다."""
    content_priority = {
        "12": 0,  # 관광지
        "14": 1,  # 문화시설
        "15": 2,  # 축제·공연·행사
        "28": 3,  # 레포츠
        "32": 4,  # 숙박
        "38": 5,  # 쇼핑
        "39": 6,  # 음식점
    }
    source_id = str(source.get("source_id") or "")
    content_type = str(source.get("content_type_id") or "")
    return (
        content_priority.get(content_type, 9),
        0 if source_id in selected_ids else 1,
        str(source.get("title") or ""),
    )


def _set_cell_text(cell: Any, value: str) -> None:
    """표 셀의 원래 문단 서식을 유지한 채 값만 바꾼다."""
    frame = cell.text_frame
    paragraphs = list(frame.paragraphs)
    source_paragraph = paragraphs[0]
    source_font = source_paragraph.runs[0].font if source_paragraph.runs else None
    frame.clear()
    paragraph = frame.paragraphs[0]
    paragraph.alignment = source_paragraph.alignment
    run = paragraph.add_run()
    run.text = value
    if source_font is not None:
        base._copy_run_font(source_font, run.font)


def _set_chart(shape: Any, categories: list[str], series_rows: list[tuple[str, list[float], RGBColor]]) -> None:
    """템플릿 안의 네이티브 차트 데이터와 색상만 교체한다."""
    if not getattr(shape, "has_chart", False):
        raise ValueError("승인 템플릿의 ML 차트가 편집 가능한 PowerPoint 차트가 아닙니다.")
    data = ChartData()
    data.categories = categories or ["미지원"]
    for name, values, _ in series_rows:
        data.add_series(name, values or [0])
    chart = shape.chart
    chart.replace_data(data)
    chart.has_legend = len(series_rows) > 1
    if chart.has_legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
    for series, (_, _, color) in zip(chart.series, series_rows):
        series.format.line.color.rgb = color
        series.format.fill.solid()
        series.format.fill.fore_color.rgb = color
        series.format.line.width = 19050


def _remove_shape(slide: Any, name: str) -> None:
    """선택적 장식·차트가 사실 근거 없이 남지 않도록 도형을 제거한다."""
    shape = next((shape for shape in slide.shapes if shape.name == name), None)
    if shape is not None:
        shape._element.getparent().remove(shape._element)


def _set_optional_text(slide: Any, name: str, value: Any) -> None:
    """새 레이아웃에서 제거된 보조 그래프 라벨은 다시 만들지 않는다."""
    shape = next((shape for shape in slide.shapes if shape.name == name), None)
    if shape is not None:
        base._set_lines(shape, str(value or "").split("\n"))


def _set_text_color(slide: Any, name: str, color: RGBColor) -> None:
    """동적 문단이 추가되어도 강조 패널의 글자색을 동일하게 유지한다."""
    shape = next((shape for shape in slide.shapes if shape.name == name), None)
    if shape is None or not getattr(shape, "has_text_frame", False):
        return
    for paragraph in shape.text_frame.paragraphs:
        for run in paragraph.runs:
            run.font.color.rgb = color


def _trim_to_final_slides(prs: Presentation) -> None:
    """최신 템플릿 뒤에 예비 장이 추가돼도 공개 출력은 12장으로 유지한다."""
    while len(prs.slides) > FINAL_SLIDE_COUNT:
        slide_id = prs.slides._sldIdLst[-1]
        relation_id = slide_id.rId
        prs.part.drop_rel(relation_id)
        prs.slides._sldIdLst.remove(slide_id)


def _populate_cover(prs: Presentation, report: dict[str, Any]) -> None:
    strategy = base._first_strategy(report)
    region = str(report.get("region_name") or "선택 지역")
    short_region = _short_region(region)
    title = base._compact(strategy.get("title") or f"{short_region} 관광 실행 전략", limit=36)
    timeframe = base._compact(strategy.get("timeframe") or "3~6개월", limit=14)
    title_line1, _, title_line2 = base._cover_title_parts(title, timeframe)
    slide = prs.slides[0]
    base._set_text(slide, "security-label", review_label(report))
    base._set_text(slide, "cover-title-line1", title_line1)
    base._set_text(slide, "cover-title-line2", title_line2)
    selected = select_report_forecast(report).get('rows') or []
    project_period = (f"사업기간 {selected[0]['month'][:4]}.{selected[0]['month'][4:]} ~ "
                      f"{selected[-1]['month'][:4]}.{selected[-1]['month'][4:]}" if selected else timeframe)
    base._set_text(slide, "cover-date", project_period)
    base._set_text(slide, "org-title", region)
    owner = "샘플 검토용 / OpenAI 미호출" if report.get("generation_mode") == "offline_sample" else "관광 전략 검토용 / 데이터·AI 기반"
    base._set_text(slide, "org-owner", owner)
    base._set_text(slide, "report-number", f"보고서 출력일 {date.today():%Y-%m-%d}")
    base._set_text(slide, "report-topic", f"{short_region} 관광 활성화\n실행안")

    toc = prs.slides[1]
    base._set_text(toc, "top-brand", f"{region} 관광 전략기획안")
    base._set_text(toc, "top-date", date.today().strftime("%Y. %m. %d"))
    labels = [
        "프로젝트 개요",
        "핵심 기획 실행 모델",
        "방문자·소비액 예측치",
        "유사 지역·사례 비교",
        "4단계 실행 가이드",
        "자연추세·목표 KPI",
        "견적",
        "지속 운영 방안",
        "전체 데이터·출처",
        "맺음말",
    ]
    for index, label in enumerate(labels):
        column, row = (0, index) if index < 5 else (1, index - 5)
        base._set_text(toc, f"toc-{column}-{row}-label", label)


def _populate_project(prs: Presentation, report: dict[str, Any]) -> list[dict[str, Any]]:
    strategy = base._first_strategy(report)
    region = str(report.get("region_name") or "선택 지역")
    findings = [_metric_finding(report), _metric_finding(report, spending=True)]
    extra_index = next((i for i, item in enumerate(report.get('observed_findings') or [])
                        if any(word in str(item.get('metric')) for word in ('증감', '비율', '검색'))), 2)
    findings.append(base._finding(report, extra_index, '관측 지표'))
    slide = prs.slides[2]
    base._set_text(slide, "title", base._compact(strategy.get("title") or f"{_short_region(region)} 관광 실행 프로젝트", limit=32))
    from .report_projection import _month
    observed_months = [_month(row.get('month')) for row in report.get('monthly_trend') or [] if not row.get('is_forecast')]
    current_month = max((month for month in observed_months if month), default='')
    base._set_text(slide, "s3-kicker", "PROJECT CONCEPT" + (f" · 관측 기준 {current_month[:4]}.{current_month[4:]}" if current_month else ''))
    thesis = strategy.get("solution") or report.get("summary") or "지역 여건에 맞는 실행 방식과 운영 범위를 확인합니다."
    if '환급' in thesis and '상품권' in thesis:
        thesis = f"{_short_region(region)} 방문객의 지역 내 지출 일부를 상품권으로 환급하고, 다시 지역에서 사용하도록 유도합니다."
    base._set_text(slide, "s3-thesis", base._compact(thesis, limit=84))
    base._set_text(slide, "s3-desc", base._compact(strategy.get("expected_effect") or "운영 결과를 기록해 보완·확대 여부를 판단합니다.", limit=92))
    for index, finding in enumerate(findings, start=1):
        base._set_text(slide, f"s3-metric-{index}-label", _short_metric(finding["metric"]))
        base._set_text(slide, f"s3-metric-{index}-value", _card_value(finding["metric"], finding["value"]))
    base._set_text(slide, "s3-evidence-title", "이 기획안을 제안한 이유")
    explanation = base._compact(
        _public_copy(strategy.get("comparison_analysis") or strategy.get("problem_to_solve") or findings[2]["interpretation"]),
        limit=110,
    )
    base._set_text(slide, "s3-evidence-body", explanation)

    selected_ids = {
        str(source_id)
        for source_id in (strategy.get("visual_asset_source_ids") or [])
    }
    image_sources = select_image_sources(report, limit=30)
    image_sources.sort(key=lambda source: _visual_source_priority(source, selected_ids))
    downloaded = download_images(image_sources[:5])
    if downloaded:
        source, stream = downloaded[0]
        base._replace_picture(slide, "visitor-photo", stream)
        base._set_text(
            slide,
            "hero-source-label",
            f"사진: {base._compact(source.get('title') or '지역 관광명소', limit=32)} · 한국관광공사 관광 Open API",
        )
        return [source]
    base._set_text(slide, "hero-source-label", "사진: 지역 관광 Open API 사진 미연결 · 템플릿 시각화")
    return []


def _populate_plan_detail(prs: Presentation, report: dict[str, Any]) -> None:
    """선택한 기획을 현장 담당자가 바로 이해할 수 있는 한 장으로 펼친다.

    후보 번호 같은 내부 식별자는 노출하지 않고, 선정 후보의 작동 방식과 사용자 입력
    자원·제약, 실행 단계의 산출물을 각각 분리해 표시한다.
    """
    strategy = base._first_strategy(report)
    candidate = _selected_candidate(report)
    brief = report.get("planning_brief") or {}
    region = str(report.get("region_name") or "선택 지역")
    steps = [step for step in strategy.get("implementation_steps") or [] if isinstance(step, dict)]

    mechanism = candidate.get("mechanism") or strategy.get("solution") or report.get("summary")
    target_users = candidate.get("target_users") or "선택 지역 방문객과 참여 사업자"
    pilot_scope = candidate.get("pilot_scope") or strategy.get("timeframe") or "범위 확정 후 시범 운영"
    prerequisites = candidate.get("prerequisites") or "담당 역할·참여처·안전·정산·측정 기준을 착수 전에 확정합니다."
    resources = " · ".join(
        value.strip()
        for value in (str(brief.get("resources_confirmed") or ""), str(brief.get("resources_possible") or ""))
        if value.strip()
    )
    if not resources:
        resources = prerequisites
    deliverables = [str(step.get("deliverable") or "").strip() for step in steps]
    deliverables = list(dict.fromkeys(value for value in deliverables if value))
    deliverable_text = " · ".join(deliverables[:4]) or "운영안 · 참여처 안내 · 이용 기록 · 성과 검토 보고서"
    operating_actions = " → ".join(
        base._compact(step.get("task") or "", limit=24)
        for step in steps[:3]
        if str(step.get("task") or "").strip()
    ) or "기준선 확정 → 소규모 운영 → 실제 기록 검토"

    slide = prs.slides[3]
    _set_optional_text(slide, 'eyebrow', 'CORE OPERATING MODEL' + (' · 교육용 더미' if _is_offline_sample(report) else ''))
    base._set_text(slide, "title", "핵심 기획 실행 모델")
    blocks = [
        ("WHAT · 무엇을 만드나", base._compact(strategy.get("title") or "지역 맞춤 관광 실행안", limit=24), base._compact(mechanism, limit=56)),
        ("WHO & WHERE · 누구에게", base._compact(target_users, limit=22), f"{base._compact(region, limit=18)} · {base._compact(pilot_scope, limit=30)}"),
        ("HOW · 어떻게 작동하나", "이용 행동을 실제 기록으로 연결", base._compact(operating_actions, limit=58)),
        ("OPERATE · 무엇이 필요한가", "운영 주체·참여처·측정 기준", base._compact(resources, limit=58)),
    ]
    for index, (label, title, body) in enumerate(blocks):
        base._set_text(slide, f"step-{index}-label", label)
        base._set_text(slide, f"step-{index}-title", title)
        base._set_text(slide, f"step-{index}-body", body)
    base._set_text(slide, "value-title", "최종적으로 만들어 내는 것")
    base._set_text(
        slide,
        "value-body",
        f"{base._compact(deliverable_text, limit=86)}\n"
        "관측값·ML 자연추세와 실제 운영 기록을 구분해, 다음 운영 기간에 유지·개선할 항목을 제시합니다.",
    )


def _populate_ml(prs: Presentation, report: dict[str, Any]) -> None:
    slide = prs.slides[4]
    scenario, is_demo = _scenario_for_display(report)
    forecasts = scenario["baseline_visitors"] if scenario else []
    forecast_spending = scenario["baseline_spending"] if scenario else []
    horizon = len(forecasts) or 3
    source_period = "DEMO VALUES" if is_demo else str((report.get("ml_analysis") or {}).get("source_period") or "SAVED MODEL")
    base._set_text(slide, "eyebrow", f"ML FORECAST · {source_period}")
    base._set_text(slide, "title", f"향후 {horizon}개월 방문자·소비액 ML 전망")
    if not scenario:
        base._set_text(slide, "intro", "이 지역은 검증된 저장 ML 전망이 없습니다. 관측 원자료와 공식 근거를 사용하며, 예측 수치는 표시하지 않습니다.")
        base._set_text(slide, "prediction-title", "저장 ML 전망 미지원")
        base._set_text(slide, "prediction-body", "등록 모델이 준비된 뒤에 자연추세와 검토 목표를 분리해 표시합니다.")
        base._set_text(slide, "forecast-chart-note", "저장 ML 없음")
        base._set_text(slide, "forecast-reading-title", "예측값 제공 상태")
        base._set_text(slide, "forecast-reading-body", "저장 모델 미등록 · 원자료와 공식 근거로 판단")
        base._set_text(slide, "consumption-title", "관광소비 전망 미지원")
        base._set_text(slide, "consumption-note", "저장 모델이 없으면 수치를 만들지 않습니다.")
        charts = [shape for shape in slide.shapes if getattr(shape, "has_chart", False)]
        for chart_shape in charts:
            _set_chart(chart_shape, ["미지원"], [("저장 ML 없음", [0], BLUE)])
        return

    selection = select_report_forecast(report)
    observed = [item for item in report.get("monthly_trend") or [] if not item.get("is_forecast")]
    last_observed = observed[-1] if observed else {}
    categories = [base._month_label(last_observed.get("month"))] if last_observed else []
    visitor_values = [round(base._as_float(last_observed.get("visitors")) / 10_000, 1)] if last_observed else []
    categories.extend(scenario["categories"])
    visitor_values.extend(value / 10_000 for value in forecasts)
    spending_values = [value / 100_000_000 for value in forecast_spending]
    intro = (
        "교육용 더미값입니다. 실제 보고서는 과거 월별 원자료를 시간순으로 학습한 저장 ML 자연추세만 표시하며, 정책 효과나 성과를 보장하지 않습니다."
        if is_demo
        else "저장 ML은 과거 월별 원자료를 시간순으로 학습한 자연추세입니다. 정책을 시행하지 않았을 때의 인과적 반사실이나 성과 보장 수치가 아닙니다."
    )
    base._set_text(slide, "intro", intro)
    base._set_text(slide, "prediction-title", f"월 방문자 수: {_format_people(forecasts[0])} → {_format_people(forecasts[-1])}")
    base._set_text(slide, "prediction-body", "교육용 더미 시나리오입니다." if is_demo else f"{selection['period']}의 저장 모델 전망입니다. 운영 성과는 운영일·비운영일의 실제 기록으로 별도 판단합니다.")
    base._set_text(slide, "forecast-chart-note", "단위: 만 명 · 더미값" if is_demo else "단위: 만 명 · ML 전망")
    base._set_text(slide, "forecast-reading-title", "샘플 해석 · 더미 시나리오" if is_demo else "모델 해석 · 예측은 자연추세")
    base._set_text(slide, "forecast-reading-body", "레이아웃 검토용 예시값이며 실제 생성 때 저장 ML로 대체됩니다." if is_demo else "시간순 검증 → 저장 모델 → 사업 기간의 참고 전망")
    base._set_text(slide, "consumption-title", f"월 관광소비액: {_format_money(forecast_spending[0])}")
    base._set_text(slide, "consumption-note", "단위: 억 원 · 더미 예시\n실제 생성 시 저장 ML 전망으로 대체\n운영 성과는 별도 비교로 판단합니다." if is_demo else "단위: 억 원 · 저장 ML 자연추세\n실제 운영 성과는 예측 차이가 아니라\n운영일·비운영일 비교로 판단합니다.")
    charts = [shape for shape in slide.shapes if getattr(shape, "has_chart", False)]
    if len(charts) < 2:
        raise ValueError("승인 템플릿의 방문자·소비액 차트 2개를 찾지 못했습니다.")
    _set_chart(charts[0], categories, [("방문자 수", visitor_values, BLUE)])
    _set_chart(charts[1], scenario["categories"], [("관광소비액", spending_values, CYAN)])


def _populate_comparison(prs: Presentation, report: dict[str, Any]) -> None:
    strategy = base._first_strategy(report)
    decision = report.get("planning_decision") or {}
    candidate = _selected_candidate(report)
    visitors = _metric_finding(report)
    spending = _metric_finding(report, spending=True)
    source, assessment = _selected_case(report)
    slide = prs.slides[5]
    base._set_text(slide, "title", f"유사 지역·사례로 검토한 {_short_region(report.get('region_name'))} 적용 논리")
    comparison = strategy.get("comparison_analysis") or decision.get("diagnosis_summary")
    case_operation = source.get("operating_model") or assessment.get("adaptation") or source.get("summary")
    local_conditions = candidate.get("prerequisites") or decision.get("selection_reason") or strategy.get("kpi")
    blocks = [
        ("선택 지역의 현재 신호", base._compact(visitors["interpretation"], limit=70), "한국관광 데이터랩 관측값"),
        ("동일 기준의 지역 비교", base._compact(_public_copy(comparison) or "기간·지표 정의가 일치하는 비교 근거를 추가 확인해야 합니다.", limit=78), "같은 기간 · 같은 지표 정의"),
        ("공식 사례의 지역 적용", base._compact(case_operation or "선정한 공식 사례의 운영 근거가 보고서에 없습니다. 사례 원문 확인 후 적용 범위를 정합니다.", limit=92), base._compact(source.get("title") or "공식 사례 근거 추가 확인", limit=36)),
        ("선택 지역의 실행 조건", base._compact(local_conditions or "시범 범위·협약·측정 자료가 확보된 뒤 운영 여부를 판단합니다.", limit=92), base._compact(candidate.get("title") or strategy.get("timeframe") or "작게 검증 후 확대", limit=30)),
    ]
    for index, (title, body, plus) in enumerate(blocks):
        base._set_text(slide, f"diff-title-{index}", title)
        base._set_text(slide, f"diff-body-{index}", body)
        base._set_text(slide, f"diff-plus-{index}", plus)
    for name, value in {
        "peer-visit-label": _short_metric(visitors["metric"]),
        "peer-visit-value": _card_value(visitors["metric"], visitors["value"]),
        "peer-spend-label": _short_metric(spending["metric"]),
        "peer-spend-value": _card_value(spending["metric"], spending["value"]),
        "peer-case-label": "공식 사례 → 지역 여건 → 적용 검증",
        "peer-case-program-label": "사례 원리",
        "peer-case-walk-label": "지역 여건",
        "peer-case-spend-label": "적용 검증",
        "peer-pilot-label": "참여 조건과 성과 기록을 착수 전에 확정",
    }.items():
        _set_optional_text(slide, name, value)
    yoy = _visitor_yoy(report)
    chart_shape = next((shape for shape in slide.shapes if shape.name == "peer-visitors-yoy-index"), None)
    if yoy is None:
        for name in ("peer-visitors-yoy-index", "peer-visit-index", "peer-visit-delta"):
            _remove_shape(slide, name)
    else:
        if chart_shape is not None:
            _set_chart(chart_shape, ["전년동월", "현재"], [("같은 지역 방문 지수", [100, round(100 + yoy, 2)], BLUE)])
        _set_optional_text(slide, "peer-visit-index", "전년동월=100")
        _set_optional_text(slide, "peer-visit-delta", f"방문 증감 {_display_percent(yoy, signed=True)}")


def _populate_roadmap(prs: Presentation, report: dict[str, Any]) -> None:
    strategy = base._first_strategy(report)
    steps = list(strategy.get("implementation_steps") or [])[:5]
    while len(steps) < 5:
        steps.append({"schedule": "", "task": "실행 단계", "deliverable": "확인 가능한 산출물"})
    slide = prs.slides[6]
    # The narrow inherited eyebrow stays on one line; full dates are on the
    # cover and individual steps, not squeezed into this decorative label.
    _set_optional_text(slide, "eyebrow", "IMPLEMENTATION ROADMAP")
    base._set_text(slide, "title", "작게 시작해, 기록으로 다음 운영을 결정합니다")
    stage_titles = ("후보 권역·기준선 확정", "참여 업소·동선 설계", "안내·혜택 시범 운영", "주간 기록·운영 조정")
    for index, step in enumerate(steps[:4]):
        base._set_text(slide, f"step-{index}-label", f"STEP {index + 1:02d} · {base._compact(step.get('schedule'), limit=12)}")
        base._set_text(slide, f"step-{index}-title", stage_titles[index])
        base._set_text(slide, f"step-{index}-body", f"{base._compact(step.get('task'), limit=48)}\n산출물: {base._compact(step.get('deliverable'), limit=30)}")
    final_step = steps[4]
    base._set_text(slide, "value-title", f"최종 산출물 · {base._compact(final_step.get('schedule') or '최종 판단', limit=18)}")
    base._set_text(slide, "value-body", f"{base._compact(final_step.get('task'), limit=84)}\n산출물: {base._compact(final_step.get('deliverable'), limit=42)}. 비용·이탈·민원·현장 운영 가능성을 함께 확인해 확대·보완·중단을 판단합니다.")
    _set_text_color(slide, "value-title", WHITE)
    _set_text_color(slide, "value-body", WHITE)


def _populate_kpi(prs: Presentation, report: dict[str, Any]) -> None:
    slide = prs.slides[7]
    scenario, is_demo = _scenario_for_display(report)
    if scenario:
        base_visitors = scenario["baseline_visitors"][0]
        base_spending = scenario["baseline_spending"][0]
        has_target = scenario["has_target"]
        visitor_target = scenario["target_visitors"][0] if has_target else base_visitors
        spending_target = scenario["target_spending"][0] if has_target else base_spending
        visitor_pct = scenario["visitor_target_pct"] if has_target else 0.0
        spending_pct = scenario["spending_target_pct"] if has_target else 0.0
        base._set_text(slide, "title", "샘플 KPI: 더미 ML 예시와 운영 목표" if is_demo else f"{scenario['horizon']}개월 시범 KPI: 자연추세와 목표를 구분")
        base._set_text(slide, "subtitle", "교육용 더미값이며, 실제 보고서는 저장 ML과 운영 기록으로 대체합니다." if is_demo else "목표는 사업 효과를 보장하는 값이 아니라, 담당자가 사전에 정해 운영 결과로 검증할 수준입니다.")
        base._set_text(slide, "audience-pill-0", f"월 방문자 예시 목표 {_display_percent(visitor_pct, signed=True)}" if is_demo else (f"월 방문자 검토 목표 {_display_percent(visitor_pct, signed=True)}" if has_target else "월 방문자 자연추세"))
        base._set_text(slide, "audience-body-0", "더미 자연추세와 운영 목표의 배치 예시입니다." if is_demo else "저장 ML 전망을 기준으로 시범 권역의 실제 유입·이용을 별도 집계합니다.")
        base._set_text(slide, "audience-role-0", "샘플: 실제 저장 ML 등록 뒤 대체" if is_demo else "근거: 월 방문자 원자료·시간순 ML 검증")
        base._set_text(slide, "visit-forecast", f"예시 {_format_people(base_visitors)}" if is_demo else f"자연추세 {_format_people(base_visitors)}")
        base._set_text(slide, "visit-target", f"예시 목표 {_format_people(visitor_target)}" if is_demo else (f"검토 목표 {_format_people(visitor_target)}" if has_target else "운영 후 실제 확인"))
        base._set_text(slide, "audience-pill-1", f"월 관광소비 예시 목표 {_display_percent(spending_pct, signed=True)}" if is_demo else (f"월 관광소비 검토 목표 {_display_percent(spending_pct, signed=True)}" if has_target else "월 관광소비 자연추세"))
        base._set_text(slide, "audience-body-1", "더미 관광소비 추세와 운영 목표의 배치 예시입니다." if is_demo else "관광소비 자연추세와 당일 결제·완료 건당 비용을 분리해 확인합니다.")
        base._set_text(slide, "audience-role-1", "샘플: 실제 저장 ML 등록 뒤 대체" if is_demo else "근거: 관광소비 원자료·운영일 비교")
        base._set_text(slide, "spend-forecast", f"예시 {_format_money(base_spending)}" if is_demo else f"자연추세 {_format_money(base_spending)}")
        base._set_text(slide, "spend-target", f"예시 목표 {_format_money(spending_target)}" if is_demo else (f"검토 목표 {_format_money(spending_target)}" if has_target else "운영 후 실제 확인"))
    else:
        base._set_text(slide, "title", "시범 KPI: 저장 ML이 준비된 뒤 수치 목표를 설정합니다")
        base._set_text(slide, "subtitle", "저장 ML이 없는 지역은 관측값·공식 근거와 실제 운영 기록으로만 판단합니다.")
        for prefix in ("visit", "spend"):
            base._set_text(slide, f"{prefix}-forecast", "ML 미지원")
            base._set_text(slide, f"{prefix}-target", "운영 후 확인")
    base._set_text(slide, "audience-pill-2", "시범 운영 완료율")
    base._set_text(slide, "audience-body-2", "예약·이용·결제를 모두 확인한 참여 건을 기준으로 완료율과 민원을 관리합니다.")
    base._set_text(slide, "audience-role-2", "측정: 예약·입장·결제·민원 기록")
    base._set_text(slide, "foreign-forecast", "기준선 확정")
    base._set_text(slide, "foreign-target", "운영 후 확인")


def _budget_rows(report: dict[str, Any]) -> tuple[str, list[list[str]]]:
    timeframe = base._compact(base._first_strategy(report).get("timeframe") or "시범 운영", limit=12)
    if report.get("generation_mode") == "offline_sample":
        return f"{timeframe} · 총 2.40억 원", [
            ["세부 항목", "예산 비중", "금액"],
            ["프로그램 운영·안전", "45%", "1.08억 원"],
            ["참여 혜택", "25%", "0.60억 원"],
            ["예약·결제 연동", "12%", "0.28억 원"],
            ["홍보·다국어 콘텐츠", "9%", "0.22억 원"],
            ["성과 측정·검토", "6%", "0.14억 원"],
            ["예비비", "3%", "0.08억 원"],
            ["합계", "100%", "2.40억 원"],
        ]
    condition = base._budget_condition(report)
    heading = f"{timeframe} · 비교견적 전" if condition == "희망 예산 미정" else f"{timeframe} · {base._compact(condition, limit=12)}"
    return heading, [
        ["세부 항목", "예산 비중", "금액"],
        ["운영·안전", "확정 전", "비교견적"],
        ["참여 혜택", "확정 전", "단가 확인"],
        ["예약·결제 연동", "확정 전", "개발 견적"],
        ["홍보·콘텐츠", "확정 전", "매체 견적"],
        ["성과 측정·검토", "확정 전", "용역 견적"],
        ["예비비", "확정 전", "범위 확정"],
        ["합계", "—", "계약 전 확정"],
    ]


def _populate_budget(prs: Presentation, report: dict[str, Any]) -> None:
    strategy = base._first_strategy(report)
    slide = prs.slides[8]
    base._set_text(slide, "title", "견적")
    base._set_text(
        slide,
        "intro",
        base._compact(
            strategy.get("budget")
            or "총액은 운영 범위·수량을 먼저 정한 뒤 공식 단가 또는 2개 이상 비교견적으로 확정합니다.",
            limit=92,
        ),
    )
    base._set_text(slide, "dashboard-title", "견적 산출 기준")
    base._set_text(
        slide,
        "dashboard-body",
        "총비용 = 운영일수×인력·안전 단가 + 참여건수×혜택 단가 + 시스템·홍보·평가 견적",
    )
    # 사용자가 삭제를 승인한 두 번째 설명 상자는 구형 템플릿에만 있을 수 있습니다.
    _set_optional_text(slide, "analysis-title", "금액 확정 순서")
    _set_optional_text(
        slide,
        "analysis-body",
        "운영 범위와 수량 확정 → 공식 단가·비교견적 확인 → 부가세·계약 조건 반영",
    )
    heading, rows = _budget_rows(report)
    base._set_text(slide, "budget-table-title", heading)
    base._set_text(slide, "budget-table-note", "※ 표의 금액은 사용자 입력·공식 단가·비교견적이 있을 때만 확정합니다.")
    tables = [shape.table for shape in slide.shapes if getattr(shape, "has_table", False)]
    if len(tables) != 1:
        raise ValueError("승인 템플릿의 견적표를 찾지 못했습니다.")
    table = tables[0]
    if len(table.rows) != len(rows) or len(table.columns) != 3:
        raise ValueError("승인 템플릿의 견적표는 머리글·6개 항목·합계의 8행 3열이어야 합니다.")
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            _set_cell_text(table.cell(row_index, column_index), value)


def _populate_continuation(prs: Presentation, report: dict[str, Any]) -> None:
    """시범 종료 후에도 담당자가 반복 운영할 수 있는 체계를 제시한다."""
    strategy = base._first_strategy(report)
    slide = prs.slides[9]
    base._set_text(slide, "title", "시범사업 이후에도 이렇게 운영합니다")
    base._set_text(slide, "expected-pill", "1 · 검증된 코스 정례 운영")
    base._set_text(
        slide,
        "expected-body",
        base._compact(
            "시범에서 현장 운영 가능성과 실제 이용이 확인된 코스·참여처만 월간 일정으로 정례화합니다.",
            limit=72,
        ),
    )
    base._set_text(slide, "service-pill", "2 · 월별 데이터 개선")
    base._set_text(
        slide,
        "service-body",
        "매월 같은 기준으로 이용·결제·비용·민원을 확인하고, 성과가 약한 구간의 동선·시간·혜택을 조정합니다.",
    )
    _set_optional_text(slide, "service-note", "효과가 약한 구성은 중단하지 않고 원인을 먼저 확인한 뒤 한 요소씩 바꿔 재검증합니다.")
    _set_optional_text(slide, "service-scope", "운영 주기: 월별 점검 · 분기별 참여처 회의")
    base._set_text(slide, "private-pill", "3 · 성과 확인 후 단계적 확장")
    base._set_text(
        slide,
        "private-body",
        "한 권역의 운영 기록이 기준을 충족한 뒤 인접 권역·계절 상품·외국인 안내를 순서대로 연결합니다.",
    )
    _set_optional_text(slide, "private-goal", "확장 조건: 운영 가능성·비용 상한·실제 이용 변화 확인")
    _set_optional_text(slide, "private-flow", "한 권역 → 인접 권역 → 계절·대상별 상품")
    _set_optional_text(slide, "private-scope", "확장 범위: 검증된 요소만 복제")


def _source_titles(report: dict[str, Any], allowed_types: set[str], *, limit: int = 3) -> list[str]:
    rows: list[str] = []
    for source in report.get("evidence_sources") or []:
        if not isinstance(source, dict):
            continue
        source_type = str(source.get("source_type") or "").lower()
        if source_type not in allowed_types:
            continue
        title = base._compact(source.get("title") or source.get("source_id") or "공식 근거", limit=42)
        if title and title not in rows:
            rows.append(title)
        if len(rows) >= limit:
            break
    return rows


def _ml_provenance(report: dict[str, Any]) -> str:
    ml = report.get("ml_analysis") or {}
    if not ml or str(ml.get("status") or "").lower() not in {"available", "ready", "completed"}:
        return "이 지역의 검증된 저장 ML이 없으므로 예측 수치를 만들지 않습니다."
    metrics = ((ml.get("evaluation") or {}).get("metrics") or {})
    selected = []
    for key, label in (("visitors", "방문자"), ("spending_krw", "관광소비")):
        model = str((metrics.get(key) or {}).get("selected_model") or "").strip()
        if model:
            selected.append(f"{label} {base._compact(model, limit=28)}")
    evaluation = ml.get("evaluation") or {}
    periods = " · ".join(
        value for value in (
            str(evaluation.get("validation_period") or "").strip(),
            str(evaluation.get("test_period") or "").strip(),
        ) if value
    )
    lines = [
        f"버전 {base._compact(ml.get('model_version') or '저장 모델', limit=24)} · 학습 {ml.get('source_period') or '메타데이터 확인'}",
    ]
    if selected:
        lines.append("모델 " + " · ".join(selected))
    if periods:
        lines.append(f"시간순 검증 {periods}")
    return "\n".join(lines)


def _provider_provenance(report: dict[str, Any]) -> str:
    if _is_offline_sample(report):
        return "오프라인 레이아웃 샘플 · LLM 및 유료 API를 호출하지 않았습니다."
    label_map = {"qwen": "Qwen", "gemma": "Gemma", "openai": "OpenAI", "local_sources": "저장 근거"}
    providers: list[str] = []
    for event in report.get("agent_trace") or []:
        if not isinstance(event, dict) or event.get("status") == "failed":
            continue
        provider = str(event.get("provider") or "").lower()
        if provider in label_map and label_map[provider] not in providers:
            providers.append(label_map[provider])
    used = " · ".join(providers) if providers else "실행 공급자 기록 없음"
    return (
        f"이번 출력: {used}\n"
        "적용성 비교 → 기획 초안·수정 → 코드 검수 → 독립 최종 검수\n"
        "실제 공급자·모델·성공/실패는 agent_trace에 기록"
    )


def _populate_provenance(prs: Presentation, report: dict[str, Any]) -> None:
    """관측값·ML·공식 사례·LLM의 역할과 출처를 한 장에서 구분한다."""
    slide = prs.slides[10]
    dataset_types = {
        "dataset", "nationwide_dataset", "regional_dataset", "regional_tourism_status",
        "tourism_datalab", "open_api", "official_open_api",
    }
    official_types = {
        "benchmark_case", "case_study", "official_case", "policy", "official_document",
        "rag", "rag_document", "official_web", "official_web_search_candidate",
    }
    datasets = _source_titles(report, dataset_types, limit=2)
    official = _source_titles(report, official_types, limit=2)
    if not datasets:
        datasets = ["보고서 observed_findings·monthly_trend의 원자료 출처"]
    if not official:
        official = ["검수된 공식 사례·정책 근거가 없으면 추가 확인으로 표시"]
    blocks = [
        ("관측 데이터", f"분석기간 {report.get('period') or '출처 메타데이터 확인'}\n" + "\n".join(datasets), "관측값 · MySQL/검증 원자료"),
        ("저장 ML 전망", _ml_provenance(report), "자연추세 · 정책효과 아님"),
        ("공식 사례·웹 근거", "\n".join(official), "공식 URL·검수 상태를 함께 보존"),
        ("AI 기획·검수 기록", _provider_provenance(report), "역할·모델·성공/실패를 trace에 기록"),
    ]
    base._set_text(slide, "title", "근거·데이터·ML·AI 활용 내역")
    for index, (title, body, plus) in enumerate(blocks):
        base._set_text(slide, f"diff-title-{index}", title)
        base._set_text(slide, f"diff-body-{index}", body)
        base._set_text(slide, f"diff-plus-{index}", plus)


def _populate_thanks(prs: Presentation, report: dict[str, Any]) -> None:
    strategy = base._first_strategy(report)
    region = str(report.get("region_name") or "선택 지역")
    slide = prs.slides[11]
    base._set_text(slide, "security-label", "FINAL")
    base._set_text(slide, "cover-title-line1", "감사합니다")
    base._set_text(slide, "cover-title-line2", "데이터로 확인하고, 현장에서 완성합니다")
    base._set_text(slide, "cover-date", "지역 관광 전략기획안")
    base._set_text(slide, "org-title", region)
    base._set_text(slide, "org-owner", "검토·협업용")
    base._set_text(slide, "report-number", "TOUR INSIGHT")
    base._set_text(slide, "report-topic", base._compact(strategy.get("title") or f"{_short_region(region)} 관광 실행안", limit=34))


def _apply_notes(prs: Presentation, report: dict[str, Any], photo_sources: list[dict[str, Any]]) -> None:
    sources = base._all_sources(report)
    selected_case, _ = _selected_case(report)
    methods = [
        "표지의 지역·전략·기간은 검증된 보고서 JSON에서 읽음.",
        "목차는 승인된 12장 기획서 구조를 고정 사용.",
        "관측값은 보고서 observed_findings, 전략 문장은 승인된 전략 JSON을 사용.",
        "선정 후보의 작동 방식·대상·범위·필요 자원과 implementation_steps 산출물을 한 장으로 정리.",
        "저장 ML의 자연추세만 사용하며 정책효과를 예측하지 않음.",
        "지역 비교·공식 사례는 적용성 판단 근거로 사용. 방문 상대 지수는 같은 지역의 관측 전년동월 증감률만 환산하며 정책효과가 아님.",
        "implementation_steps의 일정·행동·산출물을 4단계와 최종 산출물로 정리.",
        "수치 목표는 사용자 검토값이며 실제 운영 결과로 별도 검증.",
        "예산은 수량×단가 또는 비교견적으로 확정하며 근거 없는 총액을 만들지 않음.",
        "시범 종료 후 검증된 요소를 정례화하고 월별 개선과 단계적 확장을 수행하는 운영 제안임.",
        "evidence_sources·ML metadata·agent_trace를 바탕으로 관측·예측·공식 근거·AI 역할을 구분함.",
        "마지막 인사 장. 지역명과 선택 기획 제목만 보고서 JSON에서 읽음.",
    ]
    for index, slide in enumerate(prs.slides):
        extra = photo_sources if index == 2 else ([selected_case] if index == 5 and selected_case else [])
        base._set_notes(slide, [*sources[:6], *extra], methods[index])


def _validate_presentation(prs: Presentation, report: dict[str, Any]) -> None:
    if len(prs.slides) < FINAL_SLIDE_COUNT:
        raise ValueError(f"PowerPoint 필수 12장 구조가 누락되었습니다: {len(prs.slides)}장")
    all_text = "\n".join(shape.text for slide in prs.slides for shape in slide.shapes if getattr(shape, "has_text_frame", False))
    required = ("실행 기획안", "핵심 기획", "ML", "견적", "근거·데이터", "감사합니다")
    missing = [label for label in required if label not in all_text]
    if missing:
        raise ValueError(f"PowerPoint 필수 섹션 누락: {', '.join(missing)}")
    final_text = "\n".join(shape.text for shape in prs.slides[-1].shapes if getattr(shape, "has_text_frame", False))
    if "감사합니다" not in final_text:
        raise ValueError("마지막 슬라이드의 인사말이 유지되지 않았습니다.")
    scenario, _ = _scenario_for_display(report)
    if scenario and len([shape for shape in prs.slides[4].shapes if getattr(shape, "has_chart", False)]) != 2:
        raise ValueError("ML 슬라이드의 네이티브 차트 2개가 유지되지 않았습니다.")
    if len([shape for shape in prs.slides[8].shapes if getattr(shape, "has_table", False)]) != 1:
        raise ValueError("견적 슬라이드의 편집 가능한 표가 유지되지 않았습니다.")
    region = str(report.get("region_name") or "")
    if "강남" not in region and "서울특별시 강남구" in all_text:
        raise ValueError("다른 지역 보고서에 강남구 샘플 문구가 남아 있습니다.")


def create_strategy_proposal_presentation(report: dict[str, Any]) -> BytesIO:
    """승인된 본문+전체 출처 부록을 반환한다. 원 보고서/ML은 변경하지 않는다."""
    from . import proposal_slide_content as content
    if not PRESENTATION_TEMPLATE_PATH.is_file():
        raise ValueError(f"PowerPoint 레이아웃 원본 파일이 없습니다: {PRESENTATION_TEMPLATE_PATH.name}")
    prs = Presentation(str(PRESENTATION_TEMPLATE_PATH))
    _populate_cover(prs, report)
    photo_sources = _populate_project(prs, report)
    _populate_plan_detail(prs, report)
    content.populate_ml(prs, report)
    _populate_comparison(prs, report)
    _populate_roadmap(prs, report)
    content.populate_kpi(prs, report)
    content.populate_budget(prs, report)
    _populate_continuation(prs, report)
    _populate_thanks(prs, report)
    _trim_to_final_slides(prs)
    content.populate_provenance(prs, report)
    content.apply_notes(prs, report, photo_sources)
    _validate_presentation(prs, report)
    output = BytesIO()
    prs.save(output)
    output.seek(0)
    return output
