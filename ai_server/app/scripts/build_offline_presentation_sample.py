"""OpenAI 호출 없이 실제 지역 원자료·저장 ML·공식 사진으로 PPT 샘플을 만듭니다.

실행 예시:
    python -m ai_server.app.scripts.build_offline_presentation_sample \
        --region-code 11680 --region-name "서울특별시 강남구" \
        --output storage/previews/강남구_12장_기획안_오프라인검증본.pptx

이 스크립트는 템플릿과 데이터 연결을 개발자가 반복 검증하기 위한 도구입니다.
OpenAI·5-Agent는 실행하지 않으며 결과에도 오프라인 샘플임을 명확히 표시합니다.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

import httpx

from ..main import ENV_VALUES, build_region_snapshot
from ..offline_sample_report import build_offline_sample_report
from ..proposal_presentation import create_strategy_proposal_presentation
from ..tourism_open_api import TourismOpenApiClient
from ...ml.planning_evidence import build_planning_ml_evidence


def _parser() -> argparse.ArgumentParser:
    """팀원이 VS Code 터미널에서 실행할 명령행 인자를 정의합니다."""
    parser = argparse.ArgumentParser(description='12장 관광 기획안 PPT 오프라인 샘플 생성')
    parser.add_argument('--region-code', default='11680')
    parser.add_argument('--region-name', default='서울특별시 강남구')
    parser.add_argument('--output', required=True)
    parser.add_argument('--without-images', action='store_true')
    return parser


async def _official_images(region_name: str) -> list[dict[str, Any]]:
    """설정된 한국관광공사 Open API에서 사진이 있는 지역 관광자원을 읽습니다."""
    api_key = str(
        ENV_VALUES.get('TOUR_CONTENT_LAB_API_KEY')
        or ENV_VALUES.get('TOUR_API_SERVICE_KEY')
        or ENV_VALUES.get('DATA_GO_KR_SERVICE_KEY')
        or ''
    ).strip()
    if not api_key:
        return []
    base_url = str(
        ENV_VALUES.get('TOUR_INFO_API_BASE_URL')
        or 'https://apis.data.go.kr/B551011/KorService2'
    )
    try:
        resources = await TourismOpenApiClient(
            api_key=api_key,
            base_url=base_url,
        ).collect_region_resources(region_name, limit=30)
    except (httpx.HTTPError, OSError, ValueError):
        # 공공 API가 잠시 끊겨도 텍스트·차트 템플릿 검증은 계속할 수 있습니다.
        return []
    return [item for item in resources if item.get('image_url')]


def build_sample(region_code: str, region_name: str, *, include_images: bool = True) -> bytes:
    """실제 snapshot과 저장 모델을 승인된 12장 템플릿 입력 형식으로 결합합니다."""
    snapshot = build_region_snapshot(region_name)
    report = build_offline_sample_report(region_code, snapshot)
    report['ml_analysis'] = build_planning_ml_evidence(
        region_code,
        region_name,
    ).model_dump(mode='json')

    if include_images:
        resources = asyncio.run(_official_images(region_name))
        report['evidence_sources'].extend(resources)
        report['strategies'][0]['visual_asset_source_ids'] = [
            item['source_id'] for item in resources[:6]
        ]
    return create_strategy_proposal_presentation(report).getvalue()


def main() -> None:
    """출력 폴더를 만든 뒤 재현 가능한 오프라인 검증본을 저장합니다."""
    args = _parser().parse_args()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(
        build_sample(
            args.region_code,
            args.region_name,
            include_images=not args.without_images,
        )
    )
    print(output)


if __name__ == '__main__':
    main()
