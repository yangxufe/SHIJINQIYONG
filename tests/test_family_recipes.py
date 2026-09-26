import io
import hashlib
import re
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, override_settings
from PIL import Image, PngImagePlugin

from core.models import MemberRole
from core.management.commands.backup_household import create_private_backup
from inventory import services as inventory_service
from inventory.models import BusinessAction, InventoryLot, Movement
from meals import services
from meals.forms import FamilyRecipeForm
from meals.media import media_path
from meals.models import FamilyRecipe, RecipeMedia


def form_data(**changes):
    data = {
        "title": "自家番茄炒蛋", "ingredients_text": "西红柿\n鸡蛋",
        "steps_text": "洗净食材\n炒熟", "category": "家常炒菜",
        "tags_text": "快手, 家常", "source_type": "own",
        "source_url": "", "source_note": "", "request_id": str(uuid4()),
    }
    data.update(changes)
    return data


def create_from_data(user, **changes):
    form = FamilyRecipeForm(form_data(**changes))
    assert form.is_valid(), form.errors
    return services.save_family_recipe(user, form.cleaned_data)


def make_lot(actor, name, **changes):
    payload = {
        "request_id": str(uuid4()), "ingredient_name": name, "quantity": "2",
        "unit": "piece", "location": "fridge", "storage_status": "verified",
        "package_date_status": "not_applicable",
    }
    payload.update(changes)
    result = inventory_service.create_lot(actor, payload)
    return InventoryLot.objects.get(pk=result["body"]["lot"]["id"])


class FamilyRecipeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="cook-one", password="test-only-strong-password-2026!")
        self.other = get_user_model().objects.create_user(username="cook-two", password="test-only-strong-password-2026!")
        self.outsider = get_user_model().objects.create_user(username="outside", password="test-only-strong-password-2026!")
        MemberRole.objects.create(user=self.user, role="member")
        MemberRole.objects.create(user=self.other, role="member")
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def test_private_create_csrf_idempotency_and_escaped_text(self):
        payload = form_data(title="<script>alert(1)</script>")
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")
        page = client.get("/recipes/new/", secure=True)
        token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', page.content).group(1).decode()
        payload["csrfmiddlewaretoken"] = token
        self.assertEqual(client.post("/recipes/new/", payload, secure=True).status_code, 403)
        self.assertEqual(client.post("/recipes/new/", payload, secure=True, HTTP_ORIGIN="https://testserver").status_code, 302)
        self.assertEqual(client.post("/recipes/new/", payload, secure=True, HTTP_ORIGIN="https://testserver").status_code, 302)
        self.assertEqual(FamilyRecipe.objects.count(), 1)
        recipe = FamilyRecipe.objects.get()
        self.assertEqual(recipe.ingredients, ["番茄", "鸡蛋"])
        url = f"/recipes/family-{recipe.pk}/"
        response = client.get(url, secure=True)
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotIn(b"<script>alert(1)</script>", response.content)
        self.assertEqual(Client().get(url, secure=True).status_code, 302)
        other_client = Client()
        other_client.force_login(self.other, backend="django.contrib.auth.backends.ModelBackend")
        self.assertEqual(other_client.get(url, secure=True).status_code, 200)
        outsider_client = Client()
        outsider_client.force_login(self.outsider, backend="django.contrib.auth.backends.ModelBackend")
        self.assertEqual(outsider_client.get(url, secure=True).status_code, 403)
        payload["title"] = "同编号另一道菜"
        self.assertEqual(client.post("/recipes/new/", payload, secure=True, HTTP_ORIGIN="https://testserver").status_code, 409)

    def test_sort_category_tags_and_unsafe_lots(self):
        recipe = create_from_data(self.user)
        make_lot(self.user, "西红柿")
        make_lot(self.user, "鸡蛋", storage_status="needs_check")
        make_lot(self.user, "西兰花", status="suspect")
        listing = services.list_recipes(self.user)
        custom = next(item for item in listing["recipes"] if item["id"] == f"family-{recipe.pk}")
        self.assertEqual((custom["matched_count"], custom["ingredient_count"], custom["missing"]), (1, 2, ["鸡蛋"]))
        self.assertEqual(services.list_recipes(self.user, category="家常炒菜", query="快手")["count"], 3)
        self.assertEqual(services.list_recipes(self.user, category="没有这个分类")["count"], 0)
        self.assertNotContains(self.client.get("/recipes/", secure=True), "search.bilibili.com")
        self.assertContains(self.client.get("/recipes/search-results/?find=%E7%95%AA%E8%8C%84", secure=True), "search.bilibili.com")

    def test_external_link_validation_edit_conflict_and_cook_replay(self):
        bad = FamilyRecipeForm(form_data(source_type="video", source_url="javascript:alert(1)", steps_text=""))
        self.assertFalse(bad.is_valid())
        local_video = FamilyRecipeForm(form_data(source_type="video", source_url="", steps_text=""))
        self.assertTrue(local_video.is_valid(), local_video.errors)
        good = FamilyRecipeForm(form_data(source_type="video", source_url="https://example.org/tutorial", steps_text=""))
        self.assertTrue(good.is_valid(), good.errors)
        recipe = services.save_family_recipe(self.user, good.cleaned_data)
        tomato = make_lot(self.user, "番茄", quantity="1")
        egg = make_lot(self.user, "鸡蛋", quantity="1")
        action = {
            "request_id": str(uuid4()), "recipe_version": "0",
            f"quantity_{tomato.pk}": "1", f"version_{tomato.pk}": "0",
            f"quantity_{egg.pk}": "1", f"version_{egg.pk}": "0",
        }
        recipe_id = f"family-{recipe.pk}"
        self.assertEqual(services.cook_recipe(self.user, recipe_id, action)["status"], 200)
        self.assertEqual(BusinessAction.objects.filter(kind="cook").count(), 1)
        self.assertEqual(Movement.objects.filter(action__kind="cook").count(), 2)
        edit_form = FamilyRecipeForm(form_data(request_id=str(uuid4()), version="0", title="更新后的菜名",
                                               source_type="video", source_url="https://example.org/tutorial", steps_text=""))
        self.assertTrue(edit_form.is_valid(), edit_form.errors)
        services.save_family_recipe(self.other, edit_form.cleaned_data, existing=recipe)
        self.assertEqual(services.cook_recipe(self.user, recipe_id, action)["status"], 200)
        self.assertEqual(BusinessAction.objects.filter(kind="cook").count(), 1)
        with self.assertRaises(inventory_service.InventoryError) as caught:
            services.save_family_recipe(self.user, edit_form.cleaned_data, existing=recipe)
        self.assertEqual(caught.exception.status, 409)

    def test_private_image_upload_is_reencoded_and_video_range_is_authenticated(self):
        recipe = create_from_data(self.user)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        with override_settings(DATA_DIR=Path(temporary.name)):
            image = io.BytesIO()
            metadata = PngImagePlugin.PngInfo()
            metadata.add_text("private", "should-not-survive")
            Image.new("RGB", (100, 100), "red").save(image, format="PNG", pnginfo=metadata)
            upload_url = f"/recipes/family-{recipe.pk}/upload/"
            csrf_client = Client(enforce_csrf_checks=True)
            csrf_client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")
            self.assertEqual(csrf_client.post(upload_url, {
                "request_id": str(uuid4()), "kind": "image", "caption": "",
                "file": SimpleUploadedFile("dish.png", image.getvalue(), content_type="image/png"),
            }, secure=True).status_code, 403)
            response = self.client.post(upload_url, {
                "request_id": str(uuid4()), "kind": "image", "caption": "成品",
                "file": SimpleUploadedFile("dish.png", image.getvalue(), content_type="image/png"),
            }, secure=True)
            self.assertEqual(response.status_code, 302)
            item = RecipeMedia.objects.get(kind="image")
            saved = media_path(item).read_bytes()
            self.assertTrue(saved.startswith(b"\xff\xd8"))
            self.assertNotIn(b"should-not-survive", saved)
            media_url = f"/recipes/family-{recipe.pk}/media/{item.pk}/"
            self.assertEqual(Client().get(media_url, secure=True).status_code, 302)
            response = self.client.get(media_url, secure=True)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Cache-Control"], "no-store")
            self.assertEqual(b"".join(response.streaming_content), saved)
            sample_video = b"\x00\x00\x00\x18ftypisom" + b"0123456789abcdef"
            request_id = str(uuid4())
            upload = lambda: SimpleUploadedFile("clip.mp4", sample_video, content_type="video/mp4")
            self.assertEqual(self.client.post(upload_url, {"request_id": request_id, "kind": "video", "caption": "过程", "file": upload()}, secure=True).status_code, 302)
            self.assertEqual(self.client.post(upload_url, {"request_id": request_id, "kind": "video", "caption": "过程", "file": upload()}, secure=True).status_code, 302)
            self.assertEqual(RecipeMedia.objects.filter(kind="video").count(), 1)
            video = RecipeMedia.objects.get(kind="video")
            video_url = f"/recipes/family-{recipe.pk}/media/{video.pk}/"
            response = self.client.get(video_url, secure=True, HTTP_RANGE="bytes=4-7")
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response["Content-Range"], f"bytes 4-7/{len(sample_video)}")
            self.assertEqual(b"".join(response.streaming_content), b"ftyp")
            self.assertEqual(self.client.get(video_url, secure=True, HTTP_RANGE="bytes=999-").status_code, 416)
            self.assertEqual(self.client.post(upload_url, {"request_id": str(uuid4()), "kind": "video", "caption": "", "file": SimpleUploadedFile("bad.svg", b"<svg></svg>")}, secure=True).status_code, 422)


class PrivateBackupTests(SimpleTestCase):
    def test_database_and_referenced_media_are_copied_and_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "app.sqlite3"
            media_dir = root / "recipe_media"
            media_dir.mkdir()
            key = "a" * 32 + ".mp4"
            payload = b"\x00\x00\x00\x18ftypisomexample"
            (media_dir / key).write_bytes(payload)
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("CREATE TABLE meals_recipemedia(file_key TEXT, sha256 TEXT)")
                connection.execute("INSERT INTO meals_recipemedia VALUES (?, ?)", (key, hashlib.sha256(payload).hexdigest()))
                connection.commit()
            target, count = create_private_backup(database, media_dir, root / "backups")
            self.assertEqual(count, 1)
            self.assertEqual((target / "recipe_media" / key).read_bytes(), payload)
            with closing(sqlite3.connect(target / "app.sqlite3")) as check:
                self.assertEqual(check.execute("PRAGMA integrity_check").fetchone()[0], "ok")
