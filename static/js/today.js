"use strict";

const page = document.querySelector("#today-page");
const refresh = document.querySelector("#today-refresh");
const state = document.querySelector("#today-state");

function paragraph(value, className = "") {
  const node = document.createElement("p");
  node.textContent = value;
  if (className) node.className = className;
  return node;
}

function renderCards(target, lots, review, stockCount) {
  target.replaceChildren();
  if (lots.length === 0) {
    target.append(paragraph(review ? "目前没有待核对批次。" : stockCount ? "目前没有可安排的批次，请先查看“需要核对”。" : "还没有在库食材。先录入最容易忘记的 5 样，之后按真实情况补充。", "empty-state"));
    return;
  }
  for (const lot of lots) {
    const card = document.createElement("article");
    card.className = review ? "panel today-card review-card" : "panel today-card";
    const title = document.createElement("h3");
    title.textContent = lot.name;
    card.append(title, paragraph(`${lot.quantity} ${lot.unit_label} · ${lot.location_label}`));
    card.append(paragraph(review ? lot.reasons.join("；") : `${lot.reason}${lot.planned_use_date ? ` · 计划 ${lot.planned_use_date}` : ""}`, "small-note"));
    if (!review) card.append(paragraph(`包装日期：${lot.package_date || lot.package_date_status_label}；储存已由成员记录为已核对。`, "small-note"));
    const link = document.createElement("a");
    link.href = `/inventory/${encodeURIComponent(lot.id)}/edit/`;
    link.textContent = "查看批次";
    card.append(link);
    target.append(card);
  }
}

if (page && refresh && state) {
  let active = 0;
  refresh.addEventListener("click", async () => {
    const sequence = ++active;
    refresh.disabled = true;
    state.textContent = "读取中…";
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(page.dataset.todayUrl, { credentials: "same-origin", cache: "no-store", signal: controller.signal });
      if (!response.ok) throw new Error(response.status === 401 ? "登录已失效，请重新登录。" : "读取失败，请重试。");
      const data = await response.json();
      if (sequence !== active) return;
      renderCards(document.querySelector("#today-arrange"), data.arrange, false, data.stock_count);
      renderCards(document.querySelector("#today-review"), data.needs_review, true, data.stock_count);
      document.querySelector("#arrange-count").textContent = `${data.arrange_count} 批待安排`;
      document.querySelector("#review-count").textContent = `${data.needs_review_count} 批`;
      state.textContent = "已按服务器最新记录更新。";
    } catch (error) {
      if (sequence === active) state.textContent = error.message || "连接中断，当前显示上次读取结果。";
    } finally {
      clearTimeout(timer);
      if (sequence === active) refresh.disabled = false;
    }
  });
  window.addEventListener("pageshow", (event) => { if (event.persisted) refresh.click(); });
}
