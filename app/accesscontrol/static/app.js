"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const CATEGORY = { oproep: "Oproep", manueel: "Manueel", admin: "Admin", sms: "SMS", systeem: "Systeem" };

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: opts.body && !(opts.body instanceof FormData) ? { "Content-Type": "application/json" } : {},
    ...opts,
    body: opts.body && !(opts.body instanceof FormData) ? JSON.stringify(opts.body) : opts.body,
  });
  let data = null;
  try { data = await res.json(); } catch { /* geen json */ }
  if (!res.ok) {
    const err = new Error((data && data.detail) || `Fout ${res.status}`);
    err.errors = (data && data.errors) || [];
    err.status = res.status;
    throw err;
  }
  return data;
}

function toast(msg, error = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (error ? " error" : "");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.add("hidden"), error ? 6000 : 3000);
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
  return d.toLocaleString("nl-BE", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
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
    $("#mqtt-badge").textContent = "Server onbereikbaar";
  }
}

function badge(text, cls) { return `<span class="badge ${cls}">${esc(text)}</span>`; }

function renderStatus() {
  const s = lastStatus;
  const mb = $("#mqtt-badge");
  mb.className = "badge " + (s.mqtt.connected ? "ok" : "bad");
  mb.textContent = s.mqtt.connected ? "MQTT verbonden" : "MQTT niet verbonden";
  mb.title = s.mqtt.error || "";
  renderSmsBanner(s.sms_unread);

  $("#devices").innerHTML = s.devices.length ? s.devices.map((d) => {
    const id = d.id;
    if (!d.enabled) {
      return `<div class="device disabled"><h3>${esc(d.name)} ${badge("niet actief", "")}</h3>
        <div class="muted">Activeer in Configuratie.</div></div>`;
    }
    // Eén RTU-status: kabel (seriële verbinding) en GSM-netwerk samen.
    const noNetwork = ["niet geregistreerd", "geen SIM"].includes(d.gsm);
    const rtu = !d.serial_connected
      ? `<span class="badge bad" title="${esc(d.serial_error)}">RTU: kabel niet verbonden</span>`
      : noNetwork
        ? `<span class="badge bad" title="GSM: ${esc(d.gsm)}">RTU: geen GSM-netwerk</span>`
        : `<span class="badge ok" title="GSM: ${esc(d.gsm)}">RTU ok</span>`;
    const esp = badge("Relaismodule " + d.esp, d.esp === "online" ? "ok" : d.esp === "offline" ? "bad" : "warn");
    let relay = badge("Relais ?", "");
    if (d.relay === "on") relay = `<span class="badge ok relay-on" data-remaining="${d.relay_remaining_s ?? ""}">Relais aan${d.relay_remaining_s != null ? ", nog " + fmtDur(d.relay_remaining_s) : ""}</span>`;
    else if (d.relay === "off") relay = badge("Relais uit", "");
    const long = d.on_seconds >= 10;
    const actions = long
      ? `<button class="primary" data-act="on" data-dev="${id}">Aan (${fmtSetting(d.on_seconds)})</button>
         <button data-act="off" data-dev="${id}">Uit</button>`
      : `<button class="primary" data-act="on" data-dev="${id}">Open (${fmtSetting(d.on_seconds)} puls)</button>`;
    const sms = d.last_sms
      ? `<div class="last-sms" title="${esc(d.last_sms.text)}"><span class="muted">Laatste SMS ${esc(fmtTime(d.last_sms.ts))}, van ${esc(d.last_sms.sender)}:</span> ${esc(d.last_sms.text)}</div>`
      : "";
    return `<div class="device"><h3>${esc(d.name)}</h3>
      <div class="badges">${rtu}${esp}${relay}</div>
      <div class="actions">${actions}</div>${sms}</div>`;
  }).join("") : `<div class="device disabled"><h3>Nog geen toestellen</h3><div class="muted">Voeg een toestel toe onder Configuratie.</div></div>`;
}

function renderSmsBanner(u) {
  const banner = $("#sms-banner");
  document.title = u && u.count ? `(${u.count}) AccessController` : "AccessController";
  if (!u || !u.count) { banner.classList.add("hidden"); return; }
  const n = u.newest;
  const from = n.member_name ? `${n.member_name} (${n.actor})` : n.actor;
  $("#sms-banner-text").innerHTML = `<b>${u.count} nieuwe SMS</b> <span class="muted">${esc(n.device || "")}, ${esc(fmtTime(n.ts))}, van ${esc(from)}:</span> ${esc(n.detail || "")}`;
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
    el.textContent = `Relais aan, nog ${fmtDur(n)}`;
  });
}, 1000);

