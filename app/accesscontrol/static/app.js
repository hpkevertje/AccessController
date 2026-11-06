"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ---------------- Vertalingen / Translations / Traductions ---------------- */
const I18N = window.I18N || { nl: {} };
const LOCALES = window.LOCALES || { nl: "nl-BE" };

let currentLanguage = (() => {
  try {
    const stored = localStorage.getItem("lang");
    return I18N[stored] ? stored : "nl";
  } catch { return "nl"; }
})();

function t(key, vars) {
  const dict = I18N[currentLanguage] || I18N.nl;
  const text = dict[key] ?? I18N.nl[key] ?? key;
  return vars ? text.replace(/\{(\w+)\}/g, (m, k) => (vars[k] ?? m)) : text;
}

const categoryLabel = (cat) => t(`category.${cat}`);
const resultLabel = (res) => t(`result.${res}`);

function applyStaticTranslations() {
  $$("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  $$("[data-i18n-html]").forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
  $$("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
  $$("[data-i18n-title]").forEach((el) => { el.title = t(el.dataset.i18nTitle); });
}

function applyLanguage(lang, persist = true) {
  currentLanguage = I18N[lang] ? lang : "nl";
  if (persist) {
    try { localStorage.setItem("lang", currentLanguage); } catch { /* geen opslag */ }
  }
  document.documentElement.lang = currentLanguage;
  $("#language-selector").value = currentLanguage;
  applyStaticTranslations();
  const deviceForm = $("#device-form");
  if (deviceForm) deviceForm.tasmota_topic.placeholder = deviceTopicPlaceholder(deviceForm.relay_type.value);
  if (lastStatus) renderStatus();
  renderDeviceOptions();
  renderMemberHead();
  renderMembers();
  renderDeviceTable();
  if (!$("#tab-events").classList.contains("hidden")) loadEvents();
  if (!$("#tab-config").classList.contains("hidden")) loadConfig();
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: opts.body && !(opts.body instanceof FormData) ? { "Content-Type": "application/json" } : {},
    ...opts,
    body: opts.body && !(opts.body instanceof FormData) ? JSON.stringify(opts.body) : opts.body,
  });
  let data = null;
  try { data = await res.json(); } catch { /* geen json */ }
  if (!res.ok) {
    const err = new Error((data && data.detail) || t("error.api", { status: res.status }));
    err.errors = (data && data.errors) || [];
    err.status = res.status;
    throw err;
  }
  return data;
}

function toast(msg, error = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast" + (error ? " error" : "");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.add("hidden"), error ? 6000 : 3000);
}

function confirmDialog(title, text, okLabel = "OK") {
  const dlg = $("#dlg-confirm");
  $("#confirm-title").textContent = title;
  $("#confirm-text").textContent = text;
  $("#confirm-ok").textContent = okLabel;
  dlg.showModal();
  return new Promise((resolve) => {
    dlg.addEventListener("close", () => resolve(dlg.returnValue === "ok"), { once: true });
  });
}

const fmtTime = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString(LOCALES[currentLanguage] || "nl-BE", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
};
const fmtDur = (s) => {
  s = Math.max(0, Math.round(s));
  const m = Math.floor(s / 60), r = s % 60;
  return m ? `${m}:${String(r).padStart(2, "0")}` : `${r} s`;
};
const fmtSetting = (s) => (s >= 60 && s % 60 === 0 ? `${s / 60} min` : s >= 60 ? fmtDur(s) : `${s} s`);

/* ---------------- Tabs ---------------- */
$$(".tab").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
function showTab(name) {
  $$(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".panel").forEach((p) => p.classList.toggle("hidden", p.id !== `tab-${name}`));
  try { localStorage.setItem("tab", name); } catch { /* geen opslag */ }
  if (name === "events") loadEvents();
  if (name === "config") loadConfig();
}

