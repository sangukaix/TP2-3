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
    parser.error("--target 또는 --all을 사용하세요.")


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



############################################################
# 현재 구조는 다음처럼 단순합니다.
# get_target_names()
#     ↓
# load_old_result()
#     ↓
# train_one_target()
#     ↓
# create_metadata()
#     ↓
# save_result()
# Target 하나씩 학습:
# .\backend\.venv\Scripts\python.exe -m ai_server.ml.train_gangnam_004 --target visitors
# 다음 Target 학습:
# .\backend\.venv\Scripts\python.exe -m ai_server.ml.train_gangnam_004 --target spending_krw
# 7개 전체 학습:
# .\backend\.venv\Scripts\python.exe -m ai_server.ml.train_gangnam_004 --all
# 사용 가능한 Target은 다음 7개입니다.
# visitors
# spending_krw
# lodging_nights
# lodging_rate_pct
# stay_minutes
# navigation_searches
# lodging_searches
# 기존 서버와의 호환을 위해 모델은 기존 파일에 저장됩니다.
# artifacts/ml/11680/demand_model.joblib
# artifacts/ml/11680/demand_model.metadata.json
# 아직 학습하지 않은 Target은 전년 같은 달 기준선을 사용하므로 Target 하나만 학습해도 서버는 실행할 수 있습니다.
# 문법 검사와 --help 실행은 정상 확인했습니다.