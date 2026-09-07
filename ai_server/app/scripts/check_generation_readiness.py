"""생성 전 원자료·MySQL 비교·저장 모델·사례를 점검합니다. LLM/임베딩 호출은 없습니다.

실행: python -m ai_server.app.scripts.check_generation_readiness --region-code 11680
키·비밀번호·개인 노트북 주소는 출력하지 않습니다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from ai_server.app.agents.case_study_agent import _load_curated_case_cards
from ai_server.app.agents.evidence_agent import allowed_domains
from ai_server.app.case_registry import load_curated_case_registry
from ai_server.app.llm.router import LLMRouter
from ai_server.app.main import build_region_snapshot
from ai_server.app.runtime_env import load_project_env
from ai_server.ml.planning_evidence import build_planning_ml_evidence
from ai_server.ml.region_registry import get_region_pipeline


def inspect_region(region_code: str) -> dict:
    """실제 생성 진입점으로 읽어서 점검용 숫자와 생성 입력이 달라지지 않게 합니다."""
    root = Path(__file__).resolve().parents[3]
    env = load_project_env(root)
    pipeline = get_region_pipeline(region_code)
    snapshot = build_region_snapshot(pipeline.region_name)
    ml = build_planning_ml_evidence(region_code, pipeline.region_name)
    registry = load_curated_case_registry(root / 'data/rag/official_case_studies.jsonl')
    allowed = _load_curated_case_cards(root, allowed_domains(env))
    allowed_ids = {row['source_id'] for row in allowed}
    nationwide = snapshot.get('nationwide_comparison') or {}
    warnings = []
    if ml.status != 'available':
        warnings.append(f'ML 사용 불가: {ml.reason_code}')
    for key, evaluation in ml.evaluation.get('metrics', {}).items():
        if evaluation.get('model_reliability') in {'below_baseline_on_test', 'mixed_recursive_performance'}:
            warnings.append(f"{key}: {evaluation['model_reliability']} — 전망을 단독 선정 근거로 사용하지 마세요.")
    if not nationwide.get('available'):
        warnings.append('MySQL 전국 비교 자료를 현재 읽을 수 없습니다.')
    if len(allowed) < len(registry):
        warnings.append('공식 사례 일부가 허용 도메인 범위 밖입니다. 변경은 승인 후 진행합니다.')
    router = LLMRouter(project_root=root, env_values=env)
    return {
        'region_code': region_code, 'region_name': pipeline.region_name,
        'observation_period': snapshot['period'], 'latest_observed_month': snapshot['latest_month'],
        'ml_status': ml.status, 'model_version': ml.model_version, 'training_source_period': ml.source_period,
        'targets': {key: {'model': value['selected_model'], 'test_mae': value['test_mae'],
                          'baseline_test_mae': value['baseline_test_mae'],
                          'model_reliability': value.get('model_reliability')}
                    for key, value in ml.evaluation.get('metrics', {}).items()},
        'horizon_policy': ml.horizon_policy,
        'nationwide_available': nationwide.get('available', False),
        'nationwide_period': nationwide.get('period'), 'peer_count': len(nationwide.get('peer_regions') or []),
        'official_cases_total': len(registry), 'official_cases_allowed': len(allowed),
        'excluded_case_hosts': sorted({urlparse(row['source_url']).hostname for row in registry if row['source_id'] not in allowed_ids}),
        'llm_mode': router.config['mode'],
        'configured_routes': {task: row['provider'] for task, row in router.public_config()['routes'].items()},
        'effective_routes': {task: row['provider'] for task, row in router.effective_routes().items()},
        'editable_template_exists': (root / 'ai_server/app/templates/tourism_strategy_12_slide_template.pptx').is_file(),
        'warnings': warnings,
        'not_tested': ['유료 기획안 생성 품질', 'LLM 실제 응답', '공식 웹 검색 결과', 'RAG 문서 수'],
    }


def main() -> None:
    """다른 시군구도 등록 후 지역 코드만 바꿔 같은 점검을 재현합니다."""
    # Windows PowerShell의 기본 CP949 출력에서도 지역명·긴 대시가 있는 점검 JSON을
    # 중단 없이 표시한다. 파일·DB·LLM 설정에는 영향을 주지 않는다.
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    except (AttributeError, OSError):
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--region-code', default='11680')
    args = parser.parse_args()
    print(json.dumps(inspect_region(args.region_code), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