/* ---------------- Status & bediening ---------------- */
let lastStatus = null;
async function loadStatus() {
  try {
    lastStatus = await api("api/status");
    renderStatus();
  } catch (e) {
    $("#mqtt-badge").className = "badge bad";
    $("#mqtt-badge").textContent = t("status.serverUnreachable");
  }
}

function badge(text, cls) { return `<span class="badge ${cls}">${esc(text)}</span>`; }

function renderStatus() {
  const s = lastStatus;
  const mb = $("#mqtt-badge");
  mb.className = "badge " + (s.mqtt.connected ? "ok" : "bad");
  mb.textContent = s.mqtt.connected ? t("status.mqttConnected") : t("status.mqttDisconnected");
  mb.title = s.mqtt.error || "";
  renderSmsBanner(s.sms_unread);

  $("#devices").innerHTML = s.devices.length ? s.devices.map((d) => {
    const id = d.id;
    if (!d.enabled) {
      return `<div class="device disabled"><h3>${esc(d.name)} ${badge(t("common.inactive"), "")}</h3>
        <div class="muted">${t("status.activateInConfig")}</div></div>`;
    }
    // Eén RTU-status: kabel (seriële verbinding) en GSM-netwerk samen.
    const noNetwork = ["niet geregistreerd", "geen SIM"].includes(d.gsm);
    const rtu = !d.serial_connected
      ? `<span class="badge bad" title="${esc(d.serial_error)}">${t("status.rtuCable")}</span>`
      : noNetwork
        ? `<span class="badge bad" title="GSM: ${esc(d.gsm)}">${t("status.rtuNoGsm")}</span>`
        : `<span class="badge ok" title="GSM: ${esc(d.gsm)}">${t("status.rtuOk")}</span>`;
    const esp = badge(t("status.relayModule") + " " + d.esp, d.esp === "online" ? "ok" : d.esp === "offline" ? "bad" : "warn");
    let relay = badge(t("status.relayUnknown"), "");
    if (d.relay === "on") relay = `<span class="badge ok relay-on" data-remaining="${d.relay_remaining_s ?? ""}">${t("status.relayOn")}${d.relay_remaining_s != null ? t("status.remaining", { time: fmtDur(d.relay_remaining_s) }) : ""}</span>`;
    else if (d.relay === "off") relay = badge(t("status.relayOff"), "");
    const long = d.on_seconds >= 10;
    const actions = long
      ? `<button class="primary" data-act="on" data-dev="${id}">${t("common.on")} (${fmtSetting(d.on_seconds)})</button>
         <button data-act="off" data-dev="${id}">${t("common.off")}</button>`
      : `<button class="primary" data-act="on" data-dev="${id}">${t("common.open")} (${fmtSetting(d.on_seconds)} ${t("common.pulse")})</button>`;
    const sms = d.last_sms
      ? `<div class="last-sms" title="${esc(d.last_sms.text)}"><span class="muted">${t("status.lastSms")} ${esc(fmtTime(d.last_sms.ts))}, ${t("status.from")} ${esc(d.last_sms.sender)}:</span> ${esc(d.last_sms.text)}</div>`
      : "";
    return `<div class="device"><h3>${esc(d.name)}</h3>
      <div class="badges">${rtu}${esp}${relay}</div>
      <div class="actions">${actions}</div>${sms}</div>`;
  }).join("") : `<div class="device disabled"><h3>${t("devices.noDevices")}</h3><div class="muted">${t("devices.addUnderConfig")}</div></div>`;
}

function renderSmsBanner(u) {
  const banner = $("#sms-banner");
  document.title = u && u.count ? `(${u.count}) AccessController` : "AccessController";
  if (!u || !u.count) { banner.classList.add("hidden"); return; }
  const n = u.newest;
  const from = n.member_name ? `${n.member_name} (${n.actor})` : n.actor;
  $("#sms-banner-text").innerHTML = `<b>${esc(t("status.newSms", { count: u.count }))}</b> <span class="muted">${esc(n.device || "")}, ${esc(fmtTime(n.ts))}, ${t("status.from")} ${esc(from)}:</span> ${esc(n.detail || "")}`;
  banner.classList.remove("hidden");
}

