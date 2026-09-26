"""Stage 07A rules and the existing transactional write boundary."""
from copy import deepcopy
import os
import time
from datetime import timedelta
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from core.models import MemberRole
from inventory import services as stock
from inventory.models import BusinessAction, InventoryLot, Movement
from meals.generation import conditions_for_generation, claim_next_task, process_task, queue_generation, cancel_task, GenerationUnavailable
from meals.models import GenerationTask, MenuPlan, MenuShoppingContribution, NutritionReference, RecipeRequest, TasteProfile, HouseholdTaste
from meals.models import FamilyRecipe, RecipeFeedback
from meals.structured import load_structured_catalog, validate_spec
from meals.workbench import calculate_nutrition, evaluate_menu, inventory_signature, parse_request_text, ranked_candidates, validate_conditions
from meals.workbench_views import _json_digest
from shopping.models import ShoppingItem


def conditions(**changes):
    row = {"raw_text": "", "people": 2, "meal_type": "menu", "stock_mode": "strict", "taste_mode": "usual",
           "goals": [], "excluded": [], "equipment": ["炒锅", "砧板", "菜刀", "碗", "汤锅", "量杯", "食物温度计"],
           "max_minutes": 40, "must_meet_time": False, "skill": "beginner", "spice_max": 1,
           "priority_names": [], "participants": [], "explore_cuisine": ""}
    row.update(changes)
    return row


