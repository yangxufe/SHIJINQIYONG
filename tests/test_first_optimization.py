"""Issue-list regression; all users, photos and provider responses here are synthetic."""

import re
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from core.forms import INVITATION_SALT
from core.models import MemberInvitation, MemberRole
from inventory import services
from inventory.models import InventoryLot, Movement
from meals.models import GenerationTask, RecipeRequest


class FirstOptimizationTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username="optimization-admin", password="Test-only!pW2026-long")
        self.member = get_user_model().objects.create_user(username="optimization-member", password="Test-only!pW2026-long")
        MemberRole.objects.create(user=self.admin, role="admin")
        MemberRole.objects.create(user=self.member, role="member")
        self.client.force_login(self.member, backend="django.contrib.auth.backends.ModelBackend")

    def test_welcome_registration_requires_single_use_invitation_and_django_password(self):
        anonymous = Client()
        self.assertRedirects(anonymous.get("/", secure=True), "/welcome/", fetch_redirect_response=False)
        self.assertContains(anonymous.get("/welcome/", secure=True), 'href="/register/"')
        self.assertNotContains(anonymous.get("/welcome/", secure=True), "家庭成员登录")
        admin = Client()
        admin.force_login(self.admin, backend="django.contrib.auth.backends.ModelBackend")
        page = admin.post("/settings/", {"create_invitation": "yes"}, secure=True)
        invitation = MemberInvitation.objects.get()
        token = signing.dumps(str(invitation.pk), salt=INVITATION_SALT)
        self.assertContains(page, "邀请码")
        payload = {"username": "newmember", "password1": "Test-only!register-7629", "password2": "Test-only!register-7629", "invitation": token}
        bad = anonymous.post("/register/", {**payload, "invitation": "bad"}, secure=True)
        self.assertEqual(bad.status_code, 422)
        result = anonymous.post("/register/", payload, secure=True)
        self.assertRedirects(result, "/login/", fetch_redirect_response=False)
        user = get_user_model().objects.get(username="newmember")
        self.assertTrue(user.check_password(payload["password1"]))
        self.assertEqual(user.member_role.role, "member")
        self.assertFalse(user.is_staff)
        self.assertEqual(anonymous.post("/register/", {**payload, "username": "othermem"}, secure=True).status_code, 422)
        invitation.refresh_from_db()
        self.assertEqual(invitation.used_by_id, user.pk)
        self.assertEqual(InventoryLot.objects.count(), 0)

    def test_expired_invitation_and_csrf_and_member_permission(self):
        invitation = MemberInvitation.objects.create(created_by=self.admin, expires_at=timezone.now()-timedelta(seconds=1))
        token = signing.dumps(str(invitation.pk), salt=INVITATION_SALT)
        payload = {"username": "notcreated", "password1": "Test-only!register-7629", "password2": "Test-only!register-7629", "invitation": token}
        self.assertEqual(Client().post("/register/", payload, secure=True).status_code, 422)
        self.assertEqual(Client(enforce_csrf_checks=True).post("/register/", payload, secure=True).status_code, 403)
        self.assertEqual(self.client.post("/settings/", {"create_invitation": "yes"}, secure=True).status_code, 403)
        self.assertEqual(MemberInvitation.objects.count(), 1)

    def test_all_application_pages_have_header_and_photo_controls_are_separate(self):
        for path in ["/", "/settings/", "/inventory/", "/recipes/", "/recipes/new/", "/recipes/search-results/?find=番茄", "/recipes/workbench/?direct=1", "/recipes/preferences/", "/shopping/"]:
            with self.subTest(path=path):
                response = self.client.get(path, secure=True)
                self.assertContains(response, 'class="header-actions"', count=1)
                self.assertContains(response, 'href="/settings/"')
                self.assertContains(response, 'action="/logout/"', count=1)
        self.assertContains(self.client.get("/", secure=True), "添加菜品")
        page = self.client.get("/inventory/", secure=True)
        self.assertContains(page, 'data-photo-input="food-camera"')
        self.assertContains(page, 'data-photo-input="food-album"')
        self.assertContains(page, '<input id="food-album" type="file" accept="image/*" hidden')
        self.assertNotContains(page, 'for="food-photo"')

    def test_matching_uses_real_usable_inventory_only(self):
        self.assertNotContains(self.client.get("/recipes/", secure=True), "按食材匹配的菜谱")
        self.assertEqual(self.client.get("/api/recipes/", secure=True).json()["recipes"], [])
        self.assertContains(self.client.get("/recipes/library/", secure=True), "番茄炒蛋")
        self.assertNotContains(self.client.get("/recipes/library/", secure=True), "按食材匹配的菜谱")
        services.create_lot(self.member, {"request_id": str(uuid4()), "ingredient_name": "番茄", "quantity": "300", "unit": "g", "location": "fridge", "storage_status": "needs_check", "package_date_status": "not_applicable"})
        self.assertNotContains(self.client.get("/recipes/", secure=True), "按食材匹配的菜谱")
        services.create_lot(self.member, {"request_id": str(uuid4()), "ingredient_name": "番茄", "quantity": "300", "unit": "g", "location": "fridge", "storage_status": "verified", "package_date_status": "not_applicable"})
        page = self.client.get("/recipes/", secure=True)
        self.assertContains(page, "番茄炒蛋")
        self.assertNotContains(page, "西兰花炒鸡肉")
        self.assertTrue(all(row["matched_count"] > 0 for row in self.client.get("/api/recipes/", secure=True).json()["recipes"]))

    def conditions(self):
        return {"request_id": str(uuid4()), "people": "2", "meal_type": "single", "stock_mode": "buy", "taste_mode": "usual", "max_minutes": "30", "spice_max": "1", "skill": "beginner", "goals": ["high_protein", "high_carbohydrate", "low_added_sugar"], "equipment": ["炒锅", "砧板", "菜刀", "碗"], "generate": "yes"}

    @patch.dict("os.environ", {"SHIJIN_RECIPE_PROVIDER": "off"})
    def test_direct_generation_off_is_honest_local_fallback_and_no_writes(self):
        page = self.client.get("/recipes/", secure=True)
        self.assertContains(page, "填写菜谱要求")
        self.assertNotContains(page, "告诉我人数、口味、食材或时间")
        self.assertContains(self.client.get("/recipes/workbench/?direct=1", secure=True), "生成个性化菜谱")
        payload = self.conditions()
        result = self.client.post("/recipes/workbench/confirm/", payload, secure=True, follow=True)
        self.assertContains(result, "已改为本地菜谱匹配")
        self.client.post("/recipes/workbench/confirm/", payload, secure=True)
        self.assertEqual(RecipeRequest.objects.count(), 1)
        self.assertEqual(GenerationTask.objects.count(), 0)
        self.assertEqual(Movement.objects.count(), 0)

    @patch.dict("os.environ", {"SHIJIN_RECIPE_PROVIDER": "ollama", "SHIJIN_RECIPE_MODEL": "test-only-provider"})
    def test_direct_generation_queues_once_without_candidate_intermediate(self):
        payload = self.conditions()
        result = self.client.post("/recipes/workbench/confirm/", payload, secure=True)
        task = GenerationTask.objects.get()
        self.assertEqual(result.url, f"/recipes/generation/{task.pk}/")
        self.client.post("/recipes/workbench/confirm/", payload, secure=True)
        self.assertEqual(GenerationTask.objects.count(), 1)
        self.assertEqual(task.status, "queued")
        self.assertEqual(task.recipe_request.conditions["goals"], ["high_protein", "high_carbohydrate", "low_added_sugar"])
        self.assertEqual(Movement.objects.count(), 0)
