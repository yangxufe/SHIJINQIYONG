"""Seed a small, traceable offline subset of USDA SR Legacy; preserve user edits."""
import json
from pathlib import Path

from django.db import migrations


def seed(apps, schema_editor):
    reference = apps.get_model("meals", "NutritionReference")
    path = Path(__file__).resolve().parents[1] / "data" / "nutrition_sr_legacy.json"
    for row in json.loads(path.read_text(encoding="utf-8")):
        reference.objects.using(schema_editor.connection.alias).get_or_create(
            ingredient_name=row["ingredient_name"], food_state=row["food_state"],
            defaults={key: value for key, value in row.items() if key not in {"ingredient_name", "food_state"}},
        )


class Migration(migrations.Migration):
    dependencies = [("meals", "0002_familyrecipe_review_state_and_more")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