$("#devices").addEventListener("click", async (ev) => {
  const b = ev.target.closest("button[data-act]");
  if (!b) return;
  const dev = b.dataset.dev, act = b.dataset.act;
  const d = lastStatus.devices.find((x) => String(x.id) === dev);
  const text = act === "off" ? `${d.name} nu uitschakelen?`
    : d.on_seconds >= 10 ? `${d.name} inschakelen voor ${fmtSetting(d.on_seconds)}?` : `${d.name} openen?`;
  if (!(await confirmDialog("Manuele bediening", text, act === "off" ? "Uitschakelen" : "Uitvoeren"))) return;
  try {
    await api(`api/devices/${dev}/${act}`, { method: "POST", body: {} });
    toast("Commando verzonden.");
    setTimeout(loadStatus, 800);
  } catch (e) { toast(e.message, true); }
});

/* ---------------- Toestellen (lijst) ---------------- */
let devicesList = [];
async function loadDevices() {
  try {
    devicesList = await api("api/devices");
  } catch (e) { toast(e.message, true); }
  const sel = $("#e-device"), cur = sel.value;
  sel.innerHTML = `<option value="">Alle toestellen</option>` +
    devicesList.map((d) => `<option value="${d.id}">${esc(d.name)}</option>`).join("");
  sel.value = cur;
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
    <th data-sort="member_no">Lidnr</th>
    <th data-sort="name">Naam</th>
    <th data-sort="phone">Telefoon</th>
    ${devicesList.map((d) => `<th data-sort="acc:${d.id}" class="c">${esc(d.name)}</th>`).join("")}
    <th data-sort="note">Opmerking</th>
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
    return String(x ?? "").localeCompare(String(y ?? ""), "nl", { numeric: true, sensitivity: "base" }) * sort.dir;
  });
  $$("#m-head th[data-sort]").forEach((th) => {
    th.classList.toggle("asc", th.dataset.sort === sort.key && sort.dir === 1);
    th.classList.toggle("desc", th.dataset.sort === sort.key && sort.dir === -1);
  });
  $("#m-count").textContent = `${rows.length} van ${membersData.length}`;
  const sw = (m, d) => `<label class="switch" title="Toegang ${esc(d.name)}"><input type="checkbox" data-dev="${d.id}" data-id="${m.id}" ${m.access[d.id] ? "checked" : ""}><span></span></label>`;
  const cols = 5 + devicesList.length;
  $("#m-table tbody").innerHTML = rows.length ? rows.map((m) => `
    <tr class="${Object.values(m.access).some(Boolean) ? "" : "inactive"}">
      <td class="mono">${esc(m.member_no)}</td>
      <td>${esc(m.name)}</td>
      <td class="phone">${esc(m.phone || "")}</td>
      ${devicesList.map((d) => `<td class="c">${sw(m, d)}</td>`).join("")}
      <td class="note">${esc(m.note)}</td>
      <td class="actions">
        <button class="small" data-edit="${m.id}">Bewerken</button>
        <button class="small danger" data-del="${m.id}">Verwijderen</button>
      </td>
    </tr>`).join("") : `<tr><td colspan="${cols}" class="empty">Geen leden gevonden.</td></tr>`;
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
    if (!(await confirmDialog("Lid verwijderen", `${m.name} (lidnr ${m.member_no}) definitief verwijderen? Het logboek blijft bewaard.`, "Verwijderen"))) return;
    try {
      await api(`api/members/${m.id}`, { method: "DELETE" });
      toast("Lid verwijderd.");
      loadMembers();
    } catch (e) { toast(e.message, true); }
  }
});

