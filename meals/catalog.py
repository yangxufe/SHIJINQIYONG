"""Versioned local recipes and explicit, collision-free ingredient aliases."""

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path


CATALOG_PATH = Path(__file__).resolve().parent / "data" / "recipes.json"
ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def _name(value, limit=80):
    if not isinstance(value, str):
        raise ValueError("Recipe text must be a string")
    value = unicodedata.normalize("NFC", value.strip())
    if not value or len(value) > limit or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Invalid recipe text")
    return value


@lru_cache(maxsize=1)
def load_catalog():
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"aliases", "recipes"}:
        raise ValueError("Invalid recipe catalog")
    aliases = data["aliases"]
    recipes = data["recipes"]
    if not isinstance(aliases, dict) or not isinstance(recipes, list) or not 1 <= len(recipes) <= 30:
        raise ValueError("Invalid recipe catalog")
    canonical_by_name = {}
    for canonical, names in aliases.items():
        canonical = _name(canonical)
        if not isinstance(names, list) or len(names) > 20:
            raise ValueError("Invalid aliases")
        for name in [canonical, *names]:
            name = _name(name)
            if name in canonical_by_name:
                raise ValueError("Duplicate ingredient alias")
            canonical_by_name[name] = canonical
    ids = set()
    validated = []
    for raw in recipes:
        if not isinstance(raw, dict) or set(raw) != {"id", "name", "ingredients", "steps", "category", "tags"}:
            raise ValueError("Invalid recipe")
        recipe_id = raw["id"]
        if not isinstance(recipe_id, str) or not ID_PATTERN.fullmatch(recipe_id) or len(recipe_id) > 40 or recipe_id in ids:
            raise ValueError("Invalid recipe id")
        ids.add(recipe_id)
        ingredients = raw["ingredients"]
        steps = raw["steps"]
        tags = raw["tags"]
        if not isinstance(ingredients, list) or not 1 <= len(ingredients) <= 10 or not isinstance(steps, list) or not 1 <= len(steps) <= 10:
            raise ValueError("Invalid recipe content")
        if not isinstance(tags, list) or len(tags) > 6:
            raise ValueError("Invalid recipe tags")
        ingredients = [_name(name) for name in ingredients]
        if len(set(ingredients)) != len(ingredients) or any(name not in aliases for name in ingredients):
            raise ValueError("Recipe ingredient missing from aliases")
        tags = [_name(tag, 16) for tag in tags]
        if len(set(tags)) != len(tags):
            raise ValueError("Duplicate recipe tags")
        validated.append({"id": recipe_id, "name": _name(raw["name"]), "ingredients": ingredients,
                          "steps": [_name(step, 200) for step in steps], "category": _name(raw["category"], 20), "tags": tags})
    return validated, canonical_by_name
