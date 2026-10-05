"use strict";

const page = document.querySelector("#inventory-list-page");
const searchForm = document.querySelector("#inventory-search");
const queryInput = document.querySelector("#inventory-query");
const searchState = document.querySelector("#search-state");
const csrfToken = document.querySelector('input[name="csrfmiddlewaretoken"]')?.value;
const boundForms = new WeakSet();
let listSequence = 0;
let listController = null;
let debounceTimer = null;

function element(tag, value, className = "") {
  const node = document.createElement(tag);
  node.textContent = value;
  if (className) node.className = className;
  return node;
}

function hidden(form, name, value) {
  const input = document.createElement("input");
  input.type = "hidden";
  input.name = name;
  input.value = value;
  form.append(input);
}

function field(form, caption, name, options = null) {
  const label = document.createElement("label");
  label.append(document.createTextNode(caption));
  let control;
  if (options) {
    control = document.createElement("select");
    for (const [value, text] of options) control.add(new Option(text, value));
  } else {
    control = document.createElement("input");
    control.maxLength = name === "note" ? 200 : 16;
    if (name === "quantity") {
      control.inputMode = "decimal";
      control.required = true;
    }
  }
  control.name = name;
  label.append(control);
  form.append(label);
}

function renderLot(lot) {
  const card = document.createElement("article");
  card.className = "panel lot-card";
  card.id = `lot-${lot.id}`;
  card.dataset.lotId = lot.id;
  card.append(element("h3", lot.name));
  const summary = document.createElement("p");
  const amount = element("strong", `${lot.quantity} ${lot.unit_label}`);
  summary.append(amount, document.createTextNode(` · ${lot.location_label} · ${lot.status_label} · 储存：${lot.storage_status_label}`));
  card.append(summary);
  card.append(element("p", `食材：${lot.ingredient_name}；${lot.manual_priority ? "手动优先；" : ""}计划：${lot.planned_use_date || "未记录"}；包装日期：${lot.package_date || lot.package_date_status_label}；版本 ${lot.version}；更新 ${lot.updated_at_label}`, "small-note"));
  if (lot.status === "active" || lot.status === "suspect") {
    const edit = document.createElement("a");
    edit.href = `/inventory/${encodeURIComponent(lot.id)}/edit/`;
    edit.textContent = "编辑批次信息";
    card.append(edit);
    const form = document.createElement("form");
    form.method = "post";
    form.action = "/inventory/action/";
    form.dataset.inventoryForm = "";
    form.dataset.apiUrl = page.dataset.actionUrl;
    form.dataset.apiMethod = "POST";
    form.dataset.inventoryKind = "action";
    hidden(form, "csrfmiddlewaretoken", csrfToken);
    hidden(form, "request_id", crypto.randomUUID());
    hidden(form, "lot_id", lot.id);
    hidden(form, "version", lot.version);
    hidden(form, "unit", lot.unit);
    const fields = document.createElement("div");
    fields.className = "fields";
    field(fields, "记录类型 ", "kind", [["cook", "用于做饭"], ["eat", "直接食用"], ["discard", "真实丢弃"], ["correct", "校正库存"]]);
    field(fields, "本次数量／校正后余额 ", "quantity");
    field(fields, "说明（校正必填） ", "note");
    form.append(fields, element("p", "“校正库存”填写新的剩余量；其他类型填写本次用量。提交后才会扣减并记录流水。", "small-note"));
    const button = element("button", "确认记录");
    button.type = "submit";
    const state = element("span", "", "submit-state");
    state.setAttribute("role", "status");
    state.setAttribute("aria-live", "polite");
    form.append(button, state);
    bindForm(form);
    card.append(form);
  }
  return card;
}

function renderList(data) {
  const list = document.querySelector("#lots-list");
  const cards = data.items.map(renderLot);
  if (cards.length) list.replaceChildren(...cards);
  else list.replaceChildren(element("p", data.query ? "没有匹配的批次。" : "还没有批次记录。先录入最容易忘记的 5 样即可。", "note"));
  document.querySelector("#lots-count").textContent = data.count;
  const pagination = document.querySelector(".pagination");
  pagination.replaceChildren();
  const link = (pageNumber, caption) => {
    const anchor = document.createElement("a");
    anchor.href = `?${new URLSearchParams({ q: data.query, page: String(pageNumber) })}`;
    anchor.textContent = caption;
    return anchor;
  };
  if (data.page > 1) pagination.append(link(data.page - 1, "上一页"));
  pagination.append(element("span", `第 ${data.page} / ${data.pages} 页`));
  if (data.page < data.pages) pagination.append(link(data.page + 1, "下一页"));
}