$("#sms-banner-go").addEventListener("click", async () => {
  for (const id of ["#e-from", "#e-to", "#e-device", "#e-result", "#e-q"]) $(id).value = "";
  $("#e-category").value = "sms";
  evPage = 1;
  showTab("events");
  try {
    await api("api/sms/seen", { method: "POST", body: {} });
    loadStatus();
  } catch (e) { toast(e.message, true); }
});

// Aftellen tussen twee statusupdates.
setInterval(() => {
  $$(".relay-on[data-remaining]").forEach((el) => {
    const r = parseInt(el.dataset.remaining, 10);
    if (Number.isNaN(r)) return;
    const n = Math.max(0, r - 1);
    el.dataset.remaining = n;
    el.textContent = t("status.relayOnRemaining", { time: fmtDur(n) });
  });
}, 1000);

$("#devices").addEventListener("click", async (ev) => {
  const b = ev.target.closest("button[data-act]");
  if (!b) return;
  const dev = b.dataset.dev, act = b.dataset.act;
  const d = lastStatus.devices.find((x) => String(x.id) === dev);
  const text = act === "off" ? t("control.disableNow", { name: d.name })
    : d.on_seconds >= 10 ? t("control.enableFor", { name: d.name, time: fmtSetting(d.on_seconds) }) : t("control.open", { name: d.name });
  if (!(await confirmDialog(t("control.manual"), text, act === "off" ? t("control.disable") : t("control.execute")))) return;
  try {
    await api(`api/devices/${dev}/${act}`, { method: "POST", body: {} });
    toast(t("control.sent"));
    setTimeout(loadStatus, 800);
  } catch (e) { toast(e.message, true); }
});

/* ---------------- Toestellen (lijst) ---------------- */
let devicesList = [];

function renderDeviceOptions() {
  const sel = $("#e-device"), cur = sel.value;
  sel.innerHTML = `<option value="">${esc(t("events.allDevices"))}</option>` +
    devicesList.map((d) => `<option value="${d.id}">${esc(d.name)}</option>`).join("");
  sel.value = cur;
}

async function loadDevices() {
  try {
    devicesList = await api("api/devices");
  } catch (e) { toast(e.message, true); }
  renderDeviceOptions();
  renderMemberHead();
  renderMembers();
}

/* ---------------- Leden ---------------- */
let membersData = [];
let sort = { key: "name", dir: 1 };

async function loadMembers() {
  try {
    membersData = await api("api/members");
    renderMembers();
  } catch (e) { toast(e.message, true); }
}

function renderMemberHead() {
  $("#m-head").innerHTML = `
    <th data-sort="member_no">${t("common.memberNo")}</th>
    <th data-sort="name">${t("common.name")}</th>
    <th data-sort="phone">${t("common.phone")}</th>
    ${devicesList.map((d) => `<th data-sort="acc:${d.id}" class="c">${esc(d.name)}</th>`).join("")}
    <th data-sort="note">${t("common.note")}</th>
    <th></th>`;
}

$("#m-head").addEventListener("click", (ev) => {
  const th = ev.target.closest("th[data-sort]");
  if (!th) return;
  sort = { key: th.dataset.sort, dir: sort.key === th.dataset.sort ? -sort.dir : 1 };
  renderMembers();
});

const sortValue = (m, key) => (key.startsWith("acc:") ? !!m.access[key.slice(4)] : m[key]);

