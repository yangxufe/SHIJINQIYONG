"""Translate optional entry controls to the existing inventory contract."""

from datetime import date, timedelta

from inventory import services


def normalize_entry(payload):
    fields = dict(services._object(payload))
    if "shelf_life_mode" not in fields:
        return fields
    mode = services._choice(fields.pop("shelf_life_mode"), {"date", "days"}, "保质期填写方式")
    days = fields.pop("shelf_life_days", "")
    start = fields.pop("shelf_life_start", "")
    if "package_date_status" in fields:
        services._fail("选择保质期填写方式后，无需另传包装日期状态。")
    if mode == "date":
        end = services._date(fields.get("package_date"), "保质期截止日期")
    elif days == "" and start == "":
        end = None
    else:
        if days == "" or start == "":
            services._fail("请同时填写保质期天数和起算日期。")
        count = services._integer(days, "保质期天数", 1, 36500)
        start_date = services._date(start, "起算日期")
        if start_date is None:
            services._fail("请填写起算日期。")
        try:
            end = (date.fromisoformat(start_date) + timedelta(days=count)).isoformat()
        except OverflowError:
            services._fail("计算后的截止日期超出支持范围。")
    fields["package_date"] = end
    fields["package_date_status"] = "known" if end else "unknown"
    return fields
