import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from inventory import recognition
from scripts import install_yolo_food


class ModelInstallationTests(SimpleTestCase):
    def test_copy_checksum_idempotency_and_preserve_custom_model(self):
        # Deliberately fake bytes test installation only, never detector accuracy.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            assets = root / "model_assets"
            assets.mkdir()
            data = root / "data"
            payload = b"test-only-not-a-real-onnx-model"
            (assets / "yolo-food.onnx").write_bytes(payload)
            (assets / "yolo-food.json").write_text(json.dumps({"sha256": hashlib.sha256(payload).hexdigest()}))
            with patch.object(install_yolo_food, "ROOT", root):
                first = install_yolo_food.install(data)
                self.assertEqual(install_yolo_food.install(data), first)
                (data / "models" / "yolo-food.onnx").write_bytes(b"custom")
                with self.assertRaises(ValueError):
                    install_yolo_food.install(data)
                self.assertEqual((data / "models" / "yolo-food.onnx").read_bytes(), b"custom")
                (assets / "yolo-food.onnx").write_bytes(b"corrupt")
                with self.assertRaises(ValueError):
                    install_yolo_food.install(data)

    def test_missing_model_degrades_and_url_configuration_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(DATA_DIR=Path(folder)), patch.object(recognition, "_SESSION", None):
            with patch.dict("os.environ", {}, clear=True):
                with self.assertRaises(recognition.RecognitionError) as error:
                    recognition._load_detector()
                self.assertEqual(error.exception.code, "recognition_not_configured")
            with patch.dict("os.environ", {"SHIJIN_YOLO_MODEL": "https://example.invalid/model.onnx"}):
                with self.assertRaises(recognition.RecognitionError) as error:
                    recognition._load_detector()
                self.assertEqual(error.exception.code, "recognition_not_configured")
