"use strict";

const shelfField = document.querySelector(".shelf-life-field");
if (shelfField) {
  const dateInput = shelfField.querySelector('[name="package_date"]');
  const daysInput = shelfField.querySelector('[name="shelf_life_days"]');
  const startInput = shelfField.querySelector('[name="shelf_life_start"]');
  const preview = shelfField.querySelector("#shelf-life-preview");
  const update = () => {
    const useDays = shelfField.querySelector('[name="shelf_life_mode"]:checked').value === "days";
    dateInput.disabled = useDays;
    daysInput.disabled = !useDays;
    startInput.disabled = !useDays;
    daysInput.required = startInput.required = useDays && Boolean(daysInput.value || startInput.value);
    preview.textContent = "截止日期 = 起算日期 + 天数";
    if (!useDays || !daysInput.value || !startInput.value) return;
    const days = Number(daysInput.value);
    const start = new Date(`${startInput.value}T00:00:00Z`);
    if (!Number.isInteger(days) || days < 1 || days > 36500 || Number.isNaN(start.getTime())) {
      preview.textContent = "请填写有效的起算日期和 1–36500 的整数天数。";
      return;
    }
    start.setUTCDate(start.getUTCDate() + days);
    preview.textContent = start.getUTCFullYear() <= 9999 ? `截止日期：${start.toISOString().slice(0, 10)}` : "计算后的截止日期超出支持范围。";
  };
  shelfField.addEventListener("input", update);
  shelfField.addEventListener("change", update);
  shelfField.closest("form").addEventListener("reset", () => setTimeout(update, 0));
  update();
}
