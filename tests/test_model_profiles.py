import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vydra_core"))
from model_profiles import available_profiles, sha256, verify_manifest


class ModelProfileTests(unittest.TestCase):
    def test_gui_catalog_distinguishes_classifier_bank_from_model(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"VYDRA_PROFILE_ROOT": temporary}):
            root = Path(temporary)
            profile = root / "esm2-8m"
            profile.mkdir()
            (profile / "manifest.json").write_text("{}")
            (root / "prostt5").mkdir()
            (root / "prostt5/m4_manifest.json").write_text("{}")
            models = {model["id"]: model for model in available_profiles()}
            self.assertTrue(models["esm2-8m"]["installed"])
            self.assertFalse(models["esm2-8m"]["faiss"])
            self.assertTrue(models["prostt5"]["faiss"])
            self.assertFalse(models["esm2-35m"]["installed"])

    def test_manifest_rejects_cross_profile_and_altered_reference(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            weights = root / "bank.npy"
            weights.write_bytes(b"expected data")
            (root / "manifest.json").write_text(json.dumps({
                "schema": 1, "profile": "esm2-8m", "dimension": 320,
                "files": {"bank.npy": sha256(weights)},
            }))
            self.assertEqual(verify_manifest(root, "manifest.json", "esm2-8m")["dimension"], 320)
            with self.assertRaisesRegex(ValueError, "Incompatible profile"):
                verify_manifest(root, "manifest.json", "esm2-35m")
            weights.write_bytes(b"modified data")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                verify_manifest(root, "manifest.json", "esm2-8m")


    def test_m4_choice_does_not_apply_to_phage_heads(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from vydra_core import engine
        runtime = SimpleNamespace(id="esm2-8m", classifier="faiss",
                                  predict_m4=Mock(return_value=("0", .7)),
                                  predict=Mock(return_value=("phage", .9)))
        with patch.object(engine, "active_profile", runtime), patch.object(engine, "EMB_DIM", 320):
            import numpy as np
            embedding = np.ones(320, dtype=np.float32)
            self.assertEqual(engine.predict_step(engine.MODEL_NAMES[3], embedding), ("0", .7))
            for i in (0, 1, 2, 4, 5):
                self.assertEqual(engine.predict_step(engine.MODEL_NAMES[i], embedding), ("phage", .9))
            self.assertEqual(runtime.predict_m4.call_count, 1)
            self.assertEqual(runtime.predict.call_count, 5)

    def test_report_timing_keeps_profile_and_classifier(self):
        from report_payloads import update_report_timing

        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary)
            html = report / "informe.html"
            html.write_text('<script type="application/json" data-el="run">{}</script>')
            update_report_timing(report, {"inference_seconds": 2, "model_profile": "esm2-8m",
                                          "classifier": "faiss"})
            self.assertIn('"model_profile": "esm2-8m"', html.read_text())
            self.assertIn('"classifier": "faiss"', html.read_text())


if __name__ == "__main__":
    unittest.main()