let editingId = null;
function openMember(m) {
  editingId = m ? m.id : null;
  const f = $("#member-form");
  $("#member-title").textContent = m ? `Lid ${m.member_no} bewerken` : "Nieuw lid";
  f.member_no.value = m ? m.member_no : "";
  f.name.value = m ? m.name : "";
  f.phone.value = m ? m.phone || "" : "";
  f.note.value = m ? m.note : "";
  $("#member-access").innerHTML = devicesList.length
    ? devicesList.map((d) => `<label class="check"><input type="checkbox" data-access="${d.id}" ${!m || m.access[d.id] ? "checked" : ""}> Toegang ${esc(d.name)}</label>`).join("")
    : `<span class="muted">Nog geen toestellen.</span>`;
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
    toast("Opgeslagen.");
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
  if (!input.files.length) { $("#import-result").innerHTML = `<p class="errors">Kies een bestand.</p>`; return; }
  const fd = new FormData();
  fd.append("file", input.files[0]);
  $("#import-go").disabled = true;
  try {
    const r = await api("api/members/import", { method: "POST", body: fd });
    $("#import-result").innerHTML = `<p class="ok">Import gelukt: ${r.nieuw} nieuw, ${r.gewijzigd} gewijzigd, ${r.ongewijzigd} ongewijzigd. ${r.niet_in_bestand} bestaande leden stonden niet in het bestand en zijn behouden.</p>`;
    loadMembers();
  } catch (e) {
    $("#import-result").innerHTML = `<p class="errors">Bestand geweigerd, er is niets gewijzigd.</p>
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
    $("#e-pageinfo").textContent = `Pagina ${evPage} van ${pages} (${r.total} regels)`;
    $("#e-prev").disabled = evPage <= 1;
    $("#e-next").disabled = evPage >= pages;
    $("#e-table tbody").innerHTML = r.items.length ? r.items.map((e) => {
      const who = e.member_name ? `${esc(e.member_name)} <span class="muted">(${esc(e.member_no)})</span>`
        : e.category === "oproep" ? `<span class="muted">onbekend</span>` : esc(e.actor || "");
      const adminBy = (e.category === "admin" || e.category === "manueel") && e.member_name ? `<div class="muted">door ${esc(e.actor)}</div>` : "";
      const conf = e.cmd_id ? (e.confirmed_at ? `<span title="Bevestigd ${esc(fmtTime(e.confirmed_at))}">✓</span>` : `<span class="muted" title="Geen bevestiging van de relaismodule">–</span>`) : "";
      return `<tr>
        <td class="mono">${esc(fmtTime(e.ts))}</td>
        <td>${esc(CATEGORY[e.category] || e.category)}</td>
        <td>${esc(e.device || "")}</td>
        <td>${who}${adminBy}</td>
        <td class="phone">${esc(e.phone || "")}</td>
        <td>${e.result ? badge(e.result, RESULT_CLS[e.result] ?? "") : ""}</td>
        <td>${esc(e.reason || "")}</td>
        <td class="detail">${esc(e.detail || "")}</td>
        <td class="c">${conf}</td></tr>`;
    }).join("") : `<tr><td colspan="9" class="empty">Geen regels voor deze filters.</td></tr>`;
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

/* ---------------- Configuratie ---------------- */
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
    f["mqtt.password"].placeholder = cfg.mqtt.password_set ? "ingesteld, leeg = ongewijzigd" : "geen wachtwoord";
    $("#sp-secret").textContent = bk.sharepoint_secret_set
      ? "Client secret: ingesteld via SHAREPOINT_CLIENT_SECRET."
      : "Client secret: niet ingesteld. Zet SHAREPOINT_CLIENT_SECRET in de stack-variabelen.";
    renderBackupStatus(bk);
    $("#cfg-errors").innerHTML = "";
    $("#cfg-msg").textContent = "";
  } catch (e) { toast(e.message, true); }
  await loadDevices();
  renderDeviceTable();
}

function renderBackupStatus(bk) {
  const l = bk.last;
  if (!l) { $("#bk-status").innerHTML = `<span class="muted">Nog geen back-up gemaakt.</span>`; return; }
  const part = (label, r) => !r ? "" : r.ok
    ? `<div>${label}: ok${r.path ? ` (${esc(r.path)})` : ""}${r.url ? ` (<a href="${esc(r.url)}" target="_blank" rel="noopener">openen</a>)` : ""}</div>`
    : `<div class="bad">${label}: ${esc(r.error)}</div>`;
  $("#bk-status").innerHTML = `<div><b>Laatste back-up:</b> ${esc(fmtTime(l.ts))}, ${esc(l.file)} (${Math.round(l.size / 1024)} kB)${l.automatic ? ", automatisch" : ""}</div>`
    + part("Map", l.local) + part("SharePoint", l.sharepoint)
    + (bk.last_ok && bk.last_ok !== l.ts ? `<div class="muted">Laatste geslaagde: ${esc(fmtTime(bk.last_ok))}</div>` : "");
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
    $("#cfg-msg").textContent = "Opgeslagen.";
    toast("Configuratie opgeslagen.");
    loadConfig();
    setTimeout(loadStatus, 1500);
  } catch (e) { showErrors($("#cfg-errors"), e); }
});

/* Toestellen beheren */
function renderDeviceTable() {
  $("#dev-table tbody").innerHTML = devicesList.length ? devicesList.map((d) => `
    <tr>
      <td><b>${esc(d.name)}</b></td>
      <td>${d.enabled ? badge("actief", "ok") : badge("niet actief", "")}</td>
      <td class="mono">${esc(d.serial_port)}</td>
      <td class="mono">${esc(d.tasmota_topic)}</td>
      <td>${esc(fmtSetting(d.on_seconds))}</td>
      <td>${d.dedupe_seconds ? esc(d.dedupe_seconds + " s") : "uit"}</td>
      <td class="actions">
        <button class="small" type="button" data-dev-edit="${d.id}">Bewerken</button>
        <button class="small danger" type="button" data-dev-del="${d.id}">Verwijderen</button>
      </td>
    </tr>`).join("") : `<tr><td colspan="7" class="empty">Nog geen toestellen. Voeg er een toe.</td></tr>`;
}

let editingDevice = null;
function openDevice(d) {
  editingDevice = d ? d.id : null;
  const f = $("#device-form");
  $("#device-title").textContent = d ? `Toestel ${d.name} bewerken` : "Nieuw toestel";
  f.name.value = d ? d.name : "";
  f.enabled.checked = d ? d.enabled : true;
  f.serial_port.value = d ? d.serial_port : "";
  f.baudrate.value = d ? d.baudrate : 38400;
  f.tasmota_topic.value = d ? d.tasmota_topic : "";
  f.on_seconds.value = d ? d.on_seconds : 1;
  f.dedupe_seconds.value = d ? d.dedupe_seconds : 5;
  $$("input[name=grant_all]", f).forEach((r) => { r.checked = false; });
  $("#device-grant").classList.toggle("hidden", !!d);
  $(".errors", f).innerHTML = "";
  $("#dlg-device").showModal();
  f.name.focus();
}
$("#dev-new").addEventListener("click", () => openDevice(null));

$("#device-save").addEventListener("click", async (ev) => {
  ev.preventDefault();
  const f = $("#device-form");
  const grant = $("input[name=grant_all]:checked", f);
  const body = {
    name: f.name.value, enabled: f.enabled.checked, serial_port: f.serial_port.value,
    baudrate: Number(f.baudrate.value), tasmota_topic: f.tasmota_topic.value,
    on_seconds: Number(f.on_seconds.value), dedupe_seconds: Number(f.dedupe_seconds.value),
  };
  try {
    if (editingDevice) {
      await api(`api/devices/${editingDevice}`, { method: "PUT", body });
    } else {
      if (!grant) { showErrors($(".errors", f), { errors: ["Kies of alle bestaande leden toegang krijgen."] }); return; }
      await api("api/devices", { method: "POST", body: { ...body, grant_all: grant.value === "1" } });
    }
    $("#dlg-device").close();
    toast("Toestel opgeslagen.");
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
    if (!(await confirmDialog("Toestel verwijderen", `${d.name} verwijderen? De toegang van alle leden tot dit toestel verdwijnt. Het logboek blijft bewaard.`, "Verwijderen"))) return;
    try {
      await api(`api/devices/${d.id}`, { method: "DELETE" });
      toast("Toestel verwijderd.");
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
    toast(r.ok ? "Back-up gemaakt." : "Back-up gemaakt met fouten.", !r.ok);
    renderBackupStatus(await api("api/backup/status"));
  } catch (e) { toast(e.message, true); } finally { $("#bk-run").disabled = false; }
});

$("#bk-restore").addEventListener("click", () => { $("#bk-file").value = ""; $("#bk-file").click(); });
$("#bk-file").addEventListener("change", async () => {
  const file = $("#bk-file").files[0];
  if (!file) return;
  const ok = await confirmDialog("Back-up terugzetten",
    `${file.name} terugzetten? Alle leden, toestellen, instellingen en het logboek worden vervangen door de inhoud van deze back-up. Er wordt eerst een veiligheidskopie van de huidige toestand gemaakt.`,
    "Terugzetten");
  if (!ok) return;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await api("api/backup/restore", { method: "POST", body: fd });
    toast(`Back-up teruggezet (${r.members} leden). De pagina wordt herladen.`);
    setTimeout(() => location.reload(), 1500);
  } catch (e) { toast(e.errors && e.errors.length ? e.errors.join(" ") : e.message, true); }
});

/* ---------------- Start ---------------- */
(async function init() {
  try {
    const me = await api("api/me");
    $("#me").textContent = me.auth_disabled ? `${me.email} (zonder Cloudflare)` : me.email;
  } catch (e) { toast(e.message, true); }
  loadStatus();
  setInterval(loadStatus, 3000);
  await loadDevices();
  loadMembers();
  let tab = "members";
  try { tab = localStorage.getItem("tab") || "members"; } catch { /* geen opslag */ }
  showTab(["members", "events", "config"].includes(tab) ? tab : "members");
})();
