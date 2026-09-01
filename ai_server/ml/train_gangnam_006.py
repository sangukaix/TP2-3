"""초보자용·서버 호환 강남구 ML 학습 파일.

순서: 데이터 읽기 → Target 학습 → 결과 합치기 → 기존 형식으로 저장

예시:
    .\\backend\\.venv\\Scripts\\python.exe -m ai_server.ml.train_gangnam_004 --target visitors
    .\\backend\\.venv\\Scripts\\python.exe -m ai_server.ml.train_gangnam_004 --target spending_krw
    .\\backend\\.venv\\Scripts\\python.exe -m ai_server.ml.train_gangnam_004 --all

기존 AI 서버가 사용하는 demand_model.joblib과 metadata 파일을 그대로 사용합니다.
아직 학습하지 않은 Target은 전년 같은 달 기준선을 사용합니다.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import joblib

from .evaluation import BASELINE, TEST_MONTHS, VALIDATION_MONTHS, select_and_evaluate
from .gangnam_data import REGION_CODE, write_processed_dataset
from .gangnam_forecast import (
    ARTIFACT_DIRECTORY,
    FEATURE_NAMES,
    FEATURE_NAMES_BY_TARGET,
    MODEL_PATH,
    METADATA_PATH,
    MODEL_VERSION,
    TARGET_LABELS,
    _factory_for,
    _recursive_test,
    _training_frame,
)
from .validation import TARGETS, data_fingerprint


def get_target_names() -> list[str]:
    """--target 또는 --all에서 학습할 Target 목록을 만듭니다."""
    parser = argparse.ArgumentParser(description="강남구 Target별 단계적 ML 학습")
    parser.add_argument("--target", action="append", choices=TARGETS, help="학습할 Target. 여러 번 지정 가능")
    parser.add_argument("--all", action="store_true", help="7개 Target을 모두 학습")
    args = parser.parse_args()
    if args.all:
        return list(TARGETS)
    if args.target:
        return args.target

    # 옵션 없이 실행하면 가장 먼저 방문자 수 하나만 학습합니다.
    return ["visitors"]


def load_old_result() -> tuple[dict, dict]:
    """이전에 저장한 모델을 읽습니다. 처음이면 빈 결과로 시작합니다."""
    if not MODEL_PATH.exists() or not METADATA_PATH.exists():
        return {"models": {}}, {"evaluation": {}}
    return (
        joblib.load(MODEL_PATH),
        json.loads(METADATA_PATH.read_text(encoding="utf-8")),
    )


def train_one_target(monthly_data, target_name: str) -> tuple[object | None, dict]:
    """Target 하나를 학습하고 성능을 평가합니다."""
    features, targets, baseline, months = _training_frame(monthly_data, target_name)
    model, evaluation = select_and_evaluate(
        features, targets, baseline, _factory_for(target_name)
    )
    evaluation["target_period"] = f"{months[0]}~{months[-1]}"
    return model, evaluation


def create_metadata(monthly_data, models: dict, evaluations: dict) -> dict:
    """AI 서버와 ML 학습 페이지가 읽는 정보를 만듭니다."""
    months = _training_frame(monthly_data, "visitors")[3]
    test_start = len(months) - TEST_MONTHS
    validation_start = test_start - VALIDATION_MONTHS
    return {
        "version": MODEL_VERSION,
        "region_code": REGION_CODE,
        "region_name": "서울특별시 강남구",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "data_fingerprint": data_fingerprint(monthly_data),
        "target": TARGET_LABELS,
        "observation_count": len(monthly_data),
        "feature_names": list(FEATURE_NAMES),
        "feature_names_by_target": FEATURE_NAMES_BY_TARGET,
        "train_target_period": f"{months[0]}~{months[validation_start - 1]}",
        "validation_period": f"{months[validation_start]}~{months[test_start - 1]}",
        "test_period": f"{months[test_start]}~{months[-1]}",
        "baseline": BASELINE,
        "evaluation": evaluations,
        "recursive_evaluation": _recursive_test(monthly_data, evaluations),
        "trained_targets": [
            name for name in TARGETS
            if evaluations[name]["selected_model"] != BASELINE
        ],
        "limitations": [
            "Target별로 순서대로 학습하는 방식입니다.",
            "아직 학습하지 않은 Target은 전년 같은 달 기준선을 사용합니다.",
            "예측은 기존 이력의 자연 추세이며 정책 효과나 인과효과가 아닙니다.",
        ],
    }


def save_result(monthly_data, models: dict, evaluations: dict) -> dict:
    """기존 AI 서버가 읽는 파일 두 개를 저장합니다."""
    fingerprint = data_fingerprint(monthly_data)
    artifact = {
        "version": MODEL_VERSION,
        "region_code": REGION_CODE,
        "data_fingerprint": fingerprint,
        "feature_names": FEATURE_NAMES,
        "models": models,
        "latest_observed_month": str(monthly_data["year_month"].iloc[-1]),
    }
    metadata = create_metadata(monthly_data, models, evaluations)
    ARTIFACT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, MODEL_PATH)
    METADATA_PATH.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return metadata


def main() -> None:
    """프로그램을 실행하는 가장 바깥쪽 함수입니다."""
    target_names = get_target_names()
    monthly_data = write_processed_dataset()
    old_artifact, old_metadata = load_old_result()

    # 기존 모델은 유지합니다. 처음 학습하는 Target은 기준선으로 시작합니다.
    models = dict(old_artifact.get("models") or {})
    evaluations = dict(old_metadata.get("evaluation") or {})
    for name in TARGETS:
        if name not in evaluations:
            _, evaluations[name] = train_one_target(monthly_data, name)
            evaluations[name]["selected_model"] = BASELINE
            evaluations[name]["selection_basis"] = "not_trained_yet_baseline_only"
            evaluations[name]["selected_model_metrics"] = evaluations[name]["baseline_metrics"]
        models.setdefault(name, None)

    # 이번 명령에서 지정한 Target만 실제 모델로 교체합니다.
    for name in target_names:
        model, evaluation = train_one_target(monthly_data, name)
        models[name] = model
        evaluations[name] = evaluation
        print(f"[{name}] 선택 모델: {evaluation['selected_model']}")

    metadata = save_result(monthly_data, models, evaluations)
    print(json.dumps({
        "trained_targets": metadata["trained_targets"],
        "model_file": str(MODEL_PATH),
        "metadata_file": str(METADATA_PATH),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()



#############################################################################
# 수정 및 실행을 완료했습니다.
# 이제 다음 명령만 실행해도 방문자 수(visitors) 하나만 학습합니다.
# cd C:\Users\Admin\MBCA\TeamProject\TP2-3
# .\backend\.venv\Scripts\python.exe -m ai_server.ml.train_gangnam_006
# 특정 Target을 명시해도 됩니다.
# .\backend\.venv\Scripts\python.exe -m ai_server.ml.train_gangnam_006 --target visitors
# 실행 결과:
# [visitors] 선택 모델: RandomForestRegressor
# 서버 연동도 확인했습니다.
# AI Dashboard API: HTTP 200
# 지역: 서울특별시 강남구
# 저장 파일은 기존 서버가 사용하는 파일입니다.
# artifacts/ml/11680/demand_model.joblib
# artifacts/ml/11680/demand_model.metadata.json
# 주의할 점은 기존에 학습되어 있던 다른 Target 모델은 그대로 유지된다는 것입니다. 새로 시작할 때 방문자 수만 남기고 싶다면 기존 demand_model.joblib을 백업한 뒤 초기화해야 합니다.


# 오후 3:34








# 그렇게 해주세요.







# 오후 3:35






# 1분 19초 동안 작업함



# 처리 완료했습니다.
# - 기존 7개 Target 모델 파일을 안전하게 백업
# - 저장 모델을 초기화
# - visitors 하나만 새로 학습
# - 나머지 6개 Target은 기준선 상태로 설정
# - AI Dashboard API 확인 완료: HTTP 200
# 현재 학습된 Target:
# visitors
# 기존 모델 백업 위치:
# [backup-before-visitors-only-20260901](C:\\Users\\Admin\\MBCA\\TeamProject\\TP2-3\\artifacts\\ml\\11680\\backup-before-visitors-only-20260901)
# 새 모델 파일:
# artifacts/ml/11680/demand_model.joblib
# artifacts/ml/11680/demand_model.metadata.json
# 이제 브라우저를 새로고침하면 방문자 수는 ML 모델로 표시되고, 나머지 지표는 전년 같은 달 기준선으로 동작합니다.


# 오후 3:36








# 네 코드를 주세요







# 오후 3:38






# 5초 동안 작업함







# 현재 적용한 코드는 아래 파일입니다.
# [train_gangnam_006.py 열기](C:\\Users\\Admin\\MBCA\\TeamProject\\TP2-3\\ai_server\\ml\\train_gangnam_006.py)
# 실행하면 기본적으로 visitors 하나만 학습합니다.
# cd C:\Users\Admin\MBCA\TeamProject\TP2-3
# .\backend\.venv\Scripts\python.exe -m ai_server.ml.train_gangnam_006
# 특정 Target을 학습하려면:
# .\backend\.venv\Scripts\python.exe -m ai_server.ml.train_gangnam_006 --target spending_krw
# 7개 전체 학습:
# .\backend\.venv\Scripts\python.exe -m ai_server.ml.train_gangnam_006 --all
# 현재 코드는 visitors만 학습하고 나머지 Target은 기준선을 사용하도록 설정되어 있습니다.