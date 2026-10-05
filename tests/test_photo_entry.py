import base64
import io
import json
import re
from unittest.mock import patch
import numpy as np

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from PIL import Image

from core.models import MemberRole
from inventory import recognition
from inventory.models import InventoryLot, Movement


def test_photo():
    image = Image.new("RGB", (100, 100), "red")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


class PhotoEntryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="photo-member", password="test-only-strong-password-2026!")
        MemberRole.objects.create(user=self.user, role="member")

    def test_preview_requires_login_and_csrf_and_never_writes_inventory(self):
        client = Client(enforce_csrf_checks=True)
        payload = json.dumps({"image": test_photo()})
        self.assertEqual(client.post("/api/inventory/recognize/", payload, content_type="application/json", secure=True).status_code, 401)
        client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")
        self.assertEqual(client.post("/api/inventory/recognize/", payload, content_type="application/json", secure=True).status_code, 403)
        page = client.get("/inventory/", secure=True)
        token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', page.content).group(1).decode()
        self.assertContains(page, 'capture="environment"')
        self.assertNotContains(page, "更多信息")
        self.assertContains(page, "保证食材清晰可见，尽量不要遮挡")
        expected = {"ingredient_name": "番茄", "uncertain": True, "engine": "yolo",
                    "candidates": [{"ingredient_name": "番茄", "confidence": .85}]}
        with patch("inventory.recognition._detect", return_value=expected) as model:
            result = client.post("/api/inventory/recognize/", payload, content_type="application/json", secure=True, HTTP_ORIGIN="https://testserver", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), expected)
        self.assertTrue(model.call_args.args[0].startswith(b"\xff\xd8"))
        self.assertEqual(InventoryLot.objects.count(), 0)
        self.assertEqual(Movement.objects.count(), 0)

    def test_bad_images_and_yolo_predictions_are_rejected_or_marked_uncertain(self):
        with self.assertRaises(recognition.RecognitionError):
            recognition.recognise(base64.b64encode(b"not an image").decode())
        with self.assertRaises(recognition.RecognitionError):
            recognition.recognise("not base64")
        output = np.zeros((1, 6, 8400), dtype=np.float32)
        classes = [{"name": "番茄"}, {"name": "苹果"}]
        transform = (100, 100, 6.4, 0, 0)
        self.assertEqual(recognition._postprocess(output, classes, transform)["candidates"], [])
        output[0, :, 0] = [320, 320, 100, 100, .85, .1]
        output[0, :, 1] = [320, 320, 100, 100, .1, .8]
        output[0, :, 2] = [100, 100, 90, 90, .1, .34]
        result = recognition._postprocess(output, classes, transform)
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["ingredient_name"], "番茄")
        self.assertTrue(result["uncertain"])
        output[0, 0, 0] = np.nan
        with self.assertRaises(ValueError):
            recognition._postprocess(output, classes, transform)

    def test_letterbox_and_busy_limit(self):
        photo = recognition._normalise_photo(test_photo())
        tensor, transform = recognition._preprocess(photo)
        self.assertEqual(tensor.shape, (1, 3, 640, 640))
        self.assertEqual(tensor.dtype, np.float32)
        self.assertGreater(tensor[0, 0].mean(), .9)
        self.assertEqual(transform, (100, 100, 6.4, 0, 0))
        self.assertTrue(recognition._INFERENCE_SLOT.acquire(False))
        try:
            with self.assertRaises(recognition.RecognitionError) as error:
                recognition.recognise(test_photo())
            self.assertEqual(error.exception.code, "recognition_busy")
        finally:
            recognition._INFERENCE_SLOT.release()

    def test_minimal_manual_form_keeps_unverified_storage_out_of_today(self):
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")
        page = self.client.get("/inventory/", secure=True)
        request_id = re.search(rb'name="request_id" value="([^"]+)"', page.content).group(1).decode()
        response = self.client.post("/inventory/", {
            "request_id": request_id, "ingredient_name": "白菜", "quantity": "1", "unit": "piece", "location": "fridge",
        }, secure=True)
        self.assertEqual(response.status_code, 302)
        batch = InventoryLot.objects.get()
        self.assertEqual(batch.storage_status, "needs_check")
        self.assertEqual(self.client.get("/api/today/", secure=True).json()["arrange"], [])
        self.assertEqual(Movement.objects.count(), 1)
