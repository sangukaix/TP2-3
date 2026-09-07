"""문서 다운로드에서도 화면의 검수 상태를 숨기지 않기 위한 공통 표시 규칙입니다."""

from typing import Any


def review_label(report: dict[str, Any]) -> str:
    if report.get('generation_mode') == 'offline_sample':
        return '오프라인 샘플 · Agent 미실행'
    review = report.get('quality_review') or {}
    if review.get('review_stale'):
        return '수정 후 미검수 · 재검토 필요'
    try:
        score = float(review.get('overall_score') or 0)
    except (TypeError, ValueError):
        score = 0
    blocked = any(item.get('severity') in {'critical', 'major'} for item in review.get('issues') or [])
    if review.get('approved') is True and score >= 82 and not blocked:
        return 'AI 검수 통과 · 담당자 확인 필요'
    return '검토용 초안 · 보완 필요'