function renderMembers() {
  const q = $("#m-search").value.trim().toLowerCase();
  const f = $("#m-filter").value;
  const qDigits = q.replace(/\D/g, "");
  let rows = membersData.filter((m) => {
    if (f === "nophone" && m.phone) return false;
    if (f === "noaccess" && Object.values(m.access).some(Boolean)) return false;
    if (!q) return true;
    const hay = `${m.member_no} ${m.name} ${m.note} ${m.phone || ""}`.toLowerCase();
    if (hay.includes(q)) return true;
    // telefoon: zoek ook op 0470... (zonder landcode)
    return qDigits.length >= 4 && (m.phone || "").replace(/\D/g, "").includes(qDigits.replace(/^0/, ""));
  });
  rows.sort((a, b) => {
    const x = sortValue(a, sort.key), y = sortValue(b, sort.key);
    if (typeof x === "boolean") return (x === y ? 0 : x ? -1 : 1) * sort.dir;
    return String(x ?? "").localeCompare(String(y ?? ""), currentLanguage, { numeric: true, sensitivity: "base" }) * sort.dir;
  });
  $$("#m-head th[data-sort]").forEach((th) => {
    th.classList.toggle("asc", th.dataset.sort === sort.key && sort.dir === 1);
    th.classList.toggle("desc", th.dataset.sort === sort.key && sort.dir === -1);
  });
  $("#m-count").textContent = t("members.count", { shown: rows.length, total: membersData.length });
  const sw = (m, d) => `<label class="switch" title="${esc(t("members.accessTitle", { device: d.name }))}"><input type="checkbox" data-dev="${d.id}" data-id="${m.id}" ${m.access[d.id] ? "checked" : ""}><span></span></label>`;
  const cols = 5 + devicesList.length;
  $("#m-table tbody").innerHTML = rows.length ? rows.map((m) => `
    <tr class="${Object.values(m.access).some(Boolean) ? "" : "inactive"}">
      <td class="mono">${esc(m.member_no)}</td>
      <td>${esc(m.name)}</td>
      <td class="phone">${esc(m.phone || "")}</td>
      ${devicesList.map((d) => `<td class="c">${sw(m, d)}</td>`).join("")}
      <td class="note">${esc(m.note)}</td>
      <td class="actions">
        <button class="small" data-edit="${m.id}">${t("common.edit")}</button>
        <button class="small danger" data-del="${m.id}">${t("common.delete")}</button>
      </td>
    </tr>`).join("") : `<tr><td colspan="${cols}" class="empty">${t("members.none")}</td></tr>`;
}

$("#m-search").addEventListener("input", renderMembers);
$("#m-filter").addEventListener("change", renderMembers);

$("#m-table tbody").addEventListener("change", async (ev) => {
  const cb = ev.target.closest("input[data-dev]");
  if (!cb) return;
  const id = +cb.dataset.id;
  cb.disabled = true;
  try {
    const updated = await api(`api/members/${id}`, { method: "PUT", body: { access: { [cb.dataset.dev]: cb.checked } } });
    membersData = membersData.map((m) => (m.id === id ? updated : m));
    renderMembers();
  } catch (e) {
    cb.checked = !cb.checked;
    toast(e.errors.length ? e.errors.join(" ") : e.message, true);
  } finally { cb.disabled = false; }
});

$("#m-table tbody").addEventListener("click", async (ev) => {
  const edit = ev.target.closest("[data-edit]");
  const del = ev.target.closest("[data-del]");
  if (edit) openMember(membersData.find((m) => m.id === +edit.dataset.edit));
  if (del) {
    const m = membersData.find((x) => x.id === +del.dataset.del);
    if (!(await confirmDialog(t("members.deleteTitle"), t("members.deleteText", { name: m.name, no: m.member_no }), t("common.delete")))) return;
    try {
      await api(`api/members/${m.id}`, { method: "DELETE" });
      toast(t("members.deleted"));
      loadMembers();
    } catch (e) { toast(e.message, true); }
  }
});

