import json
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.db.models import Sum
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from core.models import MemberRole
from inventory import services
from inventory.models import BusinessAction, InventoryLot, Movement


def new_user(name="member"):
    user = get_user_model().objects.create_user(username=name, password="test-only-strong-password-2026!")
    MemberRole.objects.create(user=user, role="member")
    return user


def new_lot(user, quantity="3", **overrides):
    payload = {
        "request_id": str(uuid4()),
        "ingredient_name": "番茄",
        "name": "番茄",
        "quantity": quantity,
        "unit": "piece",
        "location": "fridge",
        "storage_status": "verified",
        "package_date_status": "not_applicable",
    }
    payload.update(overrides)
    result = services.create_lot(user, payload)
    return InventoryLot.objects.get(pk=result["body"]["lot"]["id"])


def action_payload(lot, kind, quantity, request_id=None, note=""):
    return {"request_id": request_id or str(uuid4()), "kind": kind, "note": note, "items": [{"lot_id": lot.pk, "version": lot.version, "quantity": quantity, "unit": lot.unit}]}


class InventoryServiceTests(TestCase):
    def setUp(self):
        self.user = new_user()

    def test_tomatoes_and_ledger_balance(self):
        lot = new_lot(self.user)
        self.assertEqual(Movement.objects.get(lot=lot).delta_milli, 3000)
        services.apply_action(self.user, action_payload(lot, "cook", "1"))
        lot.refresh_from_db()
        services.apply_action(self.user, action_payload(lot, "eat", "0.5"))
        lot.refresh_from_db()
        self.assertEqual(lot.quantity_milli, 1500)
        self.assertEqual(Movement.objects.filter(lot=lot).aggregate(total=Sum("delta_milli"))["total"], 1500)
        self.assertEqual(list(Movement.objects.filter(lot=lot).order_by("id").values_list("after_milli", flat=True)), [3000, 2000, 1500])

    def test_fractional_values_have_no_float_error_and_zero_is_archived(self):
        lot = new_lot(self.user, "0.3")
        services.apply_action(self.user, action_payload(lot, "eat", "0.1"))
        lot.refresh_from_db()
        services.apply_action(self.user, action_payload(lot, "eat", "0.2"))
        lot.refresh_from_db()
        self.assertEqual((lot.quantity_milli, lot.status), (0, "depleted"))
        self.assertEqual(Movement.objects.filter(lot=lot).aggregate(total=Sum("delta_milli"))["total"], 0)

    def test_invalid_quantities_never_write(self):
        before = BusinessAction.objects.count()
        for amount in ("NaN", "Infinity", "-1", "0.0001", "10000000000", "1e2", "", 1.0, True, None, "1.2345"):
            with self.subTest(amount=amount), self.assertRaises(services.InventoryError):
                services.create_lot(self.user, {"request_id": str(uuid4()), "ingredient_name": "坏值", "quantity": amount, "unit": "g", "location": "fridge"})
        self.assertEqual(BusinessAction.objects.count(), before)
        self.assertEqual(InventoryLot.objects.count(), 0)

    def test_idempotent_retry_after_lost_response_and_changed_params_conflict(self):
        lot = new_lot(self.user)
        payload = action_payload(lot, "cook", "1")
        first = services.apply_action(self.user, payload)
        second = services.apply_action(self.user, payload)
        self.assertEqual(first, second)
        self.assertEqual(BusinessAction.objects.filter(request_id=payload["request_id"]).count(), 1)
        self.assertEqual(Movement.objects.filter(lot=lot).count(), 2)
        changed = dict(payload)
        changed["items"] = [{"lot_id": lot.pk, "version": 0, "quantity": "0.5", "unit": lot.unit}]
        with self.assertRaises(services.InventoryError) as caught:
            services.apply_action(self.user, changed)
        self.assertEqual(caught.exception.status, 409)
        lot.refresh_from_db()
        self.assertEqual(lot.quantity_milli, 2000)

    def test_two_batch_failure_rolls_back_first_update(self):
        first = new_lot(self.user, "2")
        second = new_lot(self.user, "0.5")
        before_actions = BusinessAction.objects.count()
        payload = {"request_id": str(uuid4()), "kind": "cook", "items": [{"lot_id": first.pk, "version": 0, "quantity": "1", "unit": first.unit}, {"lot_id": second.pk, "version": 0, "quantity": "1", "unit": second.unit}]}
        with self.assertRaises(services.InventoryError) as caught:
            services.apply_action(self.user, payload)
        self.assertEqual(caught.exception.code, "insufficient_quantity")
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.quantity_milli, second.quantity_milli), (2000, 500))
        self.assertEqual(BusinessAction.objects.count(), before_actions)
        self.assertEqual(Movement.objects.count(), 2)

    def test_duplicate_lot_is_rejected_before_write(self):
        lot = new_lot(self.user, "1")
        item = {"lot_id": lot.pk, "version": 0, "quantity": "0.6", "unit": lot.unit}
        payload = {"request_id": str(uuid4()), "kind": "eat", "items": [item, item]}
        with self.assertRaises(services.InventoryError) as caught:
            services.apply_action(self.user, payload)
        self.assertEqual(caught.exception.status, 422)
        lot.refresh_from_db()
        self.assertEqual(lot.quantity_milli, 1000)

    def test_different_unit_is_rejected_without_conversion(self):
        lot = new_lot(self.user, "1")
        payload = action_payload(lot, "eat", "0.5")
        payload["items"][0]["unit"] = "kg"
        with self.assertRaises(services.InventoryError) as caught:
            services.apply_action(self.user, payload)
        self.assertEqual(caught.exception.code, "unit_conflict")
        lot.refresh_from_db()
        self.assertEqual(lot.quantity_milli, 1000)

    def test_edit_version_and_quantity_field_block(self):
        lot = new_lot(self.user)
        result = services.edit_lot(self.user, lot.pk, {"request_id": str(uuid4()), "version": 0, "name": "周末番茄"})
        self.assertEqual(result["body"]["lot"]["version"], 1)
        with self.assertRaises(services.InventoryError) as caught:
            services.edit_lot(self.user, lot.pk, {"request_id": str(uuid4()), "version": 0, "location": "pantry"})
        self.assertEqual(caught.exception.status, 409)
        with self.assertRaises(services.InventoryError) as caught:
            services.edit_lot(self.user, lot.pk, {"request_id": str(uuid4()), "version": 1, "quantity": "99"})
        self.assertEqual(caught.exception.status, 422)
        lot.refresh_from_db()
        self.assertEqual((lot.name, lot.quantity_milli, lot.version), ("周末番茄", 3000, 1))

    def test_correction_up_down_is_distinct_from_discard(self):
        lot = new_lot(self.user, "2")
        services.apply_action(self.user, action_payload(lot, "correct", "3", note="录入少了一个"))
        lot.refresh_from_db()
        services.apply_action(self.user, action_payload(lot, "correct", "2.5", note="复核称重"))
        lot.refresh_from_db()
        self.assertEqual(lot.quantity_milli, 2500)
        movements = list(Movement.objects.filter(lot=lot).order_by("id").values_list("delta_milli", "action__kind"))
        self.assertEqual(movements, [(2000, "lot_create"), (1000, "correct"), (-500, "correct")])
        self.assertEqual(sum(delta for delta, _ in movements), lot.quantity_milli)
        services.apply_action(self.user, action_payload(lot, "discard", "2.5", note="确实丢弃"))
        lot.refresh_from_db()
        self.assertEqual((lot.quantity_milli, lot.status), (0, "discarded"))

    def test_unreviewed_suspect_or_expired_lots_cannot_be_used(self):
        yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
        lots = [
            new_lot(self.user, "1", storage_status="needs_check"),
            new_lot(self.user, "1", status="suspect"),
            new_lot(self.user, "1", package_date_status="known", package_date=yesterday),
        ]
        for lot in lots:
            with self.subTest(lot=lot.pk), self.assertRaises(services.InventoryError) as caught:
                services.apply_action(self.user, action_payload(lot, "cook", "1"))
            self.assertEqual(caught.exception.code, "needs_review")
            lot.refresh_from_db()
            self.assertEqual(lot.quantity_milli, 1000)
        with self.assertRaises(services.InventoryError) as caught:
            services.edit_lot(self.user, lots[1].pk, {"request_id": str(uuid4()), "version": 0, "status": "active"})
        self.assertEqual(caught.exception.code, "needs_review")

    def test_api_and_html_share_service_and_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")
        page = client.get("/inventory/", secure=True)
        self.assertEqual(page.status_code, 200)
        token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', page.content).group(1).decode()
        payload = {"request_id": str(uuid4()), "ingredient_name": "苹果", "name": "苹果", "quantity": "3", "unit": "piece", "location": "fridge"}
        api_response = client.post("/api/inventory/", data=json.dumps(payload), content_type="application/json", secure=True, HTTP_ORIGIN="https://testserver", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(api_response.status_code, 201)
        self.assertEqual(api_response.json()["lot"]["quantity"], "3")
        form = dict(payload, request_id=str(uuid4()), ingredient_name="香蕉", quantity="2")
        form["csrfmiddlewaretoken"] = token
        form_response = client.post("/inventory/", data=form, secure=True, HTTP_ORIGIN="https://testserver")
        self.assertEqual(form_response.status_code, 302)
        self.assertEqual(InventoryLot.objects.count(), 2)
        self.assertEqual(Movement.objects.count(), 2)
        self.assertEqual(client.post("/api/actions/", data="{}", content_type="application/json", secure=True, HTTP_ORIGIN="https://testserver").status_code, 403)

    def test_api_bad_json_and_pagination_limit(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")
        token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', client.get("/inventory/", secure=True).content).group(1).decode()
        response = client.post("/api/inventory/", data='{"quantity":"1","quantity":"2"}', content_type="application/json", secure=True, HTTP_ORIGIN="https://testserver", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(client.get("/api/inventory/?per_page=101", secure=True).status_code, 422)

    def test_untrusted_batch_name_is_escaped_in_html(self):
        new_lot(self.user, "1", ingredient_name="<img src=x onerror=alert(1)>", name="<img src=x onerror=alert(1)>")
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")
        page = client.get("/inventory/", secure=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"&lt;img", page.content)
        self.assertNotIn(b"<img src=x onerror", page.content)

    def test_html_edit_and_action_forms_use_the_same_ledger(self):
        lot = new_lot(self.user, "2")
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")
        edit_response = client.get(f"/inventory/{lot.pk}/edit/", secure=True)
        self.assertEqual(edit_response.status_code, 200)
        token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', edit_response.content).group(1).decode()
        request_id = re.search(rb'name="request_id" value="([^"]+)"', edit_response.content).group(1).decode()
        updated = client.post(f"/inventory/{lot.pk}/edit/", data={"csrfmiddlewaretoken": token, "request_id": request_id, "version": "0", "name": "晚餐番茄", "location": "fridge", "package_date_status": "not_applicable", "package_date": "", "package_date_text": "", "planned_use_date": "", "purchase_date": "", "opened_date": "", "status": "active", "storage_status": "verified"}, secure=True, HTTP_ORIGIN="https://testserver")
        self.assertEqual(updated.status_code, 302)
        lot.refresh_from_db()
        self.assertEqual((lot.name, lot.version), ("晚餐番茄", 1))
        response = client.post("/inventory/action/", data={"csrfmiddlewaretoken": token, "request_id": str(uuid4()), "kind": "cook", "lot_id": str(lot.pk), "version": "1", "unit": "piece", "quantity": "0.5", "note": "晚餐"}, secure=True, HTTP_ORIGIN="https://testserver")
        self.assertEqual(response.status_code, 302)
        lot.refresh_from_db()
        self.assertEqual((lot.quantity_milli, lot.version), (1500, 2))
        self.assertEqual(Movement.objects.filter(lot=lot).count(), 2)

    def test_api_patch_action_lookup_and_movement_page(self):
        lot = new_lot(self.user, "2")
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")
        token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', client.get("/inventory/", secure=True).content).group(1).decode()
        patch = {"request_id": str(uuid4()), "version": 0, "name": "第二批番茄"}
        response = client.patch(f"/api/inventory/{lot.pk}/", data=json.dumps(patch), content_type="application/json", secure=True, HTTP_ORIGIN="https://testserver", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["lot"]["version"], 1)
        action = {"request_id": str(uuid4()), "kind": "eat", "items": [{"lot_id": lot.pk, "version": 1, "quantity": "0.5", "unit": lot.unit}]}
        response = client.post("/api/actions/", data=json.dumps(action), content_type="application/json", secure=True, HTTP_ORIGIN="https://testserver", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        lookup = client.get(f"/api/actions/{body['action_id']}/", secure=True)
        self.assertEqual(lookup.status_code, 200)
        self.assertEqual(lookup.json(), {"original_status": 200, "result": body})
        self.assertEqual(client.get("/api/movements/", secure=True).json()["count"], 2)
        other = new_user("outsider")
        client.force_login(other, backend="django.contrib.auth.backends.ModelBackend")
        self.assertEqual(client.get(f"/api/actions/{body['action_id']}/", secure=True).status_code, 404)


class RealFileConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = new_user()
        self.other = new_user("other")
        self.assertNotEqual(str(connection.settings_dict["NAME"]), ":memory:")
        self.assertTrue(Path(connection.settings_dict["NAME"]).is_file())

    def _race(self, payloads, actors):
        barrier = Barrier(len(payloads))

        def attempt(payload, actor_id):
            close_old_connections()
            actor = get_user_model().objects.get(pk=actor_id)
            barrier.wait(timeout=5)
            try:
                result = services.apply_action(actor, payload)
                return ("ok", result)
            except services.InventoryError as exc:
                return (exc.code, exc.status)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=len(payloads)) as pool:
            futures = [pool.submit(attempt, payload, actor.pk) for payload, actor in zip(payloads, actors)]
            return [future.result(timeout=8) for future in futures]

    def test_two_members_race_for_last_egg(self):
        lot = new_lot(self.user, "1", ingredient_name="鸡蛋", name="鸡蛋")
        results = self._race([action_payload(lot, "eat", "1"), action_payload(lot, "eat", "1")], [self.user, self.other])
        self.assertEqual(sum(kind == "ok" for kind, _ in results), 1)
        lot.refresh_from_db()
        self.assertEqual((lot.quantity_milli, lot.status), (0, "depleted"))
        self.assertEqual(Movement.objects.filter(lot=lot).count(), 2)

    def test_same_request_race_replays_one_result(self):
        lot = new_lot(self.user, "1")
        payload = action_payload(lot, "eat", "0.5")
        results = self._race([payload, payload], [self.user, self.user])
        self.assertEqual([kind for kind, _ in results], ["ok", "ok"])
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(BusinessAction.objects.filter(request_id=payload["request_id"]).count(), 1)
        self.assertEqual(Movement.objects.filter(lot=lot).count(), 2)

    def test_lock_busy_is_bounded_and_specific_503(self):
        lot = new_lot(self.user, "1")
        database = str(connection.settings_dict["NAME"])
        locker = sqlite3.connect(database, timeout=0.1)
        try:
            locker.execute("BEGIN IMMEDIATE")
            started = time.monotonic()
            with self.assertRaises(services.InventoryError) as caught:
                services.apply_action(self.user, action_payload(lot, "eat", "0.5"))
            elapsed = time.monotonic() - started
            self.assertEqual((caught.exception.status, caught.exception.code), (503, "database_busy"))
            self.assertLess(elapsed, 3.5)
        finally:
            locker.rollback()
            locker.close()
        lot.refresh_from_db()
        self.assertEqual(lot.quantity_milli, 1000)

    def test_api_busy_returns_retry_after_without_partial_write(self):
        lot = new_lot(self.user, "1")
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")
        token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', client.get("/inventory/", secure=True).content).group(1).decode()
        database = str(connection.settings_dict["NAME"])
        locker = sqlite3.connect(database, timeout=0.1)
        try:
            locker.execute("BEGIN IMMEDIATE")
            response = client.post("/api/actions/", data=json.dumps(action_payload(lot, "eat", "0.5")), content_type="application/json", secure=True, HTTP_ORIGIN="https://testserver", HTTP_X_CSRFTOKEN=token)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["error"]["code"], "database_busy")
            self.assertEqual(response["Retry-After"], "2")
        finally:
            locker.rollback()
            locker.close()
        lot.refresh_from_db()
        self.assertEqual(lot.quantity_milli, 1000)
