import json
import re
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase

from core.models import MemberRole
from inventory import services as stock
from inventory.models import BusinessAction, InventoryLot, Movement
from shopping import services
from shopping.models import ShoppingItem


def member():
    user = get_user_model().objects.create_user(username="shopping-member", password="test-only-strong-password-2026!")
    MemberRole.objects.create(user=user, role="member")
    return user


def new_item(user, name="番茄", *, confirm=False, request_id=None):
    return services.add_item(user, {"request_id": request_id or str(uuid4()), "name": name,
                                    "quantity": "2", "unit": "piece", "confirm_duplicate": confirm})


class ShoppingTests(TestCase):
    def setUp(self):
        self.user = member()

    def test_duplicate_warning_uses_only_usable_stock_and_known_aliases(self):
        stock.create_lot(self.user, {"request_id": str(uuid4()), "ingredient_name": "西红柿", "quantity": "3",
                                      "unit": "piece", "location": "fridge", "storage_status": "verified",
                                      "package_date_status": "not_applicable"})
        with self.assertRaises(stock.InventoryError) as caught:
            new_item(self.user)
        self.assertEqual(caught.exception.code, "possible_duplicate")
        self.assertEqual(ShoppingItem.objects.count(), 0)
        first = new_item(self.user, confirm=True)
        self.assertEqual(first["body"]["existing_stock"][0]["quantity"], "3")
        with self.assertRaises(stock.InventoryError) as caught:
            new_item(self.user, "西红柿")
        self.assertEqual(caught.exception.code, "possible_duplicate")
        self.assertEqual(ShoppingItem.objects.count(), 1)

    def test_unverified_suspect_and_expired_not_counted_as_available(self):
        for name, change in [
            ("待核对", {"storage_status": "needs_check"}),
            ("疑似变质", {"status": "suspect"}),
            ("已过包装日期", {"package_date_status": "known", "package_date": "2000-01-01"}),
        ]:
            payload = {"request_id": str(uuid4()), "ingredient_name": name, "quantity": "1",
                       "unit": "piece", "location": "fridge", "storage_status": "verified",
                       "package_date_status": "not_applicable"}
            payload.update(change)
            stock.create_lot(self.user, payload)
            with self.assertRaises(stock.InventoryError) as caught:
                new_item(self.user, name)
            self.assertEqual(caught.exception.code, "possible_duplicate")
            self.assertEqual(new_item(self.user, name, confirm=True)["body"]["needs_review_count"], 1)
        self.assertEqual(services.list_items(self.user)["available"], [])

    def test_bought_does_not_stock_and_receipt_is_once_even_with_new_key(self):
        created = new_item(self.user)
        item_id = created["body"]["item"]["id"]
        bought_key = str(uuid4())
        bought = {"request_id": bought_key, "version": 0}
        self.assertEqual(services.mark_bought(self.user, item_id, bought), services.mark_bought(self.user, item_id, bought))
        self.assertEqual(InventoryLot.objects.count(), 0)
        self.assertEqual(Movement.objects.count(), 0)
        receive = {"request_id": str(uuid4()), "version": 1, "quantity": "1.5", "location": "fridge",
                   "storage_status": "needs_check", "status": "active", "package_date_status": "not_applicable"}
        result = services.receive_item(self.user, item_id, receive)
        self.assertEqual(result, services.receive_item(self.user, item_id, receive))
        self.assertEqual(result["body"]["lot"]["quantity"], "1.5")
        self.assertEqual(InventoryLot.objects.count(), 1)
        self.assertEqual(Movement.objects.filter(action__kind="shop_receive").count(), 1)
        item = ShoppingItem.objects.get(pk=item_id)
        self.assertEqual((item.status, item.version, item.received_lot_id, item.received_action_id),
                         ("received", 2, result["body"]["lot"]["id"], result["body"]["action_id"]))
        with self.assertRaises(stock.InventoryError) as caught:
            services.receive_item(self.user, item_id, {**receive, "request_id": str(uuid4())})
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual((InventoryLot.objects.count(), Movement.objects.count()), (1, 1))
        self.assertEqual(BusinessAction.objects.filter(kind="shop_receive").count(), 1)
        self.assertEqual(services.list_items(self.user)["available"], [])

    def test_stale_version_cancel_and_failed_receipt_are_atomic(self):
        item_id = new_item(self.user)["body"]["item"]["id"]
        services.mark_bought(self.user, item_id, {"request_id": str(uuid4()), "version": 0})
        with self.assertRaises(stock.InventoryError):
            services.receive_item(self.user, item_id, {"request_id": str(uuid4()), "version": 0,
                                                        "quantity": "2", "location": "fridge"})
        self.assertEqual(InventoryLot.objects.count(), 0)
        self.assertEqual(BusinessAction.objects.filter(kind="shop_receive").count(), 0)
        services.cancel_item(self.user, item_id, {"request_id": str(uuid4()), "version": 1})
        with self.assertRaises(stock.InventoryError):
            services.receive_item(self.user, item_id, {"request_id": str(uuid4()), "version": 2,
                                                        "quantity": "2", "location": "fridge"})
        self.assertEqual((InventoryLot.objects.count(), Movement.objects.count()), (0, 0))

    def test_receipt_rolls_back_lot_when_ledger_write_fails(self):
        item_id = new_item(self.user)["body"]["item"]["id"]
        services.mark_bought(self.user, item_id, {"request_id": str(uuid4()), "version": 0})
        payload = {"request_id": str(uuid4()), "version": 1, "quantity": "2", "location": "fridge"}
        with patch("shopping.services.Movement.objects.create", side_effect=RuntimeError("test ledger failure")):
            with self.assertRaises(RuntimeError):
                services.receive_item(self.user, item_id, payload)
        self.assertEqual((InventoryLot.objects.count(), Movement.objects.count(),
                          BusinessAction.objects.filter(kind="shop_receive").count()), (0, 0, 0))
        item = ShoppingItem.objects.get(pk=item_id)
        self.assertEqual((item.status, item.version, item.received_lot_id), ("bought", 1, None))

    def test_web_and_api_auth_csrf_and_form_flow(self):
        self.assertEqual(Client().get("/api/shopping/", secure=True).status_code, 401)
        self.assertEqual(Client().get("/shopping/", secure=True).status_code, 302)
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")
        page = browser.get("/shopping/", secure=True)
        self.assertContains(page, "采购清单")
        token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', page.content).group(1).decode()
        body = {"request_id": str(uuid4()), "name": "土豆", "quantity": "2", "unit": "piece", "csrfmiddlewaretoken": token}
        self.assertEqual(browser.post("/shopping/", body, secure=True).status_code, 403)
        self.assertEqual(browser.post("/shopping/", body, secure=True, HTTP_ORIGIN="https://testserver").status_code, 302)
        item = ShoppingItem.objects.get()
        self.assertEqual(browser.post(f"/shopping/{item.pk}/bought/", {"request_id": str(uuid4()), "version": 0,
            "csrfmiddlewaretoken": token}, secure=True, HTTP_ORIGIN="https://testserver").status_code, 302)
        self.assertEqual(InventoryLot.objects.count(), 0)
        self.assertEqual(browser.post(f"/shopping/{item.pk}/receive/", {"request_id": str(uuid4()), "version": 1,
            "quantity": "1", "location": "fridge", "storage_status": "verified", "status": "active",
            "package_date_status": "not_applicable", "csrfmiddlewaretoken": token},
            secure=True, HTTP_ORIGIN="https://testserver").status_code, 302)
        self.assertEqual(InventoryLot.objects.count(), 1)
        self.assertEqual(browser.get("/api/shopping/", secure=True).json()["history"][0]["status"], "received")
        self.assertEqual(browser.post("/api/shopping/", json.dumps({"request_id": str(uuid4()), "name": "葱",
            "quantity": "1", "unit": "piece"}), content_type="application/json", secure=True).status_code, 403)


