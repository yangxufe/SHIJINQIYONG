import re
from datetime import datetime, timezone as py_timezone
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from core.models import HouseholdSettings, MemberRole
from inventory import services as inventory_service
from inventory.models import BusinessAction, InventoryLot, Movement
from meals import services as meals_service
from meals.catalog import load_catalog


def make_member():
    user = get_user_model().objects.create_user(username="recipe-member", password="test-only-strong-password-2026!")
    MemberRole.objects.create(user=user, role="member")
    return user


def make_lot(actor, name, **changes):
    payload = {
        "request_id": str(uuid4()), "ingredient_name": name, "quantity": "2",
        "unit": "piece", "location": "fridge", "storage_status": "verified",
        "package_date_status": "not_applicable",
    }
    payload.update(changes)
    result = inventory_service.create_lot(actor, payload)
    return InventoryLot.objects.get(pk=result["body"]["lot"]["id"])


class RecipeFlowTests(TestCase):
    def setUp(self):
        self.user = make_member()

    def test_local_catalog_and_explicit_alias_match_only_usable_lots(self):
        recipes, aliases = load_catalog()
        self.assertEqual(aliases["西红柿"], "番茄")
        self.assertTrue(all(recipe["steps"] for recipe in recipes))
        tomato = make_lot(self.user, "西红柿")
        egg = make_lot(self.user, "鸡蛋")
        make_lot(self.user, "西红柿泥")
        make_lot(self.user, "番茄", storage_status="needs_check")
        make_lot(self.user, "番茄", status="suspect")
        make_lot(self.user, "番茄", package_date_status="known", package_date="2000-01-01")
        detail = meals_service.get_recipe(self.user, "tomato-egg")
        self.assertTrue(detail["has_all"])
        self.assertEqual([lot["id"] for lot in detail["ingredients"][0]["lots"]], [tomato.pk])
        self.assertEqual([lot["id"] for lot in detail["ingredients"][1]["lots"]], [egg.pk])
        listing = meals_service.list_recipes(self.user)["recipes"]
        self.assertEqual(listing[0]["id"], "tomato-egg")
        self.assertEqual(listing[0]["missing"], [])

    def test_reading_and_selection_never_deduct(self):
        make_lot(self.user, "番茄")
        self.client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")
        before = (BusinessAction.objects.count(), Movement.objects.count())
        page = self.client.get("/recipes/", secure=True)
        self.assertContains(page, "番茄炒蛋")
        self.assertContains(page, "还缺：鸡蛋")
        self.assertContains(self.client.get("/recipes/tomato-egg/", secure=True), "选择菜谱不会扣库存")
        self.assertEqual(self.client.get("/api/recipes/", secure=True).status_code, 200)
        self.assertEqual(self.client.get("/recipes/tomato-egg/cook/", secure=True).status_code, 405)
        self.assertEqual((BusinessAction.objects.count(), Movement.objects.count()), before)
        self.assertEqual(Client().get("/api/recipes/", secure=True).status_code, 401)

    def test_confirmed_actual_use_is_atomic_and_idempotent_even_after_depletion(self):
        tomato = make_lot(self.user, "番茄", quantity="1")
        egg = make_lot(self.user, "鸡蛋", quantity="1")
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user, backend="django.contrib.auth.backends.ModelBackend")
        page = client.get("/recipes/tomato-egg/", secure=True)
        token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', page.content).group(1).decode()
        request_id = re.search(rb'name="request_id" value="([^"]+)"', page.content).group(1).decode()
        data = {
            "csrfmiddlewaretoken": token, "request_id": request_id,
            f"quantity_{tomato.pk}": "1", f"version_{tomato.pk}": "0",
            f"quantity_{egg.pk}": "1", f"version_{egg.pk}": "0",
        }
        self.assertEqual(client.post("/recipes/tomato-egg/cook/", data, secure=True).status_code, 403)
        origin = {"HTTP_ORIGIN": "https://testserver"}
        self.assertEqual(client.post("/recipes/tomato-egg/cook/", data, secure=True, **origin).status_code, 302)
        tomato.refresh_from_db(); egg.refresh_from_db()
        self.assertEqual((tomato.quantity_milli, egg.quantity_milli), (0, 0))
        self.assertEqual(BusinessAction.objects.filter(kind="cook").count(), 1)
        self.assertEqual(Movement.objects.filter(action__kind="cook").count(), 2)
        self.assertEqual(client.post("/recipes/tomato-egg/cook/", data, secure=True, **origin).status_code, 302)
        self.assertEqual(BusinessAction.objects.filter(kind="cook").count(), 1)
        self.assertEqual(Movement.objects.filter(action__kind="cook").count(), 2)

    def test_stale_batch_rolls_back_all_and_unrelated_batch_is_rejected(self):
        tomato = make_lot(self.user, "番茄")
        egg = make_lot(self.user, "鸡蛋")
        potato = make_lot(self.user, "土豆")
        inventory_service.edit_lot(self.user, egg.pk, {"request_id": str(uuid4()), "version": 0, "manual_priority": "true"})
        payload = {
            "request_id": str(uuid4()),
            f"quantity_{tomato.pk}": "1", f"version_{tomato.pk}": "0",
            f"quantity_{egg.pk}": "1", f"version_{egg.pk}": "0",
        }
        with self.assertRaises(inventory_service.InventoryError) as caught:
            meals_service.cook_recipe(self.user, "tomato-egg", payload)
        self.assertEqual(caught.exception.status, 409)
        tomato.refresh_from_db(); egg.refresh_from_db()
        self.assertEqual((tomato.quantity_milli, egg.quantity_milli), (2000, 2000))
        self.assertFalse(BusinessAction.objects.filter(kind="cook").exists())
        payload[f"version_{egg.pk}"] = "1"
        payload[f"quantity_{potato.pk}"] = "1"
        payload[f"version_{potato.pk}"] = "0"
        with self.assertRaises(inventory_service.InventoryError) as caught:
            meals_service.cook_recipe(self.user, "tomato-egg", payload)
        self.assertEqual(caught.exception.status, 422)

    def test_unknown_recipe_missing_ingredient_and_expired_lot(self):
        tomato = make_lot(self.user, "番茄")
        egg = make_lot(self.user, "鸡蛋", package_date_status="known", package_date="2000-01-01")
        self.assertFalse(meals_service.get_recipe(self.user, "tomato-egg")["has_all"])
        with self.assertRaises(inventory_service.InventoryError) as caught:
            meals_service.get_recipe(self.user, "not-a-recipe")
        self.assertEqual(caught.exception.status, 404)
        payload = {
            "request_id": str(uuid4()),
            f"quantity_{tomato.pk}": "1", f"version_{tomato.pk}": "0",
            f"quantity_{egg.pk}": "1", f"version_{egg.pk}": "0",
        }
        with self.assertRaises(inventory_service.InventoryError) as caught:
            meals_service.cook_recipe(self.user, "tomato-egg", payload)
        self.assertEqual(caught.exception.status, 409)
        self.assertFalse(BusinessAction.objects.filter(kind="cook").exists())

    def test_household_day_is_shared_by_matching_and_actual_use(self):
        HouseholdSettings.objects.create(time_zone="Pacific/Kiritimati")
        tomato = make_lot(self.user, "番茄", package_date_status="known", package_date="2026-01-01")
        make_lot(self.user, "鸡蛋")
        instant = datetime(2026, 1, 1, 13, 0, tzinfo=py_timezone.utc)
        with patch("django.utils.timezone.now", return_value=instant):
            detail = meals_service.get_recipe(self.user, "tomato-egg")
            self.assertFalse(detail["has_all"])
            with self.assertRaises(inventory_service.InventoryError) as caught:
                inventory_service.apply_action(self.user, {
                    "request_id": str(uuid4()), "kind": "cook",
                    "items": [{"lot_id": tomato.pk, "version": 0, "quantity": "1", "unit": "piece"}],
                })
        self.assertEqual(caught.exception.code, "needs_review")
