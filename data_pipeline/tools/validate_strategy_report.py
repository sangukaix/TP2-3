"""기획서 JSON의 저장 전 핵심 품질 규칙을 외부 패키지 없이 검사한다.

개발 초기에는 이 파일로 계약을 검증하고, FastAPI 구현 단계에서는 같은 규칙을
Pydantic 모델과 서비스 계층으로 옮긴다.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any


APPROVAL_SCORE = 82.0
SCORE_WEIGHTS = {
    "evidence": 0.25,
    "execution": 0.25,
    "regional_fit": 0.20,
    "budget_schedule": 0.15,
    "clarity": 0.15,
}


class ReportValidationError(ValueError):
    """한 번에 여러 품질 오류를 사용자에게 보여주기 위한 예외다."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


def _parse_date(value: Any, field: str, errors: list[str]) -> date | None:
    """ISO 날짜를 읽고 실패한 필드명을 오류에 남긴다."""
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        errors.append(f"{field}: YYYY-MM-DD 날짜가 아닙니다.")
        return None


def _required_mapping(report: dict[str, Any], field: str, errors: list[str]) -> dict[str, Any]:
    """필수 객체가 없을 때 후속 검사를 중단하지 않고 빈 객체로 대체한다."""
    value = report.get(field)
    if not isinstance(value, dict):
        errors.append(f"{field}: 필수 객체가 없습니다.")
        return {}
    return value


def _required_list(report: dict[str, Any], field: str, errors: list[str]) -> list[Any]:
    """필수 배열의 자료형을 확인한다."""
    value = report.get(field)
    if not isinstance(value, list):
        errors.append(f"{field}: 필수 배열이 없습니다.")
        return []
    return value


def _validate_region(region: dict[str, Any], errors: list[str]) -> None:
    """공식 Registry 비교 전 최소 지역 식별자 형식을 확인한다."""
    if not str(region.get("region_code", "")).strip():
        errors.append("region.region_code: 지역코드가 없습니다.")
    if not str(region.get("region_name", "")).strip():
        errors.append("region.region_name: 지역명이 없습니다.")
    if not str(region.get("period", "")).strip():
        errors.append("region.period: 분석기간이 없습니다.")


def _validate_claims(claims: list[Any], sources: list[Any], errors: list[str]) -> set[str]:
    """주장 ID와 source ID를 exact membership으로 연결한다."""
    source_by_id = {
        str(item.get("source_id")): item
        for item in sources
        if isinstance(item, dict) and item.get("source_id")
    }
    claim_ids: set[str] = set()

    for index, item in enumerate(claims):
        if not isinstance(item, dict):
            errors.append(f"claims[{index}]: 객체가 아닙니다.")
            continue
        claim_id = str(item.get("claim_id", ""))
        if not claim_id:
            errors.append(f"claims[{index}].claim_id: 값이 없습니다.")
            continue
        if claim_id in claim_ids:
            errors.append(f"claims[{index}].claim_id: 중복 ID {claim_id}")
        claim_ids.add(claim_id)

        source_ids = item.get("source_ids", [])
        if not isinstance(source_ids, list):
            errors.append(f"claims[{index}].source_ids: 배열이 아닙니다.")
            continue
        missing = [source_id for source_id in source_ids if str(source_id) not in source_by_id]
        if missing:
            errors.append(f"claims[{index}].source_ids: 존재하지 않는 source ID {missing}")

        claim_type = item.get("claim_type")
        source_types = {
            source_by_id[str(source_id)].get("source_type")
            for source_id in source_ids
            if str(source_id) in source_by_id
        }
        if claim_type == "observed" and "dataset" not in source_types:
            errors.append(f"claims[{index}]: observed 주장은 dataset source가 필요합니다.")
        if claim_type == "forecast" and "model" not in source_types:
            errors.append(f"claims[{index}]: forecast 주장은 model source가 필요합니다.")
        if claim_type == "official_case" and not source_types.intersection({"rag", "web"}):
            errors.append(f"claims[{index}]: official_case 주장은 rag 또는 web source가 필요합니다.")

    return claim_ids