async function refreshList(query = "", pageNumber = 1) {
  if (!page) return;
  const sequence = ++listSequence;
  if (listController) listController.abort();
  listController = new AbortController();
  searchState.textContent = "读取中…";
  const url = new URL(page.dataset.listUrl, window.location.href);
  url.searchParams.set("q", query);
  url.searchParams.set("page", pageNumber);
  const response = await fetch(url, { credentials: "same-origin", cache: "no-store", signal: listController.signal });
  if (!response.ok) throw new Error(response.status === 401 ? "登录已失效，请重新登录。" : "读取失败，请重试。");
  const data = await response.json();
  if (sequence !== listSequence) return false;
  renderList(data);
  searchState.textContent = "已按服务器最新记录更新。";
  window.history.replaceState(null, "", `?${new URLSearchParams({ q: data.query, page: String(data.page) })}`);
  return true;
}

async function lookupCommitted(requestId) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch(`/api/actions/by-request/${encodeURIComponent(requestId)}/`, { credentials: "same-origin", cache: "no-store", signal: controller.signal });
    if (response.status !== 200) return null;
    return (await response.json()).result;
  } catch (_) {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

function formPayload(form) {
  const fields = Object.fromEntries(new FormData(form));
  delete fields.csrfmiddlewaretoken;
  if (form.dataset.inventoryKind !== "action") return fields;
  return {
    request_id: fields.request_id,
    kind: fields.kind,
    note: fields.note || "",
    items: [{ lot_id: fields.lot_id, version: fields.version, quantity: fields.quantity, unit: fields.unit }],
  };
}

function bindForm(form) {
  if (boundForms.has(form)) return;
  boundForms.add(form);
  let pendingPayload = null;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    const state = form.querySelector(".submit-state:not(#photo-state)");
    const csrf = form.querySelector('input[name="csrfmiddlewaretoken"]')?.value;
    if (!button || !state || !csrf) return;
    if (pendingPayload === null) pendingPayload = formPayload(form);
    button.disabled = true;
    state.dataset.state = "pending";
    state.textContent = "提交中…";
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(form.dataset.apiUrl, {
        method: form.dataset.apiMethod,
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        body: JSON.stringify(pendingPayload),
        signal: controller.signal,
      });
      if (response.ok) {
        await committed(form, state);
        pendingPayload = null;
        return;
      }
      if (response.status === 503 || response.status >= 500) {
        const found = await lookupCommitted(pendingPayload.request_id);
        if (found) {
          await committed(form, state);
          pendingPayload = null;
        } else {
          state.dataset.state = "unknown";
          state.textContent = "结果待核对。请保留本页，用原请求编号和原参数重试。";
        }
        return;
      }
      let message = "请求未完成，请核对后重试。";
      try { message = (await response.json()).error?.message || message; } catch (_) { /* No HTML insertion. */ }
      state.dataset.state = "error";
      state.textContent = response.status === 409 ? `${message} 请刷新后核对。` : message;
      if (response.status !== 409) pendingPayload = null;
    } catch (_) {
      const found = await lookupCommitted(pendingPayload.request_id);
      if (found) {
        await committed(form, state);
        pendingPayload = null;
      } else {
        state.dataset.state = "unknown";
        state.textContent = "结果待核对：连接中断。请保留本页，用原请求编号和原参数重试。";
      }
    } finally {
      clearTimeout(timer);
      button.disabled = false;
    }
  });
}

async function committed(form, state) {
  state.dataset.state = "success";
  state.textContent = "已保存，正在读取最新列表…";
  if (!page) {
    window.location.assign("/inventory/list/");
    return;
  }
  if (form.dataset.inventoryKind === "create") {
    form.reset();
    form.querySelector('input[name="request_id"]').value = crypto.randomUUID();
  }
  try {
    await refreshList(queryInput?.value || "");
    searchState.textContent = "已保存，并按服务器最新记录更新。";
  } catch (_) {
    searchState.textContent = "已保存，但列表读取失败。请手动刷新。";
  }
}

for (const form of document.querySelectorAll("[data-inventory-form]")) bindForm(form);

const photoInputs = [...document.querySelectorAll("#food-camera, #food-album")];
const photoButtons = [...document.querySelectorAll("[data-photo-input]")];
const photoState = document.querySelector("#photo-state");
const createForm = document.querySelector('form[data-inventory-kind="create"]');