let editingId = null;
function openMember(m) {
  editingId = m ? m.id : null;
  const f = $("#member-form");
  $("#member-title").textContent = m ? t("members.titleEdit") : t("members.titleNew");
  f.member_no.value = m ? m.member_no : "";
  f.name.value = m ? m.name : "";
  f.phone.value = m ? m.phone || "" : "";
  f.note.value = m ? m.note : "";
  $("#member-access").innerHTML = devicesList.length
    ? devicesList.map((d) => `<label class="check"><input type="checkbox" data-access="${d.id}" ${!m || m.access[d.id] ? "checked" : ""}> ${t("common.access")} ${esc(d.name)}</label>`).join("")
    : `<span class="muted">${t("devices.noDevices")}</span>`;
  $(".errors", f).innerHTML = "";
  $("#dlg-member").showModal();
  f.member_no.focus();
}
$("#m-new").addEventListener("click", () => openMember(null));

$("#member-save").addEventListener("click", async (ev) => {
  ev.preventDefault();
  const f = $("#member-form");
  const access = {};
  $$("input[data-access]", f).forEach((cb) => { access[cb.dataset.access] = cb.checked; });
  const body = { member_no: f.member_no.value, name: f.name.value, phone: f.phone.value, note: f.note.value, access };
  try {
    if (editingId) await api(`api/members/${editingId}`, { method: "PUT", body });
    else await api("api/members", { method: "POST", body });
    $("#dlg-member").close();
    toast(t("members.saved"));
    loadMembers();
  } catch (e) {
    $(".errors", f).innerHTML = (e.errors.length ? e.errors : [e.message]).map((x) => `<li>${esc(x)}</li>`).join("");
  }
});

