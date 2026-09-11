"""강남구 예측 모델을 명시적으로 재학습하는 CLI 진입점입니다.

실행: python -m ai_server.ml.train_gangnam
"""
# Choi_20260831_Version_0002


from __future__ import annotations
# 20260831_Choi_Version_0002 
#    Python에게 함수의 타입 힌트(type hint)를 나중에 해석하도록 하는 기능
#   "함수의 타입 힌트를 지금 당장 해석하지 말고, 나중에 해석해 주세요."


import json

# Python에서 JSON 데이터를 처리하기 위한 표준 라이브러리를 가져오는 것
# Python의 dictionary를 JSON 문자열로 바꾸려면:

from .gangnam_forecast import train_gangnam_models


def main() -> None:
    # 운영 서버가 아니라 개발자·관리자가 원본 갱신 후 직접 실행하는 학습 진입점입니다.
    """학습 결과와 평가 기간을 콘솔에 출력해 팀원이 결과를 바로 확인할 수 있게 합니다."""
    metadata = train_gangnam_models()


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
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
    # 20260901_Choi_Version_0003 
    # 이 명령을 실행하면 train_gangnam.py의 main()이 호출됩니다.
    # .\backend\.venv\Scripts\python.exe -m ai_server.ml.train_gangnam



#####################################################################################
# train_gangnam.py
#     ↓
# train_gangnam_models()
#     ↓
# write_processed_dataset()
#     ↓
# load_gangnam_monthly_demand()
#     ↓
# gangnam_data.py의 함수들이 실행됨

#####################################################################################
# 원본 ZIP 읽기
#     ↓
# 월별 데이터 전처리
#     ↓
# 학습 Feature 생성
#     ↓
# 7개 지표별 모델 학습
#     ↓
# Validation / Test 평가
#     ↓
# 전년 동월 기준선과 비교
#     ↓
# 1~3개월 재귀 테스트
#     ↓
# 모델 파일과 평가 결과 저장


#####################################################################################
# 학습 단계:
# train_gangnam.py
#     ↓
# demand_model.joblib 저장

# 서비스 실행 단계:
# AI 서버 API 요청
#     ↓
# 저장된 joblib 모델 읽기
#     ↓
# predict_future_months()
#     ↓
# 다음 달 또는 향후 여러 달 예측