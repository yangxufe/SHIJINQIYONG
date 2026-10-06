"""Second issue-list journeys, using only synthetic accounts and inventory."""
import re
from datetime import timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import Client, TestCase
from django.utils import timezone

from core.forms import INVITATION_SALT
from core.models import MemberInvitation, MemberRole
from inventory.models import BusinessAction, InventoryLot, Movement
from inventory.services import create_lot


class SecondOptimizationTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username="admin", password="Synthetic-admin!2026")
        self.member = get_user_model().objects.create_user(username="existing-long-member-name", password="Synthetic-member!2026")
        MemberRole.objects.create(user=self.admin, role="admin")
        MemberRole.objects.create(user=self.member, role="member")
        self.client.force_login(self.member, backend="django.contrib.auth.backends.ModelBackend")
        self.invitation = MemberInvitation.objects.create(created_by=self.admin, expires_at=timezone.now()+timedelta(hours=24))
        self.token = signing.dumps(str(self.invitation.pk), salt=INVITATION_SALT)

    def register_payload(self, username="family1234", password="N7!vQ2$x"):
        return {"username": username, "password1": password, "password2": password, "invitation": self.token}

    def test_cover_to_auth_to_home_and_feature_pages(self):
        anonymous = Client()
        self.assertRedirects(anonymous.get("/", secure=True), "/welcome/", fetch_redirect_response=False)
        cover = anonymous.get("/welcome/", secure=True)
        self.assertContains(cover, 'href="/login/"')
        self.assertContains(cover, 'href="/register/"')
        self.assertContains(cover, '<h1 class="brand-script">食尽其用</h1>')
        home = self.client.get("/", secure=True)
        self.assertContains(home, '<h1>首页</h1>')
        self.assertContains(home, 'aria-label="功能入口"')
        self.assertNotContains(home, 'class="home-return"')
        for path, title in (("/inventory/", "添加菜品"), ("/inventory/list/", "食材列表"), ("/recipes/", "查看菜谱"), ("/shopping/", "采购计划")):
            self.assertContains(home, f'<h2>{title}</h2>')
            page = self.client.get(path, secure=True)
            self.assertContains(page, f'<h1>{title}</h1>')
            self.assertContains(page, 'class="home-return" href="/"', count=1)
            self.assertContains(page, 'href="/settings/"')
            self.assertContains(page, 'action="/logout/"')
            self.assertNotContains(page, 'class="bottom-nav"')
            self.assertNotContains(page, 'class="eyebrow"')
            self.assertEqual(anonymous.get(path, secure=True).status_code, 302)
        self.assertEqual((InventoryLot.objects.count(), BusinessAction.objects.count()), (0, 0))

    def test_secondary_pages_keep_home_return_without_old_path_titles(self):
        for path in ("/settings/", "/recipes/library/", "/recipes/new/", "/recipes/workbench/?direct=1", "/recipes/preferences/", "/recipes/search-results/?find=番茄", "/recipes/tomato-egg/"):
            with self.subTest(path=path):
                page = self.client.get(path, secure=True)
                self.assertContains(page, 'class="home-return" href="/"', count=1)
                self.assertNotContains(page, 'class="bottom-nav"')
                self.assertNotContains(page, 'class="eyebrow"')

    def test_server_registration_boundaries_do_not_consume_invalid_invite(self):
        anonymous = Client()
        for payload, field in ((self.register_payload("family12345"), "username"), (self.register_payload(password="N7!vQ2$"), "password2")):
            with self.subTest(field=field):
                result = anonymous.post("/register/", payload, secure=True)
                self.assertEqual(result.status_code, 422)
                self.assertIn(field, result.context["form"].errors)
                self.invitation.refresh_from_db()
                self.assertIsNone(self.invitation.used_by_id)
                self.assertFalse(get_user_model().objects.filter(username=payload["username"]).exists())
                self.assertNotContains(result, 'value="'+payload["password1"]+'"', status_code=422)
        result = anonymous.post("/register/", self.register_payload(), secure=True)
        self.assertRedirects(result, "/login/", fetch_redirect_response=False)
        user = get_user_model().objects.get(username="family1234")
        self.assertTrue(user.check_password("N7!vQ2$x"))
        self.assertFalse(user.is_staff)
        self.assertEqual(user.member_role.role, "member")

    def test_ten_chinese_characters_and_existing_password_validators(self):
        anonymous = Client()
        for password in ("12345678", "password", "family1234"):
            response = anonymous.post("/register/", self.register_payload(password=password), secure=True)
            self.assertEqual(response.status_code, 422)
            self.assertIn("password2", response.context["form"].errors)
        chinese_name = "用户甲乙丙丁戊己庚辛"
        self.assertEqual(len(chinese_name), 10)
        response = anonymous.post("/register/", self.register_payload(username=chinese_name), secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(get_user_model().objects.get(username=chinese_name).check_password("N7!vQ2$x"))

    def test_existing_long_account_can_login_and_csrf_logout_returns_cover(self):
        browser = Client(enforce_csrf_checks=True)
        login = browser.get("/login/", secure=True)
        token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', login.content).group(1).decode()
        response = browser.post("/login/", {"username": self.member.username, "password": "Synthetic-member!2026", "csrfmiddlewaretoken": token}, secure=True, HTTP_ORIGIN="https://testserver")
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        home = browser.get("/", secure=True)
        self.assertContains(home, "采购计划")
        token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', home.content).group(1).decode()
        self.assertEqual(browser.post("/logout/", secure=True, HTTP_ORIGIN="https://testserver").status_code, 403)
        result = browser.post("/logout/", {"csrfmiddlewaretoken": token}, secure=True, HTTP_ORIGIN="https://testserver", follow=True)
        self.assertContains(result, 'href="/welcome/"')
        self.assertEqual(browser.get("/api/inventory/", secure=True).status_code, 401)

    def test_password_controls_and_limits_render_without_echoing_passwords(self):
        anonymous = Client()
        for path, count in (("/login/", 1), ("/register/", 2)):
            response = anonymous.get(path, secure=True)
            self.assertContains(response, 'aria-label="显示密码 1 秒"', count=count)
            self.assertContains(response, 'class="password-control"', count=count)
            self.assertContains(response, 'js/password-peek.js')
            self.assertNotContains(response, 'class="brand-script"')
            self.assertContains(response, 'href="/welcome/">返回首页')
        self.assertContains(anonymous.get("/register/", secure=True), 'maxlength="10"')
        self.assertContains(anonymous.get("/register/", secure=True), 'minlength="8"', count=2)

    def test_today_api_and_existing_quantity_records_survive_navigation(self):
        result = create_lot(self.member, {"request_id": str(uuid4()), "ingredient_name": "番茄", "quantity": "2", "unit": "piece", "location": "fridge", "storage_status": "verified", "package_date_status": "not_applicable"})
        before = (BusinessAction.objects.count(), Movement.objects.count())
        today = self.client.get("/api/today/", secure=True).json()
        self.assertEqual(today["arrange"][0]["id"], result["body"]["lot"]["id"])
        self.assertContains(self.client.get("/inventory/", secure=True), "计划日期是安排提醒，不是安全期限。")
        for path in ("/", "/inventory/", "/recipes/", "/shopping/"):
            self.assertEqual(self.client.get(path, secure=True).status_code, 200)
        self.assertEqual((BusinessAction.objects.count(), Movement.objects.count()), before)
        self.assertEqual(InventoryLot.objects.get().quantity_milli, 2000)
