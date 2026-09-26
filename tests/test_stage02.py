import re
from unittest.mock import patch

from axes.models import AccessAttempt
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase

from core.models import MemberRole
from core.security import axes_client_ip
from inventory.models import BusinessAction, Ingredient, InventoryLot, Movement
from shopping.models import ShoppingItem
from uuid import uuid4


PASSWORD = "A-strong-family-password-2026!"


def csrf_value(response):
    match = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', response.content)
    assert match is not None
    return match.group(1).decode()


class AuthSecurityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.member = User.objects.create_user(username="mother", password=PASSWORD)
        MemberRole.objects.create(user=self.member, role="member")
        self.admin = User.objects.create_user(username="father", password=PASSWORD)
        MemberRole.objects.create(user=self.admin, role="admin")
        self.client = Client(enforce_csrf_checks=True, REMOTE_ADDR="192.168.1.52")

    def login(self, username="mother", password=PASSWORD, client=None):
        client = client or self.client
        token = csrf_value(client.get("/login/", secure=True))
        return client.post("/login/", {"username": username, "password": password, "csrfmiddlewaretoken": token}, secure=True, HTTP_ORIGIN="https://testserver")

    def test_anonymous_html_redirect_and_api_401(self):
        self.assertEqual(self.client.get("/").status_code, 302)
        response = self.client.get("/api/inventory/")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "unauthenticated")
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(self.client.post("/api/actions/").status_code, 401)
        self.assertEqual(self.client.get("/health/").json(), {"status": "ok"})

    def test_session_persists_and_member_cannot_read_settings(self):
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/settings/").status_code, 403)
        denied = self.client.get("/api/settings/")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["error"]["code"], "forbidden")
        self.assertEqual(self.client.get("/api/inventory/").status_code, 200)
        self.assertEqual(self.client.get("/api/actions/").status_code, 405)
        self.assertTrue(self.member.password.startswith("argon2$"))
        self.assertNotIn(PASSWORD, self.member.password)
        cookie = self.client.cookies["__Host-xianchi_session"]
        self.assertTrue(cookie["secure"])
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(cookie["path"], "/")
        self.assertFalse(cookie["domain"])

    def test_admin_settings_and_role_required(self):
        self.assertEqual(self.login("father").status_code, 302)
        self.assertEqual(self.client.get("/settings/").status_code, 200)
        self.assertEqual(self.client.get("/api/settings/").status_code, 501)
        self.admin.member_role.delete()
        self.assertEqual(self.client.get("/").status_code, 403)

    def test_login_and_logout_require_valid_csrf(self):
        token = csrf_value(self.client.get("/login/", secure=True))
        self.assertEqual(self.client.post("/login/", {"username": "mother", "password": PASSWORD}, secure=True, HTTP_ORIGIN="https://testserver").status_code, 403)
        self.assertEqual(self.client.post("/login/", {"username": "mother", "password": PASSWORD, "csrfmiddlewaretoken": token}, secure=True, HTTP_ORIGIN="https://evil.example").status_code, 403)
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.client.get("/logout/").status_code, 405)
        self.assertEqual(self.client.post("/logout/", secure=True, HTTP_ORIGIN="https://testserver").status_code, 403)
        token = csrf_value(self.client.get("/", secure=True))
        self.assertEqual(self.client.post("/logout/", {"csrfmiddlewaretoken": token}, secure=True, HTTP_ORIGIN="https://testserver").status_code, 302)
        self.assertEqual(self.client.get("/api/settings/").status_code, 401)
        self.assertEqual(self.client.post("/api/actions/").status_code, 401)

    def test_authenticated_business_post_still_requires_csrf(self):
        self.login()
        denied = self.client.post("/api/actions/", {}, secure=True, HTTP_ORIGIN="https://testserver")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["error"]["code"], "csrf_failed")
        token = csrf_value(self.client.get("/", secure=True))
        response = self.client.post("/api/actions/", data="{}", content_type="application/json", secure=True, HTTP_ORIGIN="https://testserver", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "invalid_input")
        self.assertEqual(self.client.post("/api/actions/", data="{}", content_type="application/json", secure=True, HTTP_ORIGIN="https://evil.example", HTTP_X_CSRFTOKEN=token).status_code, 403)

    def test_disabled_account_and_password_change_invalidate_session(self):
        self.login()
        call_command("manage_member", "disable", "mother")
        self.assertEqual(self.client.get("/api/inventory/").status_code, 401)
        call_command("manage_member", "enable", "mother")
        self.assertEqual(self.client.get("/api/inventory/").status_code, 401)
        self.client = Client(enforce_csrf_checks=True, REMOTE_ADDR="192.168.1.52")
        self.assertEqual(self.login().status_code, 302)
        self.member.refresh_from_db()
        self.member.set_password("A-new-strong-family-password-2026!")
        self.member.save(update_fields=["password"])
        self.assertEqual(self.client.get("/api/inventory/").status_code, 401)

    def test_failed_logins_lock_by_account_and_separate_ip(self):
        for _ in range(5):
            response = self.login(password="wrong-password")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.login().status_code, 429)
        self.assertEqual(self.login(username="father").status_code, 429)
        other = Client(enforce_csrf_checks=True, REMOTE_ADDR="192.168.1.53")
        self.assertEqual(self.login(username="father", client=other).status_code, 302)
        other_member = Client(enforce_csrf_checks=True, REMOTE_ADDR="192.168.1.53")
        self.assertEqual(self.login(username="mother", client=other_member).status_code, 429)
        self.assertEqual(AccessAttempt.objects.filter(ip_address="192.168.1.52").count() > 0, True)
        call_command("manage_member", "unlock", "--username", "mother", "--ip", "192.168.1.52")
        self.assertEqual(self.login().status_code, 302)

    def test_proxy_ip_is_single_valid_address(self):
        class Request:
            META = {"REMOTE_ADDR": "127.0.0.1", "HTTP_X_FORWARDED_FOR": "192.168.1.52"}

        request = Request()
        self.assertEqual(axes_client_ip(request), "192.168.1.52")
        request.META["REMOTE_ADDR"] = "192.168.1.53"
        request.META["HTTP_X_FORWARDED_FOR"] = "203.0.113.1"
        self.assertEqual(axes_client_ip(request), "192.168.1.53")
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["HTTP_X_FORWARDED_FOR"] = "203.0.113.1, 192.168.1.52"
        self.assertEqual(axes_client_ip(request), "127.0.0.1")

    def test_error_pages_do_not_expose_paths(self):
        self.login()
        response = self.client.get("/settings/")
        self.assertNotIn(b"C:\\Users", response.content)
        self.assertNotIn(b"Traceback", response.content)
        response = self.client.get("/does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b"C:\\Users", response.content)


class DataAndCommandTests(TestCase):
    def test_invalid_lot_quantity_rejected_by_database(self):
        ingredient = Ingredient.objects.create(name="番茄")
        with self.assertRaises(IntegrityError), transaction.atomic():
            InventoryLot.objects.create(ingredient=ingredient, name="番茄", quantity_milli=-1, unit="g", location="fridge")

    def test_action_idempotency_key_and_shopping_result_constraints(self):
        user = get_user_model().objects.create_user(username="sibling", password=PASSWORD)
        request_id = uuid4()
        BusinessAction.objects.create(actor=user, request_id=request_id, kind="lot_create", params_hash="a" * 64, result={})
        with self.assertRaises(IntegrityError), transaction.atomic():
            BusinessAction.objects.create(actor=user, request_id=request_id, kind="lot_create", params_hash="a" * 64, result={})
        with self.assertRaises(IntegrityError), transaction.atomic():
            ShoppingItem.objects.create(name="苹果", quantity_milli=1000, unit="piece", status="received")

    def test_movement_balance_must_match_delta(self):
        user = get_user_model().objects.create_user(username="sibling", password=PASSWORD)
        action = BusinessAction.objects.create(actor=user, request_id=uuid4(), kind="lot_create", params_hash="a" * 64, result={})
        ingredient = Ingredient.objects.create(name="番茄")
        lot = InventoryLot.objects.create(ingredient=ingredient, name="番茄", quantity_milli=1000, unit="g", location="fridge")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Movement.objects.create(lot=lot, action=action, delta_milli=-100, unit="g", before_milli=1000, after_milli=1000)

    @patch("core.management.commands.manage_member.getpass", side_effect=[PASSWORD, PASSWORD])
    def test_local_command_validates_and_hashes_password(self, _):
        call_command("manage_member", "create", "sister", "--role", "member")
        user = get_user_model().objects.get(username="sister")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertEqual(user.member_role.role, "member")
        call_command("manage_member", "disable", "sister")
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    @patch("core.management.commands.manage_member.getpass", side_effect=["123", "123"])
    def test_local_command_rejects_weak_password(self, _):
        with self.assertRaises(CommandError):
            call_command("manage_member", "create", "sister", "--role", "member")
        self.assertFalse(get_user_model().objects.filter(username="sister").exists())