async function photoAsJpeg(file) {
  if (file.size > 12_000_000) throw new Error("照片过大，请选择较小的照片。");
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("照片读取失败，请重试。"));
    reader.readAsDataURL(file);
  });
  const picture = new Image();
  picture.src = dataUrl;
  try { await picture.decode(); } catch (_) { throw new Error("无法读取照片，请使用 JPG、PNG 或手机相机拍摄。"); }
  const width = picture.naturalWidth;
  const height = picture.naturalHeight;
  if (!width || !height || width * height > 20_000_000) throw new Error("照片分辨率过大，请重拍。");
  const scale = Math.min(1, 1536 / Math.max(width, height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const context = canvas.getContext("2d");
  if (!context) throw new Error("此浏览器无法处理照片，请手动填写名称。");
  context.fillStyle = "#fff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(picture, 0, 0, canvas.width, canvas.height);
  const jpeg = canvas.toDataURL("image/jpeg", .8).split(",")[1];
  if (jpeg.length > 3_333_340) throw new Error("照片处理后仍过大，请重拍。");
  return jpeg;
}

for (const button of photoButtons) {
  button.addEventListener("click", () => document.getElementById(button.dataset.photoInput)?.click());
}

if (photoInputs.length && photoState && createForm) {
  const candidates = document.createElement("div");
  candidates.className = "photo-candidates";
  candidates.setAttribute("aria-label", "确认识别结果");
  photoState.after(candidates);
  for (const photoInput of photoInputs) photoInput.addEventListener("change", async () => {
    const file = photoInput.files?.[0];
    if (!file) return;
    const requestId = createForm.elements.request_id.value;
    const originalName = createForm.elements.ingredient_name.value;
    for (const control of [...photoButtons, ...photoInputs]) control.disabled = true;
    candidates.replaceChildren();
    photoState.textContent = "正在本机用 YOLO 检测…";
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const image = await photoAsJpeg(file);
      const csrf = createForm.querySelector('input[name="csrfmiddlewaretoken"]').value;
      const response = await fetch(createForm.dataset.photoUrl, {
        method: "POST", credentials: "same-origin", cache: "no-store", signal: controller.signal,
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        body: JSON.stringify({ image }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error?.message || "识别失败，请重试或手动填写名称。");
      if (createForm.elements.request_id.value !== requestId) return;
      if (data.candidates?.length) {
        photoState.textContent = "检测到以下候选。点击确认食材名称，再填写真实数量；检测分数不代表食品安全。";
        for (const candidate of data.candidates) {
          const button = element("button", `确认 ${candidate.ingredient_name}（检测分数 ${Math.round(candidate.confidence * 100)}%）`, "secondary-button");
          button.type = "button";
          button.addEventListener("click", () => {
            if (createForm.elements.request_id.value !== requestId) return;
            if (createForm.elements.ingredient_name.value !== originalName) {
              photoState.textContent = "你已手动修改名称，未覆盖；请自行核对。";
              candidates.replaceChildren();
              return;
            }
            createForm.elements.ingredient_name.value = candidate.ingredient_name;
            photoState.textContent = `已确认“${candidate.ingredient_name}”。请填写实际数量后保存。`;
            candidates.replaceChildren();
          });
          candidates.append(button);
        }
      } else {
        photoState.textContent = "没有检测到可确认的食材。请重拍清晰实物，也可以手动填写；YOLO 不读取包装文字。";
      }
    } catch (error) {
      if (createForm.elements.request_id.value === requestId) photoState.textContent = error.name === "AbortError" ? "检测超时，请稍后重试或手动填写。" : error.message || "识别失败，请手动填写名称。";
    } finally {
      clearTimeout(timer);
      photoInput.value = "";
      for (const control of [...photoButtons, ...photoInputs]) control.disabled = false;
    }
  });
  createForm.addEventListener("reset", () => { candidates.replaceChildren(); photoState.textContent = ""; });
}

if (page && searchForm && queryInput && searchState) {
  const search = () => refreshList(queryInput.value).catch((error) => {
    if (error.name !== "AbortError") searchState.textContent = error.message || "读取失败，当前仍显示上次结果。";
  });
  queryInput.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    if (listController) listController.abort();
    ++listSequence;
    debounceTimer = setTimeout(search, 250);
  });
  searchForm.addEventListener("submit", (event) => { event.preventDefault(); clearTimeout(debounceTimer); search(); });
  window.addEventListener("pageshow", (event) => { if (event.persisted) search(); });
}
