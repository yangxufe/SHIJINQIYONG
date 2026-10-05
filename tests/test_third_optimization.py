"""Third issue-list journeys against isolated synthetic data."""
import json
import re
from datetime import date
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from core.models import MemberRole
from inventory import services
from inventory.models import BusinessAction, InventoryLot, Movement
from meals import services as recipes
from tests.test_family_recipes import create_from_data


class ThirdOptimizationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="third-user", password="Synthetic-third!2026")
        MemberRole.objects.create(user=self.user, role="member")
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")
        page = self.client.get("/inventory/", secure=True)
        self.token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', page.content).group(1).decode()

    def payload(self, **changes):
        result = {"request_id": str(uuid4()), "ingredient_name": "番茄", "quantity": "3", "unit": "piece", "location": "fridge", "shelf_life_mode": "date", "package_date": ""}
        result.update(changes)
        return result

    def post_api(self, payload):
        return self.client.post("/api/inventory/", json.dumps(payload), content_type="application/json", secure=True, HTTP_ORIGIN="https://testserver", HTTP_X_CSRFTOKEN=self.token)

    def post_form(self, path, payload):
        return self.client.post(path, {**payload, "csrfmiddlewaretoken": self.token}, secure=True, HTTP_ORIGIN="https://testserver")

    def test_separate_list_navigation_search_permissions_and_escaping(self):
        self.post_api(self.payload(ingredient_name="<img src=x onerror=alert(1)>"))
        self.post_api(self.payload(ingredient_name="苹果"))
        home = self.client.get("/", secure=True).content.decode()
        titles = [home.index(f"<h2>{name}</h2>") for name in ("添加菜品", "食材列表", "查看菜谱", "采购计划")]
        self.assertEqual(titles, sorted(titles))
        add = self.client.get("/inventory/", secure=True)
        self.assertNotContains(add, 'id="lots-list"')
        self.assertNotContains(add, "更多信息")
        for name in ("ingredient_name", "quantity", "unit", "location"):
            self.assertRegex(add.content.decode(), rf'<(?:input|select)[^>]*name="{name}"[^>]*required')
        self.assertContains(add, 'class="required-mark"', count=4)
        listing = self.client.get("/inventory/list/?q=img", secure=True)
        self.assertContains(listing, "&lt;img src=x onerror=alert(1)&gt;")
        self.assertNotContains(listing, "<img src=x")
        self.assertNotContains(listing, "苹果")
        self.assertNotContains(listing, "保存批次")
        self.assertEqual(listing.context["page"]["count"], 1)
        self.assertRedirects(self.client.get("/inventory/?q=apple&page=1", secure=True), "/inventory/list/?q=apple&page=1", fetch_redirect_response=False)
        self.assertEqual(self.client.get("/inventory/list/", {"q": "字" * 81}, secure=True).status_code, 422)
        self.assertEqual(Client().get("/inventory/list/", secure=True).status_code, 302)
        outsider = get_user_model().objects.create_user(username="outsider")
        other = Client()
        other.force_login(outsider, backend="django.contrib.auth.backends.ModelBackend")
        self.assertEqual(other.get("/inventory/list/", secure=True).status_code, 403)
        self.assertEqual((InventoryLot.objects.count(), Movement.objects.count()), (2, 2))

    def test_date_mode_csrf_idempotency_and_html_json_equivalence(self):
        data = self.payload(package_date="2080-10-10")
        blocked = self.client.post("/api/inventory/", json.dumps(data), content_type="application/json", secure=True)
        self.assertEqual(blocked.status_code, 403)
        first = self.post_api(data)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(self.post_api(data).json(), first.json())
        self.assertRedirects(self.post_form("/inventory/", data), "/inventory/list/", fetch_redirect_response=False)
        batch = InventoryLot.objects.get()
        self.assertEqual((batch.package_date, batch.package_date_status, batch.storage_status), (date(2080, 10, 10), "known", "needs_check"))
        self.assertEqual(self.client.get("/api/today/", secure=True).json()["arrange"], [])
        self.assertEqual(self.post_api({**data, "package_date": "2080-10-11"}).status_code, 409)
        self.assertEqual((InventoryLot.objects.count(), Movement.objects.count(), BusinessAction.objects.count()), (1, 1, 1))

    def test_days_mode_leap_day_and_purchase_is_not_start_date(self):
        data = self.payload(shelf_life_mode="days", shelf_life_days="2", shelf_life_start="2028-02-28", purchase_date="2028-03-20", package_date="2099-01-01")
        result = self.post_api(data)
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.json()["lot"]["package_date"], "2028-03-01")
        html = self.post_form("/inventory/", {**data, "request_id": str(uuid4())})
        self.assertRedirects(html, "/inventory/list/", fetch_redirect_response=False)
        self.assertEqual(list(InventoryLot.objects.values_list("package_date", flat=True)), [date(2028, 3, 1)] * 2)
        self.assertEqual(Movement.objects.count(), 2)
        self.assertEqual(self.post_api(self.payload(shelf_life_mode="days", shelf_life_days="2", purchase_date="2028-03-20")).status_code, 422)
        self.assertEqual(InventoryLot.objects.count(), 2)

    def test_invalid_duration_never_creates_partial_inventory(self):
        for changes in (
            {"shelf_life_days": "-1"}, {"shelf_life_days": "0"}, {"shelf_life_days": "1.5"},
            {"shelf_life_days": True}, {"shelf_life_days": "36501"}, {"shelf_life_days": "NaN"},
            {"shelf_life_start": "2026-02-30"}, {"shelf_life_start": "9999-12-31"},
            {"shelf_life_start": ""}, {"shelf_life_days": ""}, {"shelf_life_mode": "auto"},
        ):
            with self.subTest(changes=changes):
                payload = self.payload(shelf_life_mode="days", shelf_life_days="1", shelf_life_start="2028-02-28")
                payload.update(changes)
                self.assertEqual(self.post_api(payload).status_code, 422)
        self.assertEqual((InventoryLot.objects.count(), Movement.objects.count(), BusinessAction.objects.count()), (0, 0, 0))
        bad = self.payload(shelf_life_mode="days", shelf_life_days="5", shelf_life_start="", ingredient_name="<script>bad</script>")
        response = self.post_form("/inventory/", bad)
        self.assertContains(response, "请同时填写保质期天数和起算日期", status_code=422)
        self.assertContains(response, 'value="5"', status_code=422)
        self.assertContains(response, bad["request_id"], status_code=422)
        self.assertNotContains(response, "<script>bad</script>", status_code=422)

    def test_required_fields_unknown_date_and_expired_exclusion(self):
        for field in ("ingredient_name", "quantity", "unit", "location"):
            with self.subTest(field=field):
                self.assertEqual(self.post_api(self.payload(**{field: ""})).status_code, 422)
        self.assertEqual(InventoryLot.objects.count(), 0)
        self.assertEqual(self.post_api(self.payload(shelf_life_mode="days", shelf_life_days="", shelf_life_start="")).status_code, 201)
        batch = InventoryLot.objects.get()
        self.assertEqual((batch.package_date, batch.package_date_status, batch.storage_status), (None, "unknown", "needs_check"))
        expired = self.post_api(self.payload(package_date="2000-01-01", storage_status="verified"))
        self.assertEqual(expired.status_code, 201)
        self.assertEqual(self.client.get("/api/recipes/", secure=True).json()["recipes"], [])
        self.assertContains(self.client.get("/inventory/list/", secure=True), "2000-01-01")

    def test_edit_action_return_to_list_and_stale_version_is_rejected(self):
        result = self.post_api(self.payload(package_date="2080-10-10"))
        pk = result.json()["lot"]["id"]
        listing = self.client.get("/inventory/list/", secure=True)
        self.assertContains(listing, f'href="/inventory/{pk}/edit/"')
        edited = self.post_form(f"/inventory/{pk}/edit/", {"request_id": str(uuid4()), "version": "0", "storage_status": "verified"})
        self.assertRedirects(edited, "/inventory/list/", fetch_redirect_response=False)
        action = {"request_id": str(uuid4()), "kind": "eat", "lot_id": str(pk), "version": "1", "quantity": "1", "unit": "piece"}
        self.assertRedirects(self.post_form("/inventory/action/", action), "/inventory/list/", fetch_redirect_response=False)
        self.assertEqual(self.post_form("/inventory/action/", action).status_code, 302)
        self.assertEqual(self.post_form("/inventory/action/", {**action, "request_id": str(uuid4())}).status_code, 409)
        batch = InventoryLot.objects.get(pk=pk)
        self.assertEqual((batch.quantity_milli, batch.version, Movement.objects.count()), (2000, 2, 2))

    def test_four_recipe_groups_preserve_custom_categories_and_read_only_matching(self):
        custom = create_from_data(self.user, category="周末家常", title="家庭自存菜")
        meat = create_from_data(self.user, category="荤菜", title="家庭荤菜")
        before = (custom.category, custom.version, custom.pk)
        listing = recipes.list_recipes(self.user)
        self.assertEqual(listing["categories"], ["荤菜", "素菜", "汤羹", "其他"])
        self.assertEqual({row["id"] for row in recipes.list_recipes(self.user, category="汤羹")["recipes"]}, {"seaweed-egg-soup"})
        self.assertIn("tomato-egg", {row["id"] for row in recipes.list_recipes(self.user, category="素菜")["recipes"]})
        self.assertEqual(recipes.list_recipes(self.user, category="荤菜")["recipes"][0]["id"], f"family-{meat.pk}")
        self.assertIn(f"family-{custom.pk}", {row["id"] for row in recipes.list_recipes(self.user, category="其他")["recipes"]})
        self.assertEqual(recipes.list_recipes(self.user, category="周末家常")["count"], 1)
        custom.refresh_from_db()
        self.assertEqual((custom.category, custom.version, custom.pk), before)
        self.assertEqual((InventoryLot.objects.count(), Movement.objects.count()), (0, 0))

    def test_shopping_summary_link_and_duplicate_confirmation_still_work(self):
        self.post_api(self.payload(package_date="2000-01-01", storage_status="verified"))
        page = self.client.get("/shopping/", secure=True)
        self.assertContains(page, "仅统计未过期的食材")
        self.assertContains(page, 'href="/inventory/list/">已添加食材</a>')
        self.assertNotContains(page, "当前没有已核对的可用批次")
        self.assertEqual(page.context["available"], [])
        payload = {"request_id": str(uuid4()), "name": "番茄", "quantity": "2", "unit": "piece"}
        self.assertEqual(self.post_form("/shopping/", payload).status_code, 409)
        self.assertEqual(self.post_form("/shopping/", {**payload, "confirm_duplicate": "true"}).status_code, 302)
        self.assertEqual(self.post_form("/shopping/", {**payload, "confirm_duplicate": "true"}).status_code, 302)
        from shopping.models import ShoppingItem
        self.assertEqual((ShoppingItem.objects.count(), InventoryLot.objects.count(), Movement.objects.count()), (1, 1, 1))
