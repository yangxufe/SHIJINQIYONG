import json
import re
from datetime import date, datetime, timezone as py_timezone
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from core.models import HouseholdSettings, MemberRole
from inventory import services, today
from inventory.models import InventoryLot


def member(username="member"):
    user = get_user_model().objects.create_user(username=username, password="test-only-strong-password-2026!")
    MemberRole.objects.create(user=user, role="member")
    return user


def lot(actor, name, **changes):
    payload = {
        "request_id": str(uuid4()), "ingredient_name": name, "name": name,
        "quantity": "2", "unit": "piece", "location": "fridge",
        "storage_status": "verified", "package_date_status": "not_applicable",
    }
    payload.update(changes)
    result = services.create_lot(actor, payload)
    return InventoryLot.objects.get(pk=result["body"]["lot"]["id"])


class TodayAndMobileTests(TestCase):
    def setUp(self):
        self.user = member()

    def test_empty_today_keeps_minimal_home_and_other_pages(self):
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")
        page = self.client.get("/", secure=True)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "计划日期是安排提醒，不是安全期限。")
        self.assertContains(page, 'aria-label="主要页面"')
        self.assertEqual(self.client.get("/api/today/", secure=True).json()["arrange"], [])
        self.assertNotContains(self.client.get("/recipes/", secure=True), "按食材匹配的菜谱")
        self.assertContains(self.client.get("/shopping/", secure=True), "清单还没有待办")
        self.assertEqual(self.client.get("/api/recipes/", secure=True).status_code, 200)

    def test_priority_order_and_review_exclusion(self):
        today_date = date.today()
        early = lot(self.user, "早录入")
        planned = lot(self.user, "有计划", planned_use_date=today_date.isoformat())
        priority = lot(self.user, "手动优先", manual_priority=True)
        lot(self.user, "后录入")
        lot(self.user, "疑似变质", status="suspect", manual_priority=True)
        lot(self.user, "待核对", storage_status="needs_check", manual_priority=True)
        lot(self.user, "包装已过", package_date_status="known", package_date="2000-01-01", manual_priority=True)
        arranged = today.get_today(self.user)
        self.assertEqual([item["id"] for item in arranged["arrange"]], [priority.pk, planned.pk, early.pk])
        self.assertEqual(arranged["arrange_count"], 4)
        self.assertEqual(arranged["needs_review_count"], 3)
        self.assertEqual({item["name"] for item in arranged["needs_review"]}, {"疑似变质", "待核对", "包装已过"})

    def test_packaging_not_applicable_is_not_unknown_storage(self):
        fresh = lot(self.user, "无包装鲜蔬", package_date_status="not_applicable", storage_status="verified")
        result = today.get_today(self.user)
        self.assertEqual(result["arrange"][0]["id"], fresh.pk)
        self.assertEqual(result["needs_review"], [])

    def test_household_timezone_changes_today_and_overdue_wording(self):
        HouseholdSettings.objects.create(time_zone="Pacific/Kiritimati")
        lot(self.user, "今天计划", planned_use_date="2026-01-01")
        with patch("django.utils.timezone.now", return_value=datetime(2026, 1, 1, 13, 0, tzinfo=py_timezone.utc)):
            result = today.get_today(self.user)
        self.assertEqual((result["today"], result["time_zone"]), ("2026-01-02", "Pacific/Kiritimati"))
        self.assertIn("计划已过", result["arrange"][0]["reason"])
        self.assertNotIn("变质", result["arrange"][0]["reason"])

    def test_priority_edit_is_versioned_and_invalid_boolean_rejected(self):
        batch = lot(self.user, "番茄")
        changed = services.edit_lot(self.user, batch.pk, {"request_id": str(uuid4()), "version": 0, "manual_priority": "true"})
        self.assertTrue(changed["body"]["lot"]["manual_priority"])
        self.assertEqual(changed["body"]["lot"]["version"], 1)
        with self.assertRaises(services.InventoryError):
            services.edit_lot(self.user, batch.pk, {"request_id": str(uuid4()), "version": 1, "manual_priority": "yes"})
        batch.refresh_from_db()
        self.assertEqual((batch.manual_priority, batch.version), (True, 1))

    def test_search_is_server_filtered_bounded_and_escaped(self):
        lot(self.user, "<script>alert(1)</script>")
        lot(self.user, "苹果")
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")
        response = self.client.get("/api/inventory/?q=苹果", secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["name"] for item in response.json()["items"]], ["苹果"])
        html = self.client.get("/inventory/?q=script", secure=True).content.decode()
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertEqual(self.client.get("/api/inventory/?q=" + "甲" * 81, secure=True).status_code, 422)

    def test_no_js_form_and_request_lookup_require_same_actor(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")
        page = client.get("/inventory/", secure=True)
        csrf = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', page.content).group(1).decode()
        request_id = str(uuid4())
        response = client.post("/inventory/", data={
            "csrfmiddlewaretoken": csrf, "request_id": request_id,
            "ingredient_name": "番茄", "quantity": "3", "unit": "piece", "location": "fridge",
            "storage_status": "verified", "package_date_status": "not_applicable", "manual_priority": "true",
        }, secure=True, HTTP_ORIGIN="https://testserver")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(InventoryLot.objects.get().manual_priority)
        lookup = client.get(f"/api/actions/by-request/{request_id}/", secure=True)
        self.assertEqual(lookup.status_code, 200)
        self.assertEqual(lookup.json()["original_status"], 201)
        self.assertEqual(client.get(f"/api/actions/by-request/{uuid4()}/", secure=True).status_code, 404)
        other = member("other")
        client.force_login(other, backend="django.contrib.auth.backends.ModelBackend")
        self.assertEqual(client.get(f"/api/actions/by-request/{request_id}/", secure=True).status_code, 404)
        anonymous = Client()
        self.assertEqual(anonymous.get("/api/today/", secure=True).status_code, 401)
