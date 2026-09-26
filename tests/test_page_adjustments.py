from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from core.models import MemberRole
from inventory import services as inventory_service
from inventory.models import InventoryLot


class PageAdjustmentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="page-member", password="test-only-strong-password-2026!")
        MemberRole.objects.create(user=self.user, role="member")
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")

    def test_today_keeps_only_heading_and_date_note_with_logout_at_top(self):
        response = self.client.get("/", secure=True)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("今天先吃", html)
        self.assertIn("计划日期是安排提醒，不是安全期限。", html)
        self.assertLess(html.index("退出登录"), html.index("<h1>今天先吃</h1>"))
        self.assertNotIn("显示各组前 3 批", html)
        self.assertNotIn("先安排", html)
        self.assertNotIn("需要核对", html)
        self.assertNotIn("today-refresh", html)
        self.assertIn('action="/logout/"', html)

    def test_inventory_hides_raw_package_date_without_erasing_old_value(self):
        created = inventory_service.create_lot(self.user, {
            "request_id": str(uuid4()), "ingredient_name": "番茄", "quantity": "2",
            "unit": "piece", "location": "fridge", "storage_status": "verified",
            "package_date_status": "unknown", "package_date_text": "原包装模糊喷码",
        })
        lot = InventoryLot.objects.get(pk=created["body"]["lot"]["id"])
        self.assertNotContains(self.client.get("/inventory/", secure=True), "包装日期原文")
        self.assertNotContains(self.client.get(f"/inventory/{lot.pk}/edit/", secure=True), "包装日期原文")
        result = self.client.post(f"/inventory/{lot.pk}/edit/", {
            "request_id": str(uuid4()), "version": str(lot.version), "name": "晚餐番茄",
            "location": "fridge", "storage_status": "verified", "status": "active",
            "package_date_status": "unknown", "package_date": "", "planned_use_date": "",
            "purchase_date": "", "opened_date": "", "manual_priority": "false",
        }, secure=True)
        self.assertEqual(result.status_code, 302)
        lot.refresh_from_db()
        self.assertEqual((lot.name, lot.package_date_text), ("晚餐番茄", "原包装模糊喷码"))

    def test_search_results_are_separate_escaped_and_require_input(self):
        listing = self.client.get("/recipes/", secure=True)
        self.assertContains(listing, 'action="/recipes/search-results/"')
        self.assertNotContains(listing, "搜索视频教程")
        results = self.client.get("/recipes/search-results/?find=%E7%95%AA%E8%8C%84%20%E9%B8%A1%E8%9B%8B", secure=True)
        self.assertContains(results, "番茄 鸡蛋 的教程")
        self.assertContains(results, "搜索视频教程")
        self.assertContains(results, 'href="/recipes/"')
        self.assertContains(results, "search.bilibili.com")
        self.assertEqual(self.client.get("/recipes/?find=%E7%95%AA%E8%8C%84", secure=True).status_code, 302)
        self.assertEqual(self.client.get("/recipes/search-results/?find=%20%20", secure=True).status_code, 302)
        self.assertContains(self.client.get("/recipes/", secure=True), "请先输入食材。")
        self.assertEqual(Client().get("/recipes/search-results/?find=%E7%95%AA%E8%8C%84", secure=True).status_code, 302)
        unsafe = self.client.get("/recipes/search-results/", {"find": "<script>alert(1)</script>"}, secure=True)
        self.assertNotIn(b"<script>alert(1)</script>", unsafe.content)
        self.assertContains(unsafe, "&lt;script&gt;alert(1)&lt;/script&gt;")
