"""강남구 예측 모델을 명시적으로 재학습하는 CLI 진입점입니다.

실행: python -m ai_server.ml.train_gangnam
"""

from __future__ import annotations

import json

from .gangnam_forecast import train_gangnam_models


def main() -> None:
    # 운영 서버가 아니라 개발자·관리자가 원본 갱신 후 직접 실행하는 학습 진입점입니다.
    """학습 결과와 평가 기간을 콘솔에 출력해 팀원이 결과를 바로 확인할 수 있게 합니다."""
    metadata = train_gangnam_models()
    print(json.dumps({
        'model_version': metadata['version'],
        'source_period': metadata['source_period'],
        'test_period': metadata['test_period'],
        'visitors': metadata['evaluation']['visitors'],
        'spending_krw': metadata['evaluation']['spending_krw'],
        'lodging_nights': metadata['evaluation']['lodging_nights'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
