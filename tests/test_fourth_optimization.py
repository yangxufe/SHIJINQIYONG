"""Fourth issue-list: optional conditions without weakening business boundaries."""
import re
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from core.models import MemberRole
from inventory.models import BusinessAction, InventoryLot, Movement
from meals.generation import conditions_for_generation
from meals.models import GenerationTask, HouseholdTaste, RecipeRequest
from meals.structured import load_structured_catalog
from meals.workbench import evaluate_menu, validate_conditions
from meals.workbench_forms import RecipeConditionsForm
from shopping.models import ShoppingItem
from tests.test_stage07a import conditions


class FourthOptimizationTests(TestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_user(username="fourth", password="Synthetic-fourth!2026")
        MemberRole.objects.create(user=self.actor, role="member")
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.actor, backend="django.contrib.auth.backends.ModelBackend")
        page = self.client.get("/recipes/workbench/?direct=1", secure=True)
        self.token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', page.content).group(1).decode()

    def payload(self, **changes):
        values = {"request_id": str(uuid4()), "people": "2", "meal_type": "single", "stock_mode": "buy", "taste_mode": "usual"}
        values.update(changes)
        return values

    def post(self, data, path="/recipes/workbench/confirm/"):
        return self.client.post(path, {**data, "csrfmiddlewaretoken": self.token}, secure=True, HTTP_ORIGIN="https://testserver")

    def test_footer_replacements_and_four_required_meal_fields(self):
        for path, text, href in (("/login/", "注册新账号", "/register/"), ("/register/", "登录已有账号", "/login/")):
            page = Client().get(path, secure=True)
            self.assertContains(page, f'<a href="{href}">{text}</a>', count=1)
            self.assertContains(page, '<a href="/welcome/">返回首页</a>', count=1)
            self.assertNotContains(page, "返回封面")
        page = self.client.get("/recipes/workbench/?direct=1", secure=True)
        self.assertContains(page, 'class="required-mark"', count=4)
        form = page.context["form"]
        self.assertEqual({name for name, field in form.fields.items() if field.required and not field.widget.is_hidden},
                         {"people", "meal_type", "stock_mode", "taste_mode"})
        self.assertContains(page, "时间是否必须满足")
        self.assertRegex(page.content.decode(), r'<label class="condition-check"[^>]*>\s*<input[^>]+name="must_meet_time"[^>]*>\s*<span>时间是否必须满足</span>')
        self.assertIsNone(form["max_minutes"].value())
        self.assertIsNone(form["spice_max"].value())

    @patch.dict("os.environ", {"SHIJIN_RECIPE_PROVIDER": "off"})
    def test_only_four_fields_submit_once_with_truthful_local_fallback(self):
        payload = self.payload(generate="yes")
        result = self.post(payload)
        self.assertEqual(result.status_code, 302)
        self.assertEqual(self.post(payload).url, result.url)
        plan = RecipeRequest.objects.get()
        self.assertEqual((plan.conditions["max_minutes"], plan.conditions["spice_max"], plan.conditions["skill"]), (None, None, ""))
        self.assertEqual(plan.conditions["equipment"], [])
        outgoing = conditions_for_generation(plan.conditions)
        self.assertIsNone(outgoing["max_minutes"])
        self.assertIsNone(outgoing["spice_max"])
        page = self.client.get(result.url, secure=True)
        self.assertContains(page, "本次未限定时间")
        self.assertContains(page, "本次未新增辣度上限")
        self.assertContains(page, "已改为本地菜谱匹配")
        self.assertEqual([model.objects.count() for model in (InventoryLot, Movement, BusinessAction, ShoppingItem, GenerationTask)], [0] * 5)
        self.assertEqual(self.post({**payload, "people": "3"}).status_code, 409)
        other = get_user_model().objects.create_user(username="fourth-other")
        MemberRole.objects.create(user=other, role="member")
        self.client.force_login(other, backend="django.contrib.auth.backends.ModelBackend")
        self.assertEqual(self.client.get(result.url, secure=True).status_code, 404)

    def test_required_fields_and_csrf_still_enforced(self):
        self.assertEqual(self.client.post("/recipes/workbench/confirm/", self.payload(), secure=True).status_code, 403)
        for key in ("people", "meal_type", "stock_mode", "taste_mode", "request_id"):
            with self.subTest(key=key):
                self.assertEqual(self.post(self.payload(**{key: ""})).status_code, 422)
        self.assertEqual(RecipeRequest.objects.count(), 0)

    def test_optional_values_are_bounded_and_time_conflict_is_explicit(self):
        for values in ({"max_minutes": "4"}, {"max_minutes": "1441"}, {"max_minutes": "NaN"},
                       {"spice_max": "-1"}, {"spice_max": "6"}, {"skill": "expert"}):
            with self.subTest(values=values):
                self.assertEqual(self.post(self.payload(**values)).status_code, 422)
        conflict = self.post(self.payload(must_meet_time="on"))
        self.assertContains(conflict, "请填写希望总耗时，或取消该勾选", status_code=422)
        self.assertEqual(RecipeRequest.objects.count(), 0)
        self.assertEqual(self.post(self.payload(must_meet_time="on", max_minutes="5", spice_max="0")).status_code, 302)
        plan = RecipeRequest.objects.get()
        self.assertEqual(plan.conditions["spice_max"], 0)
        self.assertTrue(plan.conditions["must_meet_time"])
        summary = self.client.get(f"/recipes/workbench/{plan.pk}/", secure=True)
        self.assertContains(summary, "本餐辣度上限 0")

    def test_empty_limits_preserve_saved_spice_allergy_stock_and_equipment_rules(self):
        spec = load_structured_catalog()["tofu-potato-mild"]
        values = conditions(stock_mode="buy", max_minutes=None, spice_max=None, skill="")
        validate_conditions(values)
        evaluate = lambda data: evaluate_menu([spec], servings=2, conditions=data, actor=self.actor)
        self.assertTrue(evaluate(values)["feasible"])
        self.assertFalse(evaluate({**values, "spice_max": 0})["feasible"])
        self.assertFalse(evaluate({**values, "stock_mode": "strict"})["feasible"])
        self.assertFalse(evaluate({**values, "equipment": []})["feasible"])
        preference = HouseholdTaste.objects.create(pk=1, data={"spice_max": 0}, version=1)
        self.assertFalse(evaluate(values)["feasible"])
        preference.data = {"allergens": ["豆腐"]}
        preference.save()
        self.assertFalse(evaluate(values)["feasible"])

    def test_empty_time_has_no_penalty_but_explicit_time_and_old_conditions_work(self):
        spec = load_structured_catalog()["tofu-potato-mild"]
        values = conditions(stock_mode="buy", max_minutes=None)
        unlimited = evaluate_menu([spec], servings=2, conditions=values, actor=self.actor)
        limited = evaluate_menu([spec], servings=2, conditions={**values, "max_minutes": 5}, actor=self.actor)
        self.assertTrue(unlimited["feasible"] and limited["feasible"])
        self.assertGreater(unlimited["score"], limited["score"])
        self.assertFalse(evaluate_menu([spec], servings=2, conditions={**values, "max_minutes": 5, "must_meet_time": True}, actor=self.actor)["feasible"])
        validate_conditions(conditions())
        for value in (True, -1, "30"):
            with self.assertRaises(ValueError):
                validate_conditions({**values, "max_minutes": value})

    def test_natural_language_confirmation_still_populates_optional_values(self):
        payload = self.payload(raw_text="两个人高蛋白、高碳水、少添加糖，半小时，不太辣，只能用炒锅和电饭煲")
        response = self.post(payload, "/recipes/workbench/")
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form["max_minutes"].value(), 30)
        self.assertEqual(form["spice_max"].value(), 1)
        self.assertEqual(form["goals"].value(), ["high_protein", "high_carbohydrate", "low_added_sugar"])
        self.assertEqual(RecipeRequest.objects.count(), 0)
        confirmed = RecipeConditionsForm(form.initial)
        self.assertTrue(confirmed.is_valid(), confirmed.errors)