class ConcurrentReceiptTests(TransactionTestCase):
    def test_two_connections_cannot_receive_same_item_twice(self):
        user = member()
        item_id = new_item(user)["body"]["item"]["id"]
        services.mark_bought(user, item_id, {"request_id": str(uuid4()), "version": 0})
        barrier = Barrier(2)

        def attempt(request_id):
            close_old_connections()
            payload = {"request_id": request_id, "version": 1, "quantity": "2", "location": "fridge",
                       "storage_status": "verified", "package_date_status": "not_applicable"}
            barrier.wait(timeout=5)
            try:
                result = services.receive_item(user, item_id, payload)
                return result["status"], payload
            except stock.InventoryError as exc:
                return exc.status, payload
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, [str(uuid4()), str(uuid4())]))
        self.assertEqual(sum(status == 201 for status, _ in results), 1)
        for status, payload in results:
            if status == 503:
                with self.assertRaises(stock.InventoryError) as caught:
                    services.receive_item(user, item_id, payload)
                self.assertEqual(caught.exception.status, 409)
            elif status != 201:
                self.assertEqual(status, 409)
        self.assertEqual((InventoryLot.objects.count(), Movement.objects.count(),
                          ShoppingItem.objects.get(pk=item_id).status), (1, 1, "received"))