class WorkbenchRuleTests(TestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_user(username="stage07a", password="test-only-strong-password-2026!")
        self.other = get_user_model().objects.create_user(username="stage07a-other", password="test-only-strong-password-2026!")
        MemberRole.objects.create(user=self.actor, role="member")
        MemberRole.objects.create(user=self.other, role="member")
        self.client.force_login(self.actor, backend="django.contrib.auth.backends.ModelBackend")
        self.recipes = load_structured_catalog()

    def lot(self, name, quantity, unit="g", **changes):
        payload = {"request_id": str(uuid4()), "ingredient_name": name, "quantity": quantity, "unit": unit,
                   "location": "fridge", "storage_status": "verified", "package_date_status": "not_applicable"}
        payload.update(changes)
        outcome = stock.create_lot(self.actor, payload)
        return InventoryLot.objects.get(pk=outcome["body"]["lot"]["id"])

    def request(self, values):
        return RecipeRequest.objects.create(owner=self.actor, request_id=uuid4(), digest="a" * 64,
            conditions=values, inventory_signature="b" * 64)

    def test_natural_language_keeps_high_carbs_and_low_added_sugar_distinct(self):
        parsed = parse_request_text("两个人健身后高蛋白、高碳水、少添加糖，半小时，不太辣，只能用炒锅和电饭煲")
        self.assertEqual(parsed["people"], 2)
        self.assertEqual(parsed["max_minutes"], 30)
        self.assertEqual(parsed["goals"], ["high_protein", "high_carbohydrate", "low_added_sugar"])
        self.assertNotIn("low_carbohydrate", parsed["goals"])
        validate_conditions(conditions(goals=parsed["goals"]))
        with self.assertRaises(ValueError):
            validate_conditions(conditions(goals=["high_carbohydrate", "low_carbohydrate"]))

    def test_strict_missing_salt_and_buy_gap_are_real(self):
        spec = self.recipes["pepper-potato"]
        self.lot("土豆", "300")
        self.lot("青椒", "120")
        self.lot("食用油", "15")
        strict = evaluate_menu([spec], servings=2, conditions=conditions(), actor=self.actor)
        self.assertFalse(strict["feasible"])
        self.assertEqual([(row["ingredient"], row["quantity"]) for row in strict["gaps"]], [("盐", "2")])
        buy = evaluate_menu([spec], servings=2, conditions=conditions(stock_mode="buy"), actor=self.actor)
        self.assertTrue(buy["feasible"])

    def test_net_gap_500_minus_300_and_priority_remaining(self):
        spec = deepcopy(self.recipes["broccoli"])
        spec["ingredients"][0]["quantity"] = "500"
        spec["steps"][0]["uses"][1]["quantity"] = "500"
        validate_spec(spec)
        lot = self.lot("西兰花", "300", manual_priority=True)
        result = evaluate_menu([spec], servings=2, conditions=conditions(stock_mode="buy"), actor=self.actor)
        self.assertEqual(result["allocations"][0]["lot_id"], lot.pk)
        self.assertEqual(result["allocations"][0]["quantity"], "300")
        self.assertEqual(result["allocations"][0]["remaining"], "0")
        self.assertIn({"recipe_id": "broccoli", "ingredient": "西兰花", "quantity": "200", "unit": "g",
                       "reason": "库存数量不足或单位未能可靠换算"}, result["gaps"])

    def test_unusable_lot_never_allocated(self):
        bad = self.lot("西兰花", "300", status="suspect")
        good = self.lot("西兰花", "300")
        result = evaluate_menu([self.recipes["broccoli"]], servings=2,
                               conditions=conditions(stock_mode="buy"), actor=self.actor)
        ids = {row["lot_id"] for row in result["allocations"]}
        self.assertIn(good.pk, ids)
        self.assertNotIn(bad.pk, ids)

    def test_joint_menu_cannot_reuse_the_same_eggs(self):
        self.lot("鸡蛋", "2", "piece")
        self.lot("番茄", "300")
        self.lot("黄瓜", "250")
        self.lot("食用油", "30")
        self.lot("盐", "4")
        one = evaluate_menu([self.recipes["tomato-egg"]], servings=2, conditions=conditions(), actor=self.actor)
        two = evaluate_menu([self.recipes["cucumber-egg"]], servings=2, conditions=conditions(), actor=self.actor)
        together = evaluate_menu([self.recipes["tomato-egg"], self.recipes["cucumber-egg"]],
                                 servings=2, conditions=conditions(), actor=self.actor)
        self.assertTrue(one["feasible"] and two["feasible"])
        self.assertFalse(together["feasible"])
        self.assertIn("鸡蛋", [row["ingredient"] for row in together["gaps"]])

    def test_unknown_nutrition_is_not_zero_and_seed_is_traceable(self):
        ref = NutritionReference.objects.get(ingredient_name="番茄", food_state="生")
        self.assertEqual(ref.source_id, "170457")
        result = calculate_nutrition([self.recipes["tomato-egg"]], 2)
        self.assertIsNone(result["whole"]["protein_g"])
        self.assertIsNone(result["whole"]["added_sugar_g"])
        self.assertIn("鸡蛋（无可靠克重）", result["unknown"]["protein_g"])

    def test_hard_restrictions_union_and_private_pages(self):
        HouseholdTaste.objects.create(pk=1, data={"allergens": ["鸡蛋"], "liked_cuisines": ["粤菜"]}, version=1)
        TasteProfile.objects.create(user=self.actor, data={"allergens": [], "liked_cuisines": ["川菜"]}, version=1)
        result = evaluate_menu([self.recipes["tomato-egg"]], servings=2,
                               conditions=conditions(stock_mode="buy"), actor=self.actor)
        self.assertFalse(result["feasible"])
        plan = self.request(conditions())
        self.client.force_login(self.other, backend="django.contrib.auth.backends.ModelBackend")
        self.assertEqual(self.client.get(f"/recipes/workbench/{plan.pk}/").status_code, 404)

    def test_provider_payload_omits_raw_text_and_member_ids(self):
        outgoing = conditions_for_generation(conditions(raw_text="私人信息", participants=[self.other.pk]))
        self.assertNotIn("raw_text", outgoing)
        self.assertNotIn("participants", outgoing)

    def test_piece_does_not_convert_to_unrecorded_grams(self):
        self.lot("鸡蛋", "120", "g")
        result = evaluate_menu([self.recipes["tomato-egg"]], servings=2,
                               conditions=conditions(stock_mode="buy"), actor=self.actor)
        self.assertIn("鸡蛋", [row["ingredient"] for row in result["gaps"]])

    def test_people_change_recomputes_gaps_and_nutrition(self):
        self.lot("西兰花", "300")
        result_two = evaluate_menu([self.recipes["broccoli"]], servings=2,
                                   conditions=conditions(stock_mode="buy"), actor=self.actor)
        result_four = evaluate_menu([self.recipes["broccoli"]], servings=4,
                                    conditions=conditions(stock_mode="buy", people=4), actor=self.actor)
        gap_two = next((row["quantity"] for row in result_two["gaps"] if row["ingredient"] == "西兰花"), None)
        gap_four = next(row["quantity"] for row in result_four["gaps"] if row["ingredient"] == "西兰花")
        self.assertIsNone(gap_two)
        self.assertEqual(gap_four, "300")
        self.assertEqual(Decimal(result_four["nutrition"]["whole"]["protein_g"]),
                         Decimal(result_two["nutrition"]["whole"]["protein_g"]) * 2)

    def test_cantonese_default_and_explore_change_ranking_without_weakening_limit(self):
        HouseholdTaste.objects.create(pk=1, data={"liked_cuisines": ["粤菜"], "spice_max": 1}, version=1)
        base = conditions(stock_mode="buy", equipment=[*conditions()["equipment"], "蒸锅"])
        usual = ranked_candidates(self.actor, base)
        explore = ranked_candidates(self.actor, {**base, "taste_mode": "explore", "explore_cuisine": "川菜"})
        usual_ids = [row["spec"]["id"] for row in usual]
        explore_ids = [row["spec"]["id"] for row in explore]
        self.assertLess(usual_ids.index("cantonese-steamed-tofu"), usual_ids.index("tofu-potato-mild"))
        self.assertLess(explore_ids.index("tofu-potato-mild"), explore_ids.index("cantonese-steamed-tofu"))
        HouseholdTaste.objects.filter(pk=1).update(data={"liked_cuisines": ["粤菜"], "spice_max": 0})
        blocked = ranked_candidates(self.actor, {**base, "taste_mode": "explore", "explore_cuisine": "川菜"})
        self.assertNotIn("tofu-potato-mild", [row["spec"]["id"] for row in blocked])

    def test_unshared_participant_requires_manual_confirmation(self):
        self.lot("西兰花", "300")
        self.lot("食用油", "12")
        self.lot("盐", "2")
        plan = self.request(conditions(participants=[self.other.pk]))
        menu = MenuPlan.objects.create(owner=self.actor, recipe_request=plan, recipe_ids=["broccoli"])
        page = self.client.get(f"/recipes/workbench/menu/{menu.pk}/")
        self.assertTrue(page.context["participants_need_manual_check"])
        data = {"snapshot": page.context["snapshot"], "request_id": str(uuid4()), "confirm_use": "on"}
        for row in page.context["cook_lots"]:
            data[f"actual_{row['lot_id']}"] = row["quantity"]
        self.assertEqual(self.client.post(f"/recipes/workbench/menu/{menu.pk}/cook/", data).status_code, 409)
        self.assertEqual(BusinessAction.objects.filter(kind="cook").count(), 0)

    def test_stale_menu_rejects_cook_after_lot_status_change(self):
        lot = self.lot("西兰花", "300")
        self.lot("食用油", "12")
        self.lot("盐", "2")
        plan = self.request(conditions())
        menu = MenuPlan.objects.create(owner=self.actor, recipe_request=plan, recipe_ids=["broccoli"])
        page = self.client.get(f"/recipes/workbench/menu/{menu.pk}/")
        data = {"snapshot": page.context["snapshot"], "request_id": str(uuid4()), "confirm_use": "on"}
        for row in page.context["cook_lots"]:
            data[f"actual_{row['lot_id']}"] = row["quantity"]
        stock.edit_lot(self.actor, lot.pk, {"request_id": str(uuid4()), "version": lot.version, "status": "suspect"})
        self.assertEqual(self.client.post(f"/recipes/workbench/menu/{menu.pk}/cook/", data).status_code, 409)
        self.assertEqual(BusinessAction.objects.filter(kind="cook").count(), 0)

    def test_queue_is_private_and_cancellation_prevents_late_publish(self):
        values = conditions(stock_mode="buy")
        plan = self.request(values)
        plan.inventory_signature = inventory_signature()
        plan.save(update_fields=["inventory_signature"])
        with patch.dict(os.environ, {"SHIJIN_RECIPE_PROVIDER": "ollama", "SHIJIN_RECIPE_MODEL": "test-only"}):
            task = queue_generation(self.actor, plan, str(uuid4()))
            same = queue_generation(self.actor, plan, str(task.request_id))
            self.assertEqual(task.pk, same.pk)
            self.client.force_login(self.other, backend="django.contrib.auth.backends.ModelBackend")
            self.assertEqual(self.client.get(f"/recipes/generation/{task.pk}/status/").status_code, 404)
            claimed = claim_next_task()
            self.assertEqual(claimed, task.pk)
            cancel_task(self.actor, task.pk)
            with patch("meals.generation.OllamaProvider.generate", return_value=self.recipes["broccoli"]):
                process_task(task.pk)
            task.refresh_from_db()
            self.assertEqual(task.status, "cancelled")
            self.assertIsNone(task.result)

    def test_expired_queued_task_recovers_as_timeout(self):
        plan = self.request(conditions(stock_mode="buy"))
        with patch.dict(os.environ, {"SHIJIN_RECIPE_PROVIDER": "ollama", "SHIJIN_RECIPE_MODEL": "test-only"}):
            task = queue_generation(self.actor, plan, str(uuid4()))
            GenerationTask.objects.filter(pk=task.pk).update(deadline_at=timezone.now() - timedelta(seconds=1))
            self.assertIsNone(claim_next_task())
            task.refresh_from_db()
            self.assertEqual(task.status, "timed_out")

    def test_mock_generation_checks_result_then_explicit_save(self):
        plan = self.request(conditions(stock_mode="buy"))
        plan.inventory_signature = inventory_signature()
        plan.save(update_fields=["inventory_signature"])
        with patch.dict(os.environ, {"SHIJIN_RECIPE_PROVIDER": "ollama", "SHIJIN_RECIPE_MODEL": "test-only"}):
            task = queue_generation(self.actor, plan, str(uuid4()))
            self.assertEqual(claim_next_task(), task.pk)
            with patch("meals.generation.OllamaProvider.generate", return_value=self.recipes["broccoli"]):
                process_task(task.pk)
        task.refresh_from_db()
        self.assertEqual(task.status, "success")
        self.assertEqual(FamilyRecipe.objects.count(), 0)
        self.assertEqual(InventoryLot.objects.count(), 0)
        self.assertEqual(ShoppingItem.objects.count(), 0)
        self.assertEqual(self.client.get(f"/recipes/generation/{task.pk}/").status_code, 200)
        self.assertEqual(self.client.post(f"/recipes/generation/{task.pk}/save/",
                                          {"request_id": str(task.request_id)}).status_code, 302)
        self.assertEqual(FamilyRecipe.objects.count(), 1)

    def test_invalid_mock_model_output_fails_without_new_recipe(self):
        plan = self.request(conditions(stock_mode="buy"))
        plan.inventory_signature = inventory_signature()
        plan.save(update_fields=["inventory_signature"])
        bad = deepcopy(self.recipes["broccoli"])
        bad["ingredients"][0]["quantity"] = "-5"
        with patch.dict(os.environ, {"SHIJIN_RECIPE_PROVIDER": "ollama", "SHIJIN_RECIPE_MODEL": "test-only"}):
            task = queue_generation(self.actor, plan, str(uuid4()))
            self.assertEqual(claim_next_task(), task.pk)
            with patch("meals.generation.OllamaProvider.generate", return_value=bad):
                process_task(task.pk)
        task.refresh_from_db()
        self.assertEqual(task.status, "failed")
        self.assertEqual(task.error_code, "validation_failed")
        self.assertEqual(FamilyRecipe.objects.count(), 0)

    def test_feedback_is_private_and_clearable(self):
        plan = self.request(conditions(stock_mode="buy"))
        url = f"/recipes/workbench/{plan.pk}/feedback/broccoli/"
        self.assertEqual(self.client.post(url, {"verdict": "like"}).status_code, 302)
        self.assertEqual(RecipeFeedback.objects.get(user=self.actor).verdict, "like")
        self.client.force_login(self.other, backend="django.contrib.auth.backends.ModelBackend")
        self.assertEqual(self.client.post(url, {"verdict": "clear"}).status_code, 404)
        self.assertEqual(RecipeFeedback.objects.get(user=self.actor).verdict, "like")
        self.client.force_login(self.actor, backend="django.contrib.auth.backends.ModelBackend")
        self.assertEqual(self.client.post(url, {"verdict": "clear"}).status_code, 302)
        self.assertFalse(RecipeFeedback.objects.filter(user=self.actor).exists())

    def test_provider_disabled_is_honest_and_local_page_works(self):
        plan = self.request(conditions(stock_mode="buy"))
        with patch.dict(os.environ, {"SHIJIN_RECIPE_PROVIDER": "off", "SHIJIN_RECIPE_MODEL": ""}):
            with self.assertRaises(GenerationUnavailable):
                queue_generation(self.actor, plan, str(uuid4()))
        self.assertEqual(self.client.get(f"/recipes/workbench/{plan.pk}/").status_code, 200)

    def test_two_person_fitness_dinner_form_to_menu_without_auto_writes(self):
        for name, quantity in (("豆腐", "400"), ("土豆", "400"), ("干辣椒", "2"),
                               ("食用油", "16"), ("盐", "3")):
            self.lot(name, quantity)
        request_id = uuid4()
        data = {"request_id": str(request_id), "raw_text": "两个人，健身后想吃高蛋白、高碳水、少添加糖，半小时左右，不太辣",
                "people": "2", "meal_type": "single", "stock_mode": "strict", "taste_mode": "explore",
                "goals": ["high_protein", "high_carbohydrate", "low_added_sugar"], "excluded": "",
                "equipment": ["炒锅", "砧板", "菜刀", "碗"], "priority_names": "土豆", "max_minutes": "30",
                "spice_max": "1", "skill": "beginner", "explore_cuisine": "川菜", "participants": ""}
        self.assertEqual(self.client.get("/recipes/?q=", secure=True).status_code, 200)
        self.assertEqual(self.client.post("/recipes/workbench/", data).status_code, 200)
        confirmation = self.client.post("/recipes/workbench/confirm/", data)
        self.assertEqual(confirmation.status_code, 302)
        plan = RecipeRequest.objects.get(request_id=request_id)
        self.assertEqual(plan.conditions["goals"], data["goals"])
        result_page = self.client.get(f"/recipes/workbench/{plan.pk}/")
        self.assertEqual(result_page.status_code, 200)
        self.assertIn("tofu-potato-mild", [row["spec"]["id"] for row in result_page.context["candidates"]])
        self.assertEqual(self.client.post(f"/recipes/workbench/{plan.pk}/menu/",
            {"request_id": str(uuid4()), "recipe_id": ["tofu-potato-mild"]}).status_code, 302)
        menu = MenuPlan.objects.get()
        self.assertEqual(self.client.get(f"/recipes/workbench/menu/{menu.pk}/").status_code, 200)
        self.assertEqual(ShoppingItem.objects.count(), 0)
        self.assertEqual(BusinessAction.objects.filter(kind="cook").count(), 0)

    def test_structure_rejects_extra_ingredient_and_html(self):
        spec = deepcopy(self.recipes["broccoli"])
        spec["steps"][0]["uses"].append({"name": "糖", "quantity": "2", "unit": "g"})
        with self.assertRaises(ValueError):
            validate_spec(spec)

    def test_new_editorial_recipe_opens_full_detail(self):
        response = self.client.get("/recipes/tofu-potato-mild/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "微辣土豆豆腐炒")
        self.assertContains(response, "分步烹饪")
        spec = deepcopy(self.recipes["broccoli"])
        spec["steps"][0]["action"] = "<script>alert(1)</script>"
        with self.assertRaises(ValueError):
            validate_spec(spec)

    def test_menu_shopping_requires_confirmation_and_is_idempotent(self):
        plan = self.request(conditions(stock_mode="buy"))
        menu = MenuPlan.objects.create(owner=self.actor, recipe_request=plan, recipe_ids=["broccoli"])
        page = self.client.get(f"/recipes/workbench/menu/{menu.pk}/")
        self.assertEqual(page.status_code, 200)
        snapshot = page.context["snapshot"]
        self.assertEqual(ShoppingItem.objects.count(), 0)
        post = {"snapshot": snapshot, "gap": ["西兰花|g"]}
        url = f"/recipes/workbench/menu/{menu.pk}/shopping/"
        self.assertEqual(self.client.post(url, post).status_code, 302)
        self.assertEqual(ShoppingItem.objects.count(), 1)
        self.assertEqual(self.client.post(url, post).status_code, 302)
        self.assertEqual(MenuShoppingContribution.objects.count(), 1)

    def test_menu_shopping_amount_can_be_adjusted_without_changing_net_gap(self):
        plan = self.request(conditions(stock_mode="buy"))
        menu = MenuPlan.objects.create(owner=self.actor, recipe_request=plan, recipe_ids=["broccoli"])
        page = self.client.get(f"/recipes/workbench/menu/{menu.pk}/")
        self.assertEqual(page.status_code, 200)
        gap = next(row for row in page.context["purchase_gaps"] if row["name"] == "西兰花")
        self.assertEqual(gap["quantity"], "300")
        post = {"snapshot": page.context["snapshot"], "gap": ["西兰花|g"], "buy_西兰花|g": "350"}
        url = f"/recipes/workbench/menu/{menu.pk}/shopping/"
        self.assertEqual(self.client.post(url, post).status_code, 302)
        self.assertEqual(ShoppingItem.objects.get().quantity_milli, 350000)
        self.assertEqual(self.client.post(url, post).status_code, 302)
        self.assertEqual(ShoppingItem.objects.count(), 1)

    def test_menu_cook_uses_existing_ledger_and_rechecks_version(self):
        lot = self.lot("西兰花", "300")
        self.lot("食用油", "12")
        self.lot("盐", "2")
        plan = self.request(conditions())
        menu = MenuPlan.objects.create(owner=self.actor, recipe_request=plan, recipe_ids=["broccoli"])
        url = f"/recipes/workbench/menu/{menu.pk}/"
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        data = {"snapshot": page.context["snapshot"], "request_id": str(uuid4()), "confirm_use": "on"}
        for row in page.context["cook_lots"]:
            data[f"actual_{row['lot_id']}"] = row["quantity"]
        cook_url = url + "cook/"
        response = self.client.post(cook_url, data)
        self.assertEqual(response.status_code, 302, response.content.decode())
        lot.refresh_from_db()
        self.assertEqual(lot.quantity_milli, 0)
        self.assertEqual(self.client.post(cook_url, data).status_code, 302)
        self.assertEqual(BusinessAction.objects.filter(kind="cook").count(), 1)
        self.assertEqual(Movement.objects.filter(action__kind="cook").count(), 3)
        menu.refresh_from_db()
        self.assertIsNotNone(menu.executed_action_id)
        self.assertEqual(self.client.post(cook_url, {**data, "request_id": str(uuid4())}).status_code, 409)

    def test_actual_oil_change_recomputes_from_ledger(self):
        self.lot("西兰花", "300")
        oil = self.lot("食用油", "12")
        self.lot("盐", "2")
        plan = self.request(conditions())
        menu = MenuPlan.objects.create(owner=self.actor, recipe_request=plan, recipe_ids=["broccoli"])
        url = f"/recipes/workbench/menu/{menu.pk}/"
        page = self.client.get(url)
        planned = Decimal(page.context["result"]["nutrition"]["whole"]["fat_g"])
        data = {"snapshot": page.context["snapshot"], "request_id": str(uuid4()), "confirm_use": "on"}
        for row in page.context["cook_lots"]:
            data[f"actual_{row['lot_id']}"] = "10" if row["lot_id"] == oil.pk else row["quantity"]
        self.assertEqual(self.client.post(url + "cook/", data).status_code, 302)
        menu.refresh_from_db()
        oil.refresh_from_db()
        self.assertEqual(oil.quantity_milli, 2000)
        self.assertLess(Decimal(menu.actual_nutrition["whole"]["fat_g"]), planned)


class SlowGenerationIsolationTests(TransactionTestCase):
    def test_stock_write_can_finish_while_mock_model_waits(self):
        actor = get_user_model().objects.create_user(username="slow-worker-test", password="test-only-strong-password-2026!")
        MemberRole.objects.create(user=actor, role="member")
        values = conditions(stock_mode="buy")
        plan = RecipeRequest.objects.create(owner=actor, request_id=uuid4(), digest="a" * 64,
            conditions=values, inventory_signature=inventory_signature())
        entered = Event()
        release = Event()

        def slow_generate(**kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test worker was not released")
            return load_structured_catalog()["broccoli"]

        with patch.dict(os.environ, {"SHIJIN_RECIPE_PROVIDER": "ollama", "SHIJIN_RECIPE_MODEL": "test-only"}):
            task = queue_generation(actor, plan, str(uuid4()))
            self.assertEqual(claim_next_task(), task.pk)
            with patch("meals.generation.OllamaProvider.generate", side_effect=slow_generate):
                def worker():
                    close_old_connections()
                    try:
                        process_task(task.pk)
                    finally:
                        close_old_connections()

                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(worker)
                    self.assertTrue(entered.wait(3))
                    started = time.perf_counter()
                    stock.create_lot(actor, {"request_id": str(uuid4()), "ingredient_name": "西兰花",
                        "quantity": "300", "unit": "g", "location": "fridge", "storage_status": "verified",
                        "package_date_status": "not_applicable"})
                    elapsed = time.perf_counter() - started
                    release.set()
                    future.result(timeout=5)
        self.assertLess(elapsed, 1.5)
        self.assertEqual(InventoryLot.objects.count(), 1)
