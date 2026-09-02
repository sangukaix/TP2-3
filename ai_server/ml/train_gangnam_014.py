"""강남구 관광 데이터 학습을 실행하는 간단한 프로그램입니다.

실행 방법:
    python -m ai_server.ml.train_gangnam_014

이 파일은 학습 방법을 새로 만들지 않습니다.
기존의 train_gangnam_models()를 그대로 호출하므로
모델, 데이터, 평가 방법은 기존 train_gangnam.py와 같습니다.
"""
# train_gangnam_014.py 
# 초보자 수준의 코드로 수정한 파일

from __future__ import annotations

import json

from .gangnam_forecast import train_gangnam_models


def make_summary(metadata: dict) -> dict:
    """학습 결과에서 콘솔에 보여 줄 내용만 골라냅니다."""
    targets = {}

    # 학습한 관광 지표를 하나씩 확인합니다.
    for target_name in metadata["target"]:
        result = metadata["evaluation"][target_name]

        targets[target_name] = {
            "selected_model": result["selected_model"],
            "test_mape_percent": result["selected_model_metrics"]["mape_percent"],
            "baseline_test_mape_percent": result["baseline_metrics"]["mape_percent"],
            "beats_baseline_on_test": result["beats_baseline_on_test"],
        }

    return {
        "model_version": metadata["version"],
        "source_period": metadata["source_period"],
        "test_period": metadata["test_period"],
        "targets": targets,
    }


def main() -> None:
    """모델을 학습하고 평가 결과를 JSON으로 출력합니다."""
    print("강남구 모델 학습을 시작합니다.")

    # 실제 학습과 모델 파일 저장은 기존 함수가 담당합니다.
    metadata = train_gangnam_models()

    # 전체 메타데이터 대신 확인에 필요한 요약만 출력합니다.
    summary = make_summary(metadata)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
