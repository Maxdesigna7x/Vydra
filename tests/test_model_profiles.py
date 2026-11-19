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
            (root / "prostt5/train_manifest.json").write_text("{}")
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


    def test_batched_faiss_tracks_row_after_checkpoint_writes(self):
        from types import SimpleNamespace
        from vydra_cli import rows_from_records

        class Profile:
            classifier = "faiss"

            def classify(self, embeddings):
                return [str(x) for x in embeddings]

            def for_row(self, predictions, row):
                return predictions[row]

        engine = SimpleNamespace(active_profile=Profile(), release_prost_t5=lambda: None,
                                 run_hierarchy=lambda _, prediction: {"path": [prediction]})
        records = [SimpleNamespace(seq_id=f"q{i}", original_length=1, chunked=False)
                   for i in range(3)]
        for resumed in ([], [{"seq_id": "q0", "path": ["0"]}]):
            with self.subTest(already_saved=len(resumed)):
                checkpoint = SimpleNamespace(predictions=lambda: list(resumed),
                                             save_predictions=lambda rows, index: None,
                                             save_progress=lambda **kwargs: None)
                results = rows_from_records(engine, records, [0, 1, 2], checkpoint=checkpoint)
                self.assertEqual([row["path"] for row in results], [["0"], ["1"], ["2"]])


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
