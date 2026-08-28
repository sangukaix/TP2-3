"""등록된 여러 시군구를 순서대로 재학습하는 관리용 CLI입니다.

실행: python -m ai_server.ml.scripts.train_regions --all
"""

from __future__ import annotations

import argparse
import json

from ..region_registry import list_region_pipelines
from ..region_service import train_region_demand


def main() -> None:
    # --all은 등록표의 모든 지역을 순서대로 학습합니다.
    # --region-code를 여러 번 쓰면 필요한 시군구만 골라 다시 학습할 수 있습니다.
    """지역별 실패를 분리해 한 지역 원본 오류가 전체 재학습을 멈추지 않게 합니다."""
    parser = argparse.ArgumentParser(description='등록된 지역 관광수요 모델을 재학습합니다.')
    parser.add_argument('--region-code', action='append', default=[], help='재학습할 시군구 코드. 여러 번 입력 가능')
    parser.add_argument('--all', action='store_true', help='등록된 모든 시군구를 재학습')
    args = parser.parse_args()
    codes = args.region_code or ([item.region_code for item in list_region_pipelines()] if args.all else [])
    if not codes:
        parser.error('--region-code 또는 --all 중 하나가 필요합니다.')
    # 배치 결과를 JSON으로 출력하면 팀원이 실행 로그에서 성공·실패 지역을 한눈에 확인할 수 있습니다.
    results = []
    for code in codes:
        try:
            results.append({'region_code': code, 'status': 'completed', 'metadata': train_region_demand(code)})
        except Exception as exc:  # 배치 작업은 실패 지역을 기록하고 다음 지역으로 진행합니다.
            results.append({'region_code': code, 'status': 'failed', 'error': str(exc)})
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