def _validate_strategy(strategy: dict[str, Any], claim_ids: set[str], source_ids: set[str], errors: list[str]) -> None:
    """5단계 일정과 보고서 내부 참조를 결정적으로 검사한다."""
    start_date = _parse_date(strategy.get("start_date"), "strategy.start_date", errors)
    end_date = _parse_date(strategy.get("end_date"), "strategy.end_date", errors)
    if start_date and end_date and start_date > end_date:
        errors.append("strategy: 시작일이 종료일보다 늦습니다.")

    problem_ids = strategy.get("problem_claim_ids", [])
    if not isinstance(problem_ids, list) or not problem_ids:
        errors.append("strategy.problem_claim_ids: 문제 근거가 없습니다.")
    else:
        missing = [claim_id for claim_id in problem_ids if str(claim_id) not in claim_ids]
        if missing:
            errors.append(f"strategy.problem_claim_ids: 존재하지 않는 claim ID {missing}")

    case_ids = strategy.get("solution_case_ids", [])
    if not isinstance(case_ids, list):
        errors.append("strategy.solution_case_ids: 배열이 아닙니다.")
    else:
        missing = [source_id for source_id in case_ids if str(source_id) not in source_ids]
        if missing:
            errors.append(f"strategy.solution_case_ids: 존재하지 않는 source ID {missing}")

    steps = strategy.get("steps", [])
    if not isinstance(steps, list) or len(steps) != 5:
        errors.append("strategy.steps: 실행 단계는 정확히 5개여야 합니다.")
        return
    step_numbers = [item.get("step") for item in steps if isinstance(item, dict)]
    if step_numbers != [1, 2, 3, 4, 5]:
        errors.append("strategy.steps: 단계 번호는 1,2,3,4,5 순서여야 합니다.")

    previous_start: date | None = None
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"strategy.steps[{index}]: 객체가 아닙니다.")
            continue
        step_start = _parse_date(step.get("start_date"), f"strategy.steps[{index}].start_date", errors)
        step_end = _parse_date(step.get("end_date"), f"strategy.steps[{index}].end_date", errors)
        if step_start and step_end and step_start > step_end:
            errors.append(f"strategy.steps[{index}]: 시작일이 종료일보다 늦습니다.")
        if start_date and step_start and step_start < start_date:
            errors.append(f"strategy.steps[{index}]: 사업 시작일보다 빠릅니다.")
        if end_date and step_end and step_end > end_date:
            errors.append(f"strategy.steps[{index}]: 사업 종료일보다 늦습니다.")
        # 병렬 실행은 허용하되 단계의 시작 순서가 거꾸로 되는 경우만 막는다.
        if previous_start and step_start and step_start < previous_start:
            errors.append(f"strategy.steps[{index}]: 앞 단계보다 먼저 시작할 수 없습니다.")
        if step_start:
            previous_start = step_start
        if not str(step.get("task", "")).strip():
            errors.append(f"strategy.steps[{index}].task: 실행 내용이 없습니다.")
        if not str(step.get("deliverable", "")).strip():
            errors.append(f"strategy.steps[{index}].deliverable: 산출물이 없습니다.")

    for index, kpi in enumerate(strategy.get("kpis", [])):
        if not isinstance(kpi, dict):
            errors.append(f"strategy.kpis[{index}]: 객체가 아닙니다.")
            continue
        if str(kpi.get("source_id", "")) not in source_ids:
            errors.append(f"strategy.kpis[{index}].source_id: 등록된 source가 아닙니다.")


def _validate_quality(report: dict[str, Any], review: dict[str, Any], errors: list[str]) -> None:
    """Reviewer 차원 점수와 최종 상태의 일관성을 검사한다."""
    dimensions = review.get("dimension_scores")
    if not isinstance(dimensions, dict):
        errors.append("quality_review.dimension_scores: 객체가 없습니다.")
        return
    try:
        calculated = sum(float(dimensions[name]) * weight for name, weight in SCORE_WEIGHTS.items())
        recorded = float(review.get("overall_score"))
    except (KeyError, TypeError, ValueError):
        errors.append("quality_review: 차원 점수 또는 총점이 올바르지 않습니다.")
        return

    if abs(calculated - recorded) > 0.05:
        errors.append(f"quality_review.overall_score: 서버 계산값 {calculated:.2f}와 다릅니다.")

    critical_issues = review.get("critical_issues", [])
    should_approve = calculated >= APPROVAL_SCORE and not critical_issues and report.get("generation_mode") == "openai"
    if bool(review.get("approved")) != should_approve:
        errors.append("quality_review.approved: 점수·critical issue·생성 모드와 일치하지 않습니다.")
    expected_status = "approved" if should_approve else "needs_review"
    if report.get("status") not in {expected_status, "failed"}:
        errors.append(f"status: 현재 검수 결과에서는 {expected_status} 또는 failed여야 합니다.")


def validate_report(report: dict[str, Any]) -> None:
    """저장 전에 호출하는 공개 검증 함수다."""
    errors: list[str] = []
    if report.get("schema_version") != "1.0":
        errors.append("schema_version: 1.0이어야 합니다.")
    if report.get("generation_mode") not in {"openai", "offline_sample"}:
        errors.append("generation_mode: openai 또는 offline_sample이어야 합니다.")

    region = _required_mapping(report, "region", errors)
    strategy = _required_mapping(report, "strategy", errors)
    review = _required_mapping(report, "quality_review", errors)
    _required_mapping(report, "provenance", errors)
    claims = _required_list(report, "claims", errors)
    sources = _required_list(report, "sources", errors)

    _validate_region(region, errors)
    claim_ids = _validate_claims(claims, sources, errors)
    source_ids = {
        str(item.get("source_id"))
        for item in sources
        if isinstance(item, dict) and item.get("source_id")
    }
    _validate_strategy(strategy, claim_ids, source_ids, errors)
    _validate_quality(report, review, errors)

    if errors:
        raise ReportValidationError(errors)


def main() -> int:
    """CLI에서 JSON 파일 하나를 검사하고 명확한 종료코드를 반환한다."""
    parser = argparse.ArgumentParser(description="STAY-UP AI 기획서 JSON 품질 검사")
    parser.add_argument("report", type=Path, help="검사할 기획서 JSON 경로")
    args = parser.parse_args()

    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise ReportValidationError(["root: JSON 객체가 아닙니다."])
        validate_report(report)
    except (OSError, json.JSONDecodeError, ReportValidationError) as exc:
        print("INVALID")
        if isinstance(exc, ReportValidationError):
            for error in exc.errors:
                print(f"- {error}")
        else:
            print(f"- {exc}")
        return 1

    print("VALID")
    print(f"- checked_at: {datetime.now().isoformat(timespec='seconds')}")
    print(f"- report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
