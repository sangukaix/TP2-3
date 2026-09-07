"""승인되지 않았거나 변조된 모델이 로드되지 않는지 확인한다."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import joblib

from data_pipeline.nationwide_ml.artifact_store import ArtifactValidationError, load_model_artifact, sha256_file


class ArtifactStoreTest(unittest.TestCase):
    # 승인 상태와 hash가 모두 맞을 때만 bundle을 반환한다.
    def test_load_valid_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_dir = Path(temp_dir)
            artifact_path = artifact_dir / "model.joblib"
            joblib.dump({"features": ["lag1"], "target": "visitors"}, artifact_path)
            metadata = {
                "decision_status": "decision_usable",
                "artifact_file": "model.joblib",
                "artifact_sha256": sha256_file(artifact_path),
            }
            (artifact_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            bundle, _ = load_model_artifact(artifact_dir)
            self.assertEqual(bundle["target"], "visitors")

    # rejected 모델은 파일이 존재해도 온라인 서비스에서 차단한다.
    def test_reject_unapproved_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_dir = Path(temp_dir)
            artifact_path = artifact_dir / "model.joblib"
            joblib.dump({"features": ["lag1"], "target": "visitors"}, artifact_path)
            metadata = {
                "decision_status": "rejected",
                "artifact_file": "model.joblib",
                "artifact_sha256": sha256_file(artifact_path),
            }
            (artifact_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaises(ArtifactValidationError):
                load_model_artifact(artifact_dir)


if __name__ == "__main__":
    unittest.main()
