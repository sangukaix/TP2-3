"""초보자용 강남구 방문자 수 학습 파일.

이 파일의 핵심 흐름은 다음과 같습니다.

    데이터 준비 → Target 하나 학습 → 기존 결과와 합치기 → 저장

기본 Target은 visitors입니다. 저장 형식은 기존 AI 서버와 같기 때문에,
아직 학습하지 않은 Target은 전년 같은 달 기준선으로 동작합니다.
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


def choose_targets() -> list[str]:
    """사용자가 이번에 학습할 Target을 선택합니다.

    아무 옵션이 없으면 가장 이해하기 쉬운 visitors 하나만 학습합니다.
    """
    parser = argparse.ArgumentParser(description="강남구 Target별 단계적 학습")
    parser.add_argument("--target", action="append", choices=TARGETS, help="학습할 Target")
    parser.add_argument("--all", action="store_true", help="7개 Target 전체 학습")
    args = parser.parse_args()

    if args.all:
        return list(TARGETS)
    return args.target or ["visitors"]


def load_data():
    """원본 ZIP을 읽고 학습용 월별 CSV를 준비합니다."""
    return write_processed_dataset()


def train_one_target(data, target_name: str) -> tuple[object | None, dict]:
    """Target 하나를 학습하고 Validation/Test 성능을 계산합니다."""
    features, target_values, baseline_values, months = _training_frame(data, target_name)
    model_factory = _factory_for(target_name)
    model, evaluation = select_and_evaluate(
        features,
        target_values,
        baseline_values,
        model_factory,
    )
    evaluation["target_period"] = f"{months[0]}~{months[-1]}"
    print(f"[{target_name}] 선택 모델: {evaluation['selected_model']}")
    return model, evaluation


def load_previous_models() -> tuple[dict, dict]:
    """이전에 저장한 모델을 읽습니다. 없으면 빈 사전으로 시작합니다."""
    if not MODEL_PATH.exists() or not METADATA_PATH.exists():
        return {"models": {}}, {"evaluation": {}}

    artifact = joblib.load(MODEL_PATH)
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    return artifact, metadata


def prepare_missing_targets(data, models: dict, evaluations: dict) -> None:
    """학습하지 않은 Target을 기준선 상태로 준비합니다."""
    for target_name in TARGETS:
        if target_name in evaluations:
            models.setdefault(target_name, None)
            continue

        # 평가 형식만 만들고, 실제 모델은 저장하지 않습니다.
        _, baseline_result = train_one_target(data, target_name)
        baseline_result["selected_model"] = BASELINE
        baseline_result["selection_basis"] = "not_trained_yet_baseline_only"
        baseline_result["selected_model_metrics"] = baseline_result["baseline_metrics"]
        evaluations[target_name] = baseline_result
        models[target_name] = None


def build_metadata(data, evaluations: dict, models: dict) -> dict:
    """AI 서버가 예측에 사용할 metadata를 만듭니다."""
    months = _training_frame(data, "visitors")[3]
    test_start = len(months) - TEST_MONTHS
    validation_start = test_start - VALIDATION_MONTHS
    trained_targets = [
        name for name in TARGETS
        if evaluations[name]["selected_model"] != BASELINE
    ]

    return {
        "version": MODEL_VERSION,
        "region_code": REGION_CODE,
        "region_name": "서울특별시 강남구",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "data_fingerprint": data_fingerprint(data),
        "target": TARGET_LABELS,
        "observation_count": len(data),
        "feature_names": list(FEATURE_NAMES),
        "feature_names_by_target": FEATURE_NAMES_BY_TARGET,
        "train_target_period": f"{months[0]}~{months[validation_start - 1]}",
        "validation_period": f"{months[validation_start]}~{months[test_start - 1]}",
        "test_period": f"{months[test_start]}~{months[-1]}",
        "baseline": BASELINE,
        "evaluation": evaluations,
        "recursive_evaluation": _recursive_test(data, evaluations),
        "trained_targets": trained_targets,
        "limitations": [
            "Target을 하나씩 학습할 수 있습니다.",
            "학습하지 않은 Target은 전년 같은 달 기준선을 사용합니다.",
            "예측은 기존 이력의 자연 추세이며 정책 효과가 아닙니다.",
        ],
    }


def save_for_server(data, models: dict, evaluations: dict) -> None:
    """기존 AI 서버가 읽는 모델과 metadata를 저장합니다."""
    fingerprint = data_fingerprint(data)
    artifact = {
        "version": MODEL_VERSION,
        "region_code": REGION_CODE,
        "data_fingerprint": fingerprint,
        "feature_names": FEATURE_NAMES,
        "models": models,
        "latest_observed_month": str(data["year_month"].iloc[-1]),
    }
    metadata = build_metadata(data, evaluations, models)

    ARTIFACT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, MODEL_PATH)
    METADATA_PATH.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n저장 완료")
    print(f"모델: {MODEL_PATH}")
    print(f"정보: {METADATA_PATH}")
    print(f"학습된 Target: {metadata['trained_targets']}")


def main() -> None:
    """프로그램의 실행 순서를 보여주는 함수입니다."""
    target_names = choose_targets()
    data = load_data()
    old_artifact, old_metadata = load_previous_models()

    models = dict(old_artifact.get("models") or {})
    evaluations = dict(old_metadata.get("evaluation") or {})
    prepare_missing_targets(data, models, evaluations)

    for target_name in target_names:
        models[target_name], evaluations[target_name] = train_one_target(data, target_name)

    save_for_server(data, models, evaluations)


if __name__ == "__main__":
    main()
