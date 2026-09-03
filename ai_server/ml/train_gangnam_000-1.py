"""강남구 예측 모델을 명시적으로 재학습하는 CLI 진입점입니다.

실행: python -m ai_server.ml.train_gangnam
"""
#train_gangnam_000-1.py

from __future__ import annotations

import json

from .gangnam_forecast import train_gangnam_models


def main() -> None:
    # 운영 서버가 아니라 개발자·관리자가 원본 갱신 후 직접 실행하는 학습 진입점입니다.
    """학습 결과와 평가 기간을 콘솔에 출력해 팀원이 결과를 바로 확인할 수 있게 합니다."""

    print('train_gangnam_000-1.py\n')
    print('main함수 내부\n')
    print('train_gangnam_models함수 호출\n')
    metadata = train_gangnam_models()

    print('metadata : ', metadata,'\n')
    summary = {
        'model_version': metadata['version'],
        'source_period': metadata['source_period'],
        'test_period': metadata['test_period'],

    
        # Target 목록에서 동적으로 만들기 때문에 모델이 늘어도 CLI 출력이 자동으로 늘어납니다.
        'targets': {
            key: {
                'selected_model': metadata['evaluation'][key]['selected_model'],
                'test_mape_percent': metadata['evaluation'][key]['selected_model_metrics']['mape_percent'],
                'baseline_test_mape_percent': metadata['evaluation'][key]['baseline_metrics']['mape_percent'],
                'beats_baseline_on_test': metadata['evaluation'][key]['beats_baseline_on_test'],
            }
            for key in metadata['target']
        },
    }

    print('summary :', summary,'\n')

    print('python 객체를 json으로 전환 \n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()


# PS C:\Users\Admin\MBCA\TeamProject\TP2-3> & ".\backend\.venv\Scripts\python.exe" -m ai_server.ml.train_gangnam_000-1 >> ".\ai_server\ml\training_result.txt" 2>&1