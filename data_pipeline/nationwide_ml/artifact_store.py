"""저장된 ML artifact의 상태와 hash를 검증한 뒤 안전하게 로드한다."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import joblib


class ArtifactValidationError(RuntimeError):
    """모델 상태·파일·hash가 온라인 사용 조건을 만족하지 않을 때 발생한다."""


# Joblib/Pickle은 코드를 실행할 수 있으므로 내부 학습 파이프라인의 파일만 로드한다.
def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_model_artifact(
    artifact_dir: Path,
    allowed_statuses: tuple[str, ...] = ("decision_usable", "baseline_only"),
) -> tuple[dict[str, Any], dict[str, Any]]:
    """승인 상태와 SHA-256이 일치하는 모델 bundle만 반환한다."""

    metadata_path = artifact_dir / "metadata.json"
    if not metadata_path.is_file():
        raise ArtifactValidationError("metadata.json이 없습니다.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("decision_status") not in allowed_statuses:
        raise ArtifactValidationError(
            f"온라인 사용 불가 모델 상태: {metadata.get('decision_status')}"
        )

    artifact_path = artifact_dir / str(metadata.get("artifact_file", "model.joblib"))
    if not artifact_path.is_file():
        raise ArtifactValidationError("model artifact가 없습니다.")
    actual_hash = sha256_file(artifact_path)
    if actual_hash != metadata.get("artifact_sha256"):
        raise ArtifactValidationError("model artifact SHA-256이 metadata와 다릅니다.")

    bundle = joblib.load(artifact_path)
    if not isinstance(bundle, dict) or "features" not in bundle or "target" not in bundle:
        raise ArtifactValidationError("model bundle 계약이 올바르지 않습니다.")
    return bundle, metadata
