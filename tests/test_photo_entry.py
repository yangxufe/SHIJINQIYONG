import base64
import io
import json
import re
from unittest.mock import patch

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
        self.assertContains(page, "更多信息（日期、批次名、优先顺序）")
        with patch("inventory.recognition._ask_local_model", return_value={"name": "番茄", "uncertain": False}) as model:
            result = client.post("/api/inventory/recognize/", payload, content_type="application/json", secure=True, HTTP_ORIGIN="https://testserver", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), {"ingredient_name": "番茄", "uncertain": False})
        self.assertTrue(model.call_args.args[0].startswith(b"\xff\xd8"))
        self.assertEqual(InventoryLot.objects.count(), 0)
        self.assertEqual(Movement.objects.count(), 0)

    def test_bad_images_and_model_suggestions_are_rejected_or_marked_uncertain(self):
        self.assertEqual(
            recognition._parse_model_response(json.dumps({
                "done": True, "message": {"content": "", "thinking": '{"name":"番茄","uncertain":false}'},
            }).encode()),
            {"name": "番茄", "uncertain": False},
        )
        with self.assertRaises(recognition.RecognitionError):
            recognition.recognise(base64.b64encode(b"not an image").decode())
        with self.assertRaises(recognition.RecognitionError):
            recognition.recognise("not base64")
        with patch("inventory.recognition._ask_local_model", return_value={"name": "", "uncertain": False}):
            self.assertEqual(recognition.recognise(test_photo()), {"ingredient_name": "", "uncertain": True})
        with patch("inventory.recognition._ask_local_model", return_value={"name": "<script>", "uncertain": True}):
            self.assertEqual(recognition.recognise(test_photo())["ingredient_name"], "<script>")
        with patch("inventory.recognition._ask_local_model", return_value={"name": "甲" * 81, "uncertain": False}):
            with self.assertRaises(recognition.RecognitionError):
                recognition.recognise(test_photo())

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