/* Import */
$("#m-import").addEventListener("click", () => {
  $("#import-form").reset();
  $("#import-result").innerHTML = "";
  $("#dlg-import").showModal();
});
$("#import-go").addEventListener("click", async (ev) => {
  ev.preventDefault();
  const input = $("#import-form").file;
  if (!input.files.length) { $("#import-result").innerHTML = `<p class="errors">${esc(t("import.chooseFile"))}</p>`; return; }
  const fd = new FormData();
  fd.append("file", input.files[0]);
  $("#import-go").disabled = true;
  try {
    const r = await api("api/members/import", { method: "POST", body: fd });
    $("#import-result").innerHTML = `<p class="ok">${esc(t("import.success", { created: r.nieuw, updated: r.gewijzigd, unchanged: r.ongewijzigd, missing: r.niet_in_bestand }))}</p>`;
    loadMembers();
  } catch (e) {
    $("#import-result").innerHTML = `<p class="errors">${esc(t("import.rejected"))}</p>
      <ul class="errors">${(e.errors.length ? e.errors : [e.message]).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
  } finally { $("#import-go").disabled = false; }
});

/* ---------------- Logboek ---------------- */
let evPage = 1;
const EV_PAGE_SIZE = 100;

function eventParams() {
  const p = new URLSearchParams();
  const from = $("#e-from").value, to = $("#e-to").value;
  if (from) p.set("from", new Date(from + "T00:00:00").toISOString().replace(/\.\d{3}Z$/, "Z"));
  if (to) p.set("to", new Date(to + "T23:59:59").toISOString().replace(/\.\d{3}Z$/, "Z"));
  for (const [id, key] of [["#e-category", "category"], ["#e-device", "device"], ["#e-result", "result"], ["#e-q", "q"]]) {
    const v = $(id).value.trim();
    if (v) p.set(key, v);
  }
  return p;
}

const RESULT_CLS = { toegelaten: "ok", ok: "ok", geweigerd: "bad", fout: "bad", info: "" };

async function loadEvents() {
  const p = eventParams();
  $("#e-export").href = "api/events/export.xlsx?" + p.toString();
  p.set("page", evPage);
  p.set("page_size", EV_PAGE_SIZE);
  try {
    const r = await api("api/events?" + p.toString());
    const pages = Math.max(1, Math.ceil(r.total / EV_PAGE_SIZE));
    $("#e-pageinfo").textContent = t("events.pageInfo", { page: evPage, pages, total: r.total });
    $("#e-prev").disabled = evPage <= 1;
    $("#e-next").disabled = evPage >= pages;
    $("#e-table tbody").innerHTML = r.items.length ? r.items.map((e) => {
      const who = e.member_name ? `${esc(e.member_name)} <span class="muted">(${esc(e.member_no)})</span>`
        : e.category === "oproep" ? `<span class="muted">${esc(t("events.unknown"))}</span>` : esc(e.actor || "");
      const adminBy = (e.category === "admin" || e.category === "manueel") && e.member_name ? `<div class="muted">${esc(t("events.by", { actor: e.actor }))}</div>` : "";
      const conf = e.cmd_id ? (e.confirmed_at ? `<span title="${esc(t("events.confirmedAt", { time: fmtTime(e.confirmed_at) }))}">✓</span>` : `<span class="muted" title="${esc(t("events.noConfirmation"))}">–</span>`) : "";
      return `<tr>
        <td class="mono">${esc(fmtTime(e.ts))}</td>
        <td>${esc(categoryLabel(e.category))}</td>
        <td>${esc(e.device || "")}</td>
        <td>${who}${adminBy}</td>
        <td class="phone">${esc(e.phone || "")}</td>
        <td>${e.result ? badge(resultLabel(e.result), RESULT_CLS[e.result] ?? "") : ""}</td>
        <td>${esc(e.reason || "")}</td>
        <td class="detail">${esc(e.detail || "")}</td>
        <td class="c">${conf}</td></tr>`;
    }).join("") : `<tr><td colspan="9" class="empty">${t("events.none")}</td></tr>`;
  } catch (e) { toast(e.message, true); }
}

let evTimer;
for (const id of ["#e-from", "#e-to", "#e-category", "#e-device", "#e-result"]) {
  $(id).addEventListener("change", () => { evPage = 1; loadEvents(); });
}
$("#e-q").addEventListener("input", () => { clearTimeout(evTimer); evTimer = setTimeout(() => { evPage = 1; loadEvents(); }, 300); });
$("#e-reset").addEventListener("click", () => {
  for (const id of ["#e-from", "#e-to", "#e-category", "#e-device", "#e-result", "#e-q"]) $(id).value = "";
  evPage = 1; loadEvents();
});
$("#e-prev").addEventListener("click", () => { evPage--; loadEvents(); });
$("#e-next").addEventListener("click", () => { evPage++; loadEvents(); });
setInterval(() => {
  if (!$("#tab-events").classList.contains("hidden") && $("#e-auto").checked && evPage === 1) loadEvents();
}, 5000);

$("#language-selector").addEventListener("change", (ev) => {
  applyLanguage(ev.target.value);
});
function showErrors(el, e) {
  el.innerHTML = (e.errors && e.errors.length ? e.errors : [e.message]).map((x) => `<li>${esc(x)}</li>`).join("");
}

async function loadConfig() {
  try {
    const [cfg, bk] = await Promise.all([api("api/config"), api("api/backup/status")]);
    const f = $("#cfg-form");
    for (const el of $$("[name]", f)) {
      const v = el.name.split(".").reduce((o, k) => (o ? o[k] : undefined), cfg);
      if (el.type === "checkbox") el.checked = !!v;
      else if (el.name !== "mqtt.password") el.value = v ?? "";
    }
    f["mqtt.password"].value = "";
    f["mqtt.password"].placeholder = cfg.mqtt.password_set ? t("config.passwordSet") : t("config.passwordNone");
    $("#sp-secret").textContent = bk.sharepoint_secret_set
      ? t("config.secretSet")
      : t("config.secretNone");
    renderBackupStatus(bk);
    $("#cfg-errors").innerHTML = "";
    $("#cfg-msg").textContent = "";
  } catch (e) { toast(e.message, true); }
  await loadDevices();
  renderDeviceTable();
}

function renderBackupStatus(bk) {
  const l = bk.last;
  if (!l) { $("#bk-status").innerHTML = `<span class="muted">${esc(t("config.backupNone"))}</span>`; return; }
  const part = (label, r) => !r ? "" : r.ok
    ? `<div>${esc(label)}: ok${r.path ? ` (${esc(r.path)})` : ""}${r.url ? ` (<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(t("config.open"))}</a>)` : ""}</div>`
    : `<div class="bad">${esc(label)}: ${esc(r.error)}</div>`;
  $("#bk-status").innerHTML = `<div><b>${esc(t("config.lastBackup"))}</b> ${esc(fmtTime(l.ts))}, ${esc(l.file)} (${Math.round(l.size / 1024)} kB)${l.automatic ? esc(t("config.automatic")) : ""}</div>`
    + part(t("config.folder"), l.local) + part(t("config.sharepoint"), l.sharepoint)
    + (bk.last_ok && bk.last_ok !== l.ts ? `<div class="muted">${esc(t("config.lastSuccess", { time: fmtTime(bk.last_ok) }))}</div>` : "");
}

$("#cfg-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const body = {};
  for (const el of $$("[name]", ev.target)) {
    const path = el.name.split(".");
    let o = body;
    path.slice(0, -1).forEach((k) => { o = o[k] ??= {}; });
    o[path.at(-1)] = el.type === "checkbox" ? el.checked : el.type === "number" ? Number(el.value) : el.value;
  }
  try {
    await api("api/config", { method: "PUT", body });
    $("#cfg-errors").innerHTML = "";
    $("#cfg-msg").textContent = t("members.saved");
    toast(t("config.saved"));
    loadConfig();
    setTimeout(loadStatus, 1500);
  } catch (e) { showErrors($("#cfg-errors"), e); }
});

/* Toestellen beheren */
function renderDeviceTable() {
  $("#dev-table tbody").innerHTML = devicesList.length ? devicesList.map((d) => `
    <tr>
      <td><b>${esc(d.name)}</b></td>
      <td>${d.enabled ? badge(t("common.active"), "ok") : badge(t("common.inactive"), "")}</td>
      <td class="mono">${esc(d.serial_port)}</td>
      <td>${d.relay_type === "shelly" ? "Shelly 1 Gen3" : "Tasmota"}</td>
      <td class="mono">${esc(d.tasmota_topic)}</td>
      <td>${esc(fmtSetting(d.on_seconds))}</td>
      <td>${d.dedupe_seconds ? esc(d.dedupe_seconds + " s") : t("common.offValue")}</td>
      <td class="actions">
        <button class="small" type="button" data-dev-edit="${d.id}">${t("common.edit")}</button>
        <button class="small danger" type="button" data-dev-del="${d.id}">${t("common.delete")}</button>
      </td>
    </tr>`).join("") : `<tr><td colspan="8" class="empty">${t("devices.noDevices")} ${t("devices.addOne")}</td></tr>`;
}

function deviceTopicPlaceholder(type) {
  return type === "shelly"
    ? t("devices.topicPlaceholderShelly")
    : t("devices.topicPlaceholderTasmota");
}

let editingDevice = null;
function openDevice(d) {
  editingDevice = d ? d.id : null;
  const f = $("#device-form");
  $("#device-title").textContent = d ? t("devices.titleEdit", { name: d.name }) : t("devices.titleNew");
  f.name.value = d ? d.name : "";
  f.enabled.checked = d ? d.enabled : true;
  f.serial_port.value = d ? d.serial_port : "";
  f.baudrate.value = d ? d.baudrate : 38400;
  f.relay_type.value = d ? d.relay_type : "tasmota";
  f.tasmota_topic.placeholder = deviceTopicPlaceholder(f.relay_type.value);
  f.tasmota_topic.value = d ? d.tasmota_topic : "";
  f.on_seconds.value = d ? d.on_seconds : 1;
  f.dedupe_seconds.value = d ? d.dedupe_seconds : 5;
  $$("input[name=grant_all]", f).forEach((r) => { r.checked = false; });
  $("#device-grant").classList.toggle("hidden", !!d);
  $(".errors", f).innerHTML = "";
  $("#dlg-device").showModal();
  f.name.focus();
}
$("#device-form select[name=relay_type]").addEventListener("change", (ev) => {
  $("#device-form input[name=tasmota_topic]").placeholder = deviceTopicPlaceholder(ev.target.value);
});
$("#dev-new").addEventListener("click", () => openDevice(null));

$("#device-save").addEventListener("click", async (ev) => {
  ev.preventDefault();
  const f = $("#device-form");
  const grant = $("input[name=grant_all]:checked", f);
  const body = {
    name: f.name.value, enabled: f.enabled.checked, serial_port: f.serial_port.value,
    baudrate: Number(f.baudrate.value), relay_type: f.relay_type.value, tasmota_topic: f.tasmota_topic.value,
    on_seconds: Number(f.on_seconds.value), dedupe_seconds: Number(f.dedupe_seconds.value),
  };
  try {
    if (editingDevice) {
      await api(`api/devices/${editingDevice}`, { method: "PUT", body });
    } else {
      if (!grant) { showErrors($(".errors", f), { errors: [t("devices.grantRequired")] }); return; }
      await api("api/devices", { method: "POST", body: { ...body, grant_all: grant.value === "1" } });
    }
    $("#dlg-device").close();
    toast(t("devices.saved"));
    await loadDevices();
    renderDeviceTable();
    loadMembers();
    setTimeout(loadStatus, 800);
  } catch (e) { showErrors($(".errors", f), e); }
});

$("#dev-table tbody").addEventListener("click", async (ev) => {
  const edit = ev.target.closest("[data-dev-edit]");
  const del = ev.target.closest("[data-dev-del]");
  if (edit) openDevice(devicesList.find((d) => d.id === +edit.dataset.devEdit));
  if (del) {
    const d = devicesList.find((x) => x.id === +del.dataset.devDel);
    if (!(await confirmDialog(t("devices.deleteTitle"), t("devices.deleteText", { name: d.name }), t("common.delete")))) return;
    try {
      await api(`api/devices/${d.id}`, { method: "DELETE" });
      toast(t("devices.deleted"));
      await loadDevices();
      renderDeviceTable();
      loadMembers();
      loadStatus();
    } catch (e) { toast(e.message, true); }
  }
});

/* Back-up */
$("#bk-run").addEventListener("click", async () => {
  $("#bk-run").disabled = true;
  try {
    const r = await api("api/backup/run", { method: "POST", body: {} });
    toast(r.ok ? t("config.backupCreated") : t("config.backupCreatedErrors"), !r.ok);
    renderBackupStatus(await api("api/backup/status"));
  } catch (e) { toast(e.message, true); } finally { $("#bk-run").disabled = false; }
});

$("#bk-restore").addEventListener("click", () => { $("#bk-file").value = ""; $("#bk-file").click(); });
$("#bk-file").addEventListener("change", async () => {
  const file = $("#bk-file").files[0];
  if (!file) return;
  const ok = await confirmDialog(t("config.restoreTitle"),
    t("config.restoreText", { file: file.name }),
    t("config.restoreButton"));
  if (!ok) return;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await api("api/backup/restore", { method: "POST", body: fd });
    toast(t("config.restored", { count: r.members }));
    setTimeout(() => location.reload(), 1500);
  } catch (e) { toast(e.errors && e.errors.length ? e.errors.join(" ") : e.message, true); }
});

/* ---------------- Start ---------------- */
(async function init() {
  try {
    const me = await api("api/me");
    $("#me").textContent = me.auth_disabled ? t("me.noCloudflare", { email: me.email }) : me.email;
  } catch (e) { toast(e.message, true); }
  applyLanguage(currentLanguage, false);
  loadStatus();
  setInterval(loadStatus, 3000);
  await loadDevices();
  loadMembers();
  let tab = "members";
  try { tab = localStorage.getItem("tab") || "members"; } catch { /* geen opslag */ }
  showTab(["members", "events", "config"].includes(tab) ? tab : "members");
})();
