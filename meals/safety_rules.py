"""Small referenced cooking temperature lookup, separate from untrusted recipe text."""

FSIS_SOURCE = "https://www.fsis.usda.gov/food-safety/safe-food-handling-and-preparation/food-safety-basics/safe-temperature-chart"
RULES = {
    "egg_71c": "含蛋混合菜中心至少 71°C（160°F）；用食物温度计核对。",
    "poultry_74c": "鸡肉等禽肉中心至少 74°C（165°F）；用食物温度计核对。",
    "ground_meat_71c": "绞肉中心至少 71°C（160°F）；用食物温度计核对。",
    "fish_63c": "鱼中心至少 63°C（145°F）；用食物温度计核对。",
    "leftover_74c": "复热剩菜中心至少 74°C（165°F）；用食物温度计核对。",
    "whole_meat_63c_rest3": "猪、牛等完整肉块中心至少 63°C（145°F），离火静置至少 3 分钟；用食物温度计核对。",
}


def notes(rule_ids):
    return [{"text": RULES[rule_id], "source": FSIS_SOURCE} for rule_id in rule_ids]
