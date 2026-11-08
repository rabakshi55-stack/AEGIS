"use strict";

const $ = (id) => document.getElementById(id);
const state = {
  ready: false, currentView: "intake", status: null, summary: null,
  orderPage: 1, orderPages: 1, currentOrder: "", orderRows: [],
  scenarios: [], selectedScenario: null, policies: [], readiness: [], busy: false,
  intake: null, intakeBusy: false, historicalOutcomes: null, outcomeBusy: false,
  chatHistory: [], lastCopilotContext: null, copilotSessionId: null,
  customCharts: [], customEditing: -1, customFieldsKey: null, customDatasetKey: null,
};
const titles = {intake:"Data", visualizations:"Visualizations", copilot:"Decision Copilot"};
let toastTimeout;
const fmt = (n) => Number(n).toLocaleString("en-US");
const fixed = (n, places = 2) => Number(n).toLocaleString("en-US", {minimumFractionDigits:places,maximumFractionDigits:places});
const html = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
const humanDate = (iso) => {
  const value = String(iso ?? "");
  const stamp = value.slice(0, 10);
  const parts = stamp.split("-");
  if (parts.length !== 3) return value;
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${parts[2]} ${months[Number(parts[1]) - 1] || parts[1]} ${parts[0]}`;
};

async function request(path, options) {
  const response = await fetch(path, options);
  let data;
  try { data = await response.json(); } catch { throw new Error(`Invalid local response (${response.status}).`); }
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
  return data;
}

function toast(message) {
  const node = $("toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => node.classList.remove("show"), 3200);
}

function navigate(view) {
  if (!titles[view]) return;
  state.currentView = view;
  document.querySelectorAll(".view").forEach((el) => el.classList.toggle("active", el.id === `view-${view}`));
  document.querySelectorAll(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.view === view));
  $("current-view-label").textContent = titles[view];
  $("sidebar").classList.remove("open");
  if (location.hash !== `#${view}`) history.replaceState(null, "", `#${view}`);
  window.scrollTo({top:0,behavior:"smooth"});
  if (view === "visualizations") renderVisualizations(state.intake);
  if (view === "copilot" && !$("copilot-order").value && state.currentOrder) $("copilot-order").value = state.currentOrder;
}

function setupNavigation() {
  document.querySelectorAll("[data-view],[data-goto]").forEach((button) => button.addEventListener("click", () => navigate(button.dataset.view || button.dataset.goto)));
  $("mobile-menu").addEventListener("click", () => $("sidebar").classList.toggle("open"));
  $("global-search").addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    $("order-search").value = $("global-search").value.trim();
    state.orderPage = 1;
    navigate("orders");
    if (state.ready) loadOrders();
  });
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault(); $("global-search").focus();
    }
    if (event.key === "Escape") closeDrawer();
  });
  const initial = location.hash.slice(1);
  navigate(titles[initial] ? initial : "intake");
}

function renderStatus(status) {
  state.status = status;
  state.ready = Boolean(status.ready);
  if (!state.ready) {
    $("setup-banner").classList.remove("hidden");
    $("setup-detail").textContent = status.message || "The research bundle has not been exported yet.";
    $("metric-scored").textContent = "—";
    $("metric-source").textContent = "—";
    $("metric-scenarios").textContent = "—";
  } else {
    $("setup-banner").classList.add("hidden");
    const count = status.summary;
    $("metric-scored").textContent = fmt(count.scored_orders);
    $("metric-source").textContent = fmt(count.source_orders);
    $("metric-scenarios").textContent = fmt(count.scenarios);
    state.summary = count;
    renderHistogram(count);
    renderPhases(count);
  }
  renderGovernance();
}

function renderHistogram(data) {
  const bars = data.score_histogram;
  const max = Math.max(...bars, 1);
  const w = 710, h = 204, left = 39, right = 16, top = 12, bottom = 30;
  const chartW = w - left - right, chartH = h - top - bottom;
  const band = chartW / bars.length, barW = band * .57;
  let shapes = "";
  for (let i = 0; i <= 3; i++) {
    const y = top + i * chartH / 3;
    const count = Math.round(max * (1 - i / 3));
    shapes += `<line x1="${left}" x2="${w-right}" y1="${y}" y2="${y}" stroke="#264365" opacity=".54" stroke-dasharray="3 6"/><text x="${left-10}" y="${y+3}" fill="#607fa2" text-anchor="end" font-size="10">${fmt(count)}</text>`;
  }
  bars.forEach((count, i) => {
    const x = left + i * band + (band - barW) / 2;
    const height = Math.max(1, (count / max) * chartH);
    const y = top + chartH - height;
    const min = Number(data.score_min) + i * (Number(data.score_max) - Number(data.score_min)) / 12;
    const upper = Number(data.score_min) + (i + 1) * (Number(data.score_max) - Number(data.score_min)) / 12;
    shapes += `<rect x="${x}" y="${y}" width="${barW}" height="${height}" rx="4" fill="url(#bars-grad)" opacity="${.65 + i / 36}"><title>${fmt(count)} historical orders · scores ${min.toFixed(4)} to ${upper.toFixed(4)}</title></rect>`;
  });
  shapes += `<text x="${left}" y="${h-7}" fill="#7994b7" font-size="10">${Number(data.score_min).toFixed(4)}</text><text x="${w-right}" y="${h-7}" fill="#7994b7" font-size="10" text-anchor="end">${Number(data.score_max).toFixed(4)}</text><text x="${w/2}" y="${h-7}" fill="#7593b5" font-size="10" text-anchor="middle">Uncalibrated research score</text>`;
  $("histogram").innerHTML = `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Distribution of historical AEGIS research scores"><defs><linearGradient id="bars-grad" x1="0" y1="1" x2="0" y2="0"><stop stop-color="#2d77d8"/><stop offset="1" stop-color="#32d5d5"/></linearGradient></defs>${shapes}</svg>`;
}

function renderPhases(data) {
  const total = Number(data.scored_orders);
  const phases = ["TRAIN", "VALIDATION", "TEST"];
  $("phase-distribution").innerHTML = phases.map((key) => {
    const count = Number(data.phase_counts[key] || 0);
    const pct = total ? count / total * 100 : 0;
    return `<div class="phase-row"><span class="phase-name">${key === "VALIDATION" ? "VALIDATION" : key}</span><div class="phase-track"><span style="width:${pct}%"></span></div><strong>${fmt(count)}</strong></div>`;
  }).join("");
}

async function loadOrders() {
  if (!state.ready) return;
  const params = new URLSearchParams({
    q: $("order-search").value.trim(), phase: $("order-phase").value,
    sort: $("order-sort").value, page: String(state.orderPage),
  });
  try {
    const result = await request(`/api/orders?${params}`);
    state.orderRows = result.items;
    state.orderPages = result.pages;
    if (!state.currentOrder && result.items.length) {
      state.currentOrder = result.items[0].reference;
      $("copilot-order").value = state.currentOrder;
    }
    $("orders-tbody").innerHTML = result.items.length ? result.items.map((row) => `<tr><td><span class="order-ref">Order ${html(row.reference)}</span><div style="font-size:10px;color:#617f9e;margin-top:4px">${html(humanDate(row.purchase_time))}</div></td><td><span class="split-badge ${row.phase === "TEST" ? "test" : ""}">${html(row.phase)}</span></td><td>${html(row.state)}</td><td>${fixed(row.promise_days,1)} days</td><td class="score-cell">${fixed(row.score,4)}</td><td><button class="table-button" data-inspect="${html(row.reference)}">Inspect evidence →</button></td></tr>`).join("") : `<tr><td colspan="6" class="empty-row">No scored historical orders match this search.</td></tr>`;
    $("orders-count").textContent = `${fmt(result.total)} matching research orders`;
    $("orders-page").textContent = `${result.page} of ${result.pages}`;
    $("orders-prev").disabled = result.page <= 1;
    $("orders-next").disabled = result.page >= result.pages;
  } catch (error) { toast(error.message); }
}

function setupOrders() {
  let searchTimer;
  $("order-search").addEventListener("input", () => {clearTimeout(searchTimer);searchTimer=setTimeout(() => {state.orderPage=1;loadOrders();},260);});
  ["order-phase","order-sort"].forEach((id) => $(id).addEventListener("change", () => {state.orderPage=1;loadOrders();}));
  $("orders-prev").addEventListener("click", () => {if(state.orderPage>1){state.orderPage--;loadOrders();}});
  $("orders-next").addEventListener("click", () => {if(state.orderPage<state.orderPages){state.orderPage++;loadOrders();}});
  $("orders-tbody").addEventListener("click", (event) => {
    const target = event.target.closest("[data-inspect]");
    if (target) inspectOrder(target.dataset.inspect);
  });
}

async function inspectOrder(reference) {
  try {
    const row = await request(`/api/orders/${encodeURIComponent(reference)}`);
    state.currentOrder = row.reference;
    $("copilot-order").value = row.reference;
    $("drawer-reference").textContent = `Order ${row.reference}`;
    $("drawer-content").innerHTML = `<div class="drawer-score"><span>FROZEN HISTORICAL RESEARCH SCORE</span><strong>${fixed(row.score,4)}</strong><p>Relative ranking score only. Not a verified probability or a real-time risk alert.</p></div><div class="drawer-section-title">RECORDED INPUTS</div><div class="evidence-row"><span>Evaluation split</span><strong>${html(row.phase)}</strong></div><div class="evidence-row"><span>Purchase timestamp</span><strong>${html(String(row.purchase_time).replace("T"," "))}</strong></div><div class="evidence-row"><span>Destination state</span><strong>${html(row.state)}</strong></div><div class="evidence-row"><span>Promise window</span><strong>${fixed(row.promise_days,1)} days</strong></div><div class="evidence-row"><span>Promise band</span><strong>${html(row.promise_band)}</strong></div><div class="drawer-section-title">SOURCE TRACEABILITY</div><div class="source-id-box"><code>${html(row.original_order_id)}</code><button id="copy-raw-id"><svg><use href="#i-copy"/></svg> Copy original order ID</button></div><div class="drawer-section-title">RESEARCH SAFETY</div><div class="evidence-row"><span>Data source</span><strong>Historical Olist</strong></div><div class="evidence-row"><span>Decision-time certification</span><strong>Not certified</strong></div><div class="evidence-row"><span>Supplier causality</span><strong>Not established</strong></div><div class="evidence-row"><span>Permitted action</span><strong>NONE</strong></div><div class="drawer-warning">Historical research evidence only. This score cannot support a supplier switch or an automatic procurement decision.</div>`;
    $("copy-raw-id").addEventListener("click", async () => {
      try {await navigator.clipboard.writeText(row.original_order_id);toast("Original dataset ID copied.");} catch {toast("Copy unavailable. Select the full ID above.");}
    });
    $("drawer-backdrop").classList.remove("hidden");
    $("order-drawer").classList.add("open");
    $("order-drawer").setAttribute("aria-hidden","false");
  } catch (error) { toast(error.message); }
}
function closeDrawer() {
  $("drawer-backdrop").classList.add("hidden");
  $("order-drawer").classList.remove("open");
  $("order-drawer").setAttribute("aria-hidden","true");
}

function renderScenarios() {
  const rows = state.scenarios;
  $("scenarios-tbody").innerHTML = rows.map((row) => `<tr class="${state.selectedScenario === Number(row.Scenario) ? "scenario-row-selected" : ""}"><td><span class="split-badge">#${html(row.Rank)}</span></td><td><span class="order-ref">Scenario ${html(row.Scenario)}</span></td><td>${fixed(row.Actual_Reserve_Pct)}%</td><td>${fixed(row.Minimum_Allowance_Pct)}%</td><td>$${fmt(Number(row.Landed_Cost).toFixed(2))}</td><td>${fixed(row.Supplier_HHI,4)}</td><td><button class="table-button" data-scenario="${html(row.Scenario)}">Inspect →</button></td></tr>`).join("");
  const select = $("copilot-scenario");
  select.innerHTML = rows.map((row) => `<option value="${html(row.Scenario)}">Rank ${html(row.Rank)} · Scenario ${html(row.Scenario)}</option>`).join("");
  if (rows.length) selectScenario(state.selectedScenario || Number(rows[0].Scenario));
}

function scatterPlot() {
  const rows = state.scenarios;
  if (!rows.length) return;
  const W=620,H=293,left=70,right=25,top=22,bottom=45;
  const reserve=rows.map(r=>Number(r.Actual_Reserve_Pct)), cost=rows.map(r=>Number(r.Landed_Cost));
  const minX=Math.min(...reserve),maxX=Math.max(...reserve),minY=Math.min(...cost),maxY=Math.max(...cost);
  const spanX=Math.max(.001,maxX-minX),spanY=Math.max(.001,maxY-minY);
  const x=(v)=>left+(Number(v)-minX)/spanX*(W-left-right);
  const y=(v)=>top+(maxY-Number(v))/spanY*(H-top-bottom);
  let parts="";
  for(let i=0;i<5;i++){
    const t=i/4,py=top+t*(H-top-bottom),px=left+t*(W-left-right);
    parts+=`<line x1="${left}" y1="${py}" x2="${W-right}" y2="${py}" stroke="#2b4463" stroke-dasharray="4 6" opacity=".7"/>`;
    parts+=`<line x1="${px}" y1="${top}" x2="${px}" y2="${H-bottom}" stroke="#233a55" opacity=".6"/>`;
    parts+=`<text x="${left-9}" y="${py+4}" text-anchor="end" fill="#718baa" font-size="10">${Math.round(maxY-t*spanY).toLocaleString("en-US")}</text>`;
    parts+=`<text x="${px}" y="${H-bottom+18}" text-anchor="middle" fill="#718baa" font-size="10">${(minX+t*spanX).toFixed(1)}%</text>`;
  }
  rows.forEach(row=>{
    const selected=state.selectedScenario===Number(row.Scenario);
    parts+=`<circle data-scenario="${html(row.Scenario)}" cx="${x(row.Actual_Reserve_Pct)}" cy="${y(row.Landed_Cost)}" r="${selected?8:6}" fill="${selected?"#34e2da":"#4c8fff"}" stroke="${selected?"#c9ffff":"#add2ff"}" stroke-width="${selected?2:1.2}"><title>Scenario ${html(row.Scenario)} · Reserve ${fixed(row.Actual_Reserve_Pct)}% · Cost $${fixed(row.Landed_Cost)}</title></circle>`;
  });
  parts+=`<text x="${W/2}" y="${H-4}" text-anchor="middle" fill="#8aa5c5" font-size="11">Minimum remaining capacity (%)</text><text transform="translate(14 ${H/2}) rotate(-90)" text-anchor="middle" fill="#8aa5c5" font-size="11">Synthetic landed cost ($)</text>`;
  $("scenario-scatter").innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Synthetic optimization scatter plot">${parts}</svg>`;
}

function selectScenario(id) {
  const row=state.scenarios.find(r=>Number(r.Scenario)===Number(id));
  if(!row)return;
  state.selectedScenario=Number(row.Scenario);
  $("scenario-name").textContent=`Scenario ${row.Scenario}`;
  $("scenario-rank").textContent=`RANK ${row.Rank} OF ${state.scenarios.length} · FROZEN OPTIMIZATION`;
  $("scenario-reserve").textContent=`${fixed(row.Actual_Reserve_Pct)}%`;
  $("scenario-allowance").textContent=`${fixed(row.Minimum_Allowance_Pct)}%`;
  $("scenario-cost").textContent=`$${fixed(row.Landed_Cost)}`;
  $("scenario-hhi").textContent=fixed(row.Supplier_HHI,4);
  $("copilot-scenario").value=String(row.Scenario);
  $("scenarios-tbody").querySelectorAll("tr").forEach(tr=>tr.classList.toggle("scenario-row-selected",tr.querySelector("[data-scenario]")?.dataset.scenario===String(id)));
  scatterPlot();
}
function setupScenarios(){
  $("scenarios-tbody").addEventListener("click",e=>{const button=e.target.closest("[data-scenario]");if(button)selectScenario(button.dataset.scenario);});
  $("scenario-scatter").addEventListener("click",e=>{const circle=e.target.closest("circle[data-scenario]");if(circle)selectScenario(circle.dataset.scenario);});
}

function renderPolicies() {
  if(!state.policies.length) return;
  const fields=Object.keys(state.policies[0]);
  $("policies-thead").innerHTML=`<tr>${fields.map(key=>`<th>${html(key.replaceAll("_"," "))}</th>`).join("")}</tr>`;
  $("policies-tbody").innerHTML=state.policies.map(row=>`<tr>${fields.map(key=>`<td>${typeof row[key]==="number"?html(Number(row[key].toFixed(4)).toLocaleString("en-US")):html(row[key]??"—")}</td>`).join("")}</tr>`).join("");
}
function renderReadiness() {
  $("readiness-tbody").innerHTML=state.readiness.map(row=>`<tr><td><span class="order-ref">${html(row.Table)}</span></td><td>${html(row.Module)}</td><td><span class="status-pill ${row.Status==="SCHEMA_PASS"?"passed":""}">${html(row.Status)}</span></td></tr>`).join("");
}

async function loadConnections() {
  try {
    const result = await request("/api/connections");
    const sqlite = result.active_sqlite;
    const localInspection = sqlite.connected;
    const tables = result.available_sqlite_tables || [];
    $("sqlite-import-panel").classList.toggle("hidden", !localInspection || !tables.length);
    $("sqlite-import-table").innerHTML = tables.map(name=>`<option value="${html(name)}">${html(name)}</option>`).join("");
    $("connection-heading").textContent = localInspection
      ? "Local schema source inspected — not certified"
      : "No enterprise system connected yet";
    $("connection-message").textContent = localInspection
      ? sqlite.message
      : "The read-only integration layer is installed. Connecting a real company system requires its specifications and explicit authorization.";
    $("connection-active-label").textContent = localInspection
      ? `Configured local source: ${sqlite.database_name || "SQLite"} (read-only)`
      : "No approved enterprise connection";
    $("connection-contract-count").textContent = `${sqlite.complete_table_schemas} / ${sqlite.required_tables} column schemas`;
    $("manager-connection-status").textContent = sqlite.connected
      ? `Read-only source available: ${sqlite.complete_table_schemas} of ${sqlite.required_tables} canonical table schemas found. Choose a table to import a local snapshot; source data is not certified.`
      : "No SQLite schema source configured. You can still upload a CSV or XLSX now.";
    const descriptions = {
      SQLITE: "Local read-only SQLite. Import a selected table explicitly for charts and Copilot.",
      SQL_SERVER_POSTGRESQL: "Adapter interface reserved until a company database is identified.",
      REST_API: "ERP / WMS / TMS system choice and approved API access required.",
    };
    $("connection-adapters").innerHTML = result.adapters.map((adapter, index) => {
      const implemented = adapter.implementation === "READ_ONLY_METADATA_AND_MANUAL_TABLE_SNAPSHOT";
      const label = implemented ? (sqlite.connected ? "SCHEMA INSPECTED" : "READY TO CONFIGURE") : "NOT YET BUILT";
      return `<article class="panel connection-adapter"><div class="connector-mark">${index === 0 ? "DB" : index === 1 ? "SQL" : "API"}</div><strong>${html(adapter.name)}</strong><p>${html(descriptions[adapter.kind] || "Connector specification required.")}</p><span class="status-pill ${implemented ? "schema" : ""}">${label}</span></article>`;
    }).join("");
    $("connection-contracts-tbody").innerHTML = sqlite.table_contracts.map(row => {
      const allColumnsPresent = row.status === "COLUMNS_PRESENT_NOT_CERTIFIED";
      const displayStatus = allColumnsPresent ? "COLUMNS PRESENT · NOT CERTIFIED" : row.status.replaceAll("_", " ");
      return `<tr><td><span class="order-ref">${html(row.table)}</span></td><td>${html(row.module)}</td><td>${row.required_fields}</td><td><span class="status-pill ${allColumnsPresent ? "schema" : ""}">${html(displayStatus)}</span></td><td>${html(row.missing_fields.length ? row.missing_fields.join(", ") : "None · meaning not checked")}</td></tr>`;
    }).join("");
  } catch (error) {
    $("connection-heading").textContent = "Connection inspection unavailable";
    $("connection-message").textContent = error.message;
    $("manager-connection-status").textContent = "Connection status unavailable.";
    toast(`Enterprise connections: ${error.message}`);
  }
}
function setupConnections() {
  $("connection-refresh").addEventListener("click", loadConnections);
  $("sqlite-import-btn").addEventListener("click", async () => {
    const table = $("sqlite-import-table").value;
    if (!table || state.intakeBusy) return;
    state.intakeBusy = true;
    $("sqlite-import-btn").disabled = true;
    $("sqlite-import-feedback").textContent = "Loading the selected local table...";
    try {
      const result = await request("/api/intake/sqlite", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({table})});
      state.chatHistory = []; // Disconnect previous dataset conversation context.
      renderIntake(result);
      renderVisualizations(result);
      $("sqlite-import-feedback").textContent = `Imported ${fmt(result.rows)} records from '${table}' read-only. Source unchanged.`;
      toast("Read-only SQLite snapshot loaded.");
      navigate("visualizations");
    } catch(error) {
      $("sqlite-import-feedback").textContent = error.message;
      toast(`SQLite import: ${error.message}`);
    } finally {
      state.intakeBusy = false;
      $("sqlite-import-btn").disabled = false;
    }
  });
}

function managerBars(hostId, items, total, emptyMessage) {
  const host=$(hostId);
  if (!items.length) {
    host.innerHTML=`<div class="manager-chart-empty">${html(emptyMessage)}</div>`;
    return;
  }
  const maximum=Math.max(1,...items.map(item=>Number(item.count)||0));
  host.innerHTML=items.map(item=>{
    const count=Math.max(0, Number(item.count)||0);
    const width=(count/maximum*100).toFixed(2);
    return `<div class="manager-bar-row"><span class="manager-bar-label" title="${html(item.label)}">${html(item.label)}</span><div class="manager-bar-track"><span style="width:${width}%"></span></div><strong>${fmt(count)}</strong></div>`;
  }).join("");
}
async function loadModelSelection() {
  try {
    const data = await request("/api/model-selection");
    if (!data.available) throw Error(data.error || "Benchmark evidence not loaded.");
    const first = data.selected_algorithm;
    $("model-selection-summary").textContent = `${data.models_tested_successfully} historical configurations checked. Selection: ${first.name} (January average precision ${Number(first.average_precision).toFixed(5)}, ROC-AUC ${Number(first.roc_auc).toFixed(5)}). Not a certified operational improvement.`;
    $("model-selection-rank").innerHTML = (data.sorted_candidates || []).slice(0,5).map((r,i)=>
      `<div class="manager-priority"><span class="manager-priority-index">${i+1}</span><div><strong>${html(r.name)}</strong><p>Average precision ${fixed(r.average_precision,5)} · ROC-AUC ${fixed(r.roc_auc,5)}</p></div></div>`).join("");
  } catch(error) {$("model-selection-summary").textContent = `Research model report unavailable: ${error.message}`;}
}

// Render only server-computed aggregate values; no raw uploaded records enter charts.
function adaptiveChartVisual(spec) {
  const values=(spec.values||[]).filter(x=>Number.isFinite(Number(x.count)) && Number(x.count)>=0);
  if(!values.length) return `<p>No usable observations for this chart.</p>`;
  const colors=["#37bda9","#7db3f2","#b7a0ee","#f2bd82","#e9828e","#a4bd75","#d1a5bb","#80a9a6"];
  if(spec.type==="line" && values.length>1){
    const high=Math.max(1,...values.map(v=>Number(v.count)));
    const coords=values.map((v,i)=>[34 + i*480/(values.length-1),175-(Number(v.count)/high)*136]);
    const polygon=coords.map(v=>v.map(n=>n.toFixed(1)).join(",")).join(" ");
    const marks=coords.map(([x,y],i)=>`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4" fill="#37bda9"><title>${html(values[i].label)}: ${fmt(values[i].count)}</title></circle>`).join("");
    const ticks=coords.map(([x],i)=>`<text x="${x.toFixed(1)}" y="194" text-anchor="middle" fill="#a4b9ce" font-size="11">${html(String(values[i].label).slice(2))}</text>`).join("");
    return `<svg viewBox="0 0 560 214" class="adaptive-line" role="img" aria-label="${html(spec.title)}"><line x1="30" y1="175" x2="526" y2="175" stroke="#536578"/><polyline points="${polygon}" fill="none" stroke="#37bda9" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>${marks}${ticks}</svg>`;
  }
  if(spec.type==="donut"){
    const total=values.reduce((sum,v)=>sum+Number(v.count),0);
    if(!total) return `<p>No positive counts for a category chart.</p>`;
    let pos=0;
    const arcs=values.map((v,i)=>{const pct=Number(v.count)/total*100;const arc=`<circle cx="88" cy="88" r="57" fill="none" stroke="${colors[i%colors.length]}" stroke-width="26" stroke-dasharray="${pct.toFixed(4)} ${(100-pct).toFixed(4)}" stroke-dashoffset="${(-pos).toFixed(4)}" pathLength="100" transform="rotate(-90 88 88)"/>`;pos+=pct;return arc;}).join("");
    const legend=values.map((v,i)=>`<div class="adaptive-legend"><span class="adaptive-dot" style="background:${colors[i%colors.length]}"></span><span title="${html(v.label)}">${html(v.label)}</span><strong>${fmt(v.count)}</strong></div>`).join("");
    return `<div class="adaptive-donut-wrap"><svg viewBox="0 0 176 176" role="img" aria-label="${html(spec.title)}"><circle cx="88" cy="88" r="57" fill="none" stroke="#24364a" stroke-width="26"/>${arcs}<text x="88" y="94" fill="#e5eef8" text-anchor="middle" font-size="19">${fmt(total)}</text></svg><div class="adaptive-legends">${legend}</div></div>`;
  }
  // Categorical bars and numeric histograms use transparent, labeled aggregates.
  const maximum=Math.max(1,...values.map(v=>Number(v.count)));
  return `<div class="manager-bars">${values.map(v=>{const val=Number(v.count);return `<div class="manager-bar-row"><span class="manager-bar-label" title="${html(v.label)}">${html(v.label)}</span><div class="manager-bar-track"><span style="width:${(val/maximum*100).toFixed(2)}%"></span></div><strong>${fmt(val)}${spec.value_label?.includes("(%)") ? "%" : ""}</strong></div>`;}).join("")}</div>`;
}
function renderAdaptiveCharts(plan) {
  const charts=plan?.charts||[];
  const host=$("adaptive-charts");
  $("adaptive-summary").textContent=charts.length
    ? `${plan.business_context || "Uploaded dataset"}. Selected ${charts.length} relevant chart(s) from recorded fields and values; ${plan.excluded_count||0} other candidate(s) ranked lower. Mapping fields can change these choices.`
    : "No reliable chart types were detected. Map business fields or provide a dataset with usable dates, categories or numeric values.";
  $("adaptive-warnings").textContent=(plan?.warnings||[]).join(" ");
  host.innerHTML=charts.map(spec=>`<article class="panel manager-chart adaptive-card" data-chart-id="${html(spec.id)}">
    <div class="panel-kicker">${html(spec.type.toUpperCase())} · ${html(spec.value_label)} · ${html(spec.selection_basis)}</div>
    <h2>${html(spec.title)}</h2><p>${html(spec.reason)}</p>
    ${adaptiveChartVisual(spec)}
    <div class="adaptive-provenance">Source: ${html((spec.source_columns||[]).join(" + "))}. ${html(spec.caution)}</div>
    <div class="adaptive-card-actions" role="group" aria-label="Chart actions"><button type="button" class="secondary-action adaptive-customize-button" data-adaptive-customize="${html(spec.id)}">Customize a copy</button><button type="button" class="secondary-action adaptive-ask-button" data-adaptive-ask="${html(spec.id)}">Ask AEGIS about this chart</button></div>
  </article>`).join("");
  host.querySelectorAll("[data-adaptive-customize]").forEach(button => button.addEventListener("click", () => customizeRecommendedChart(button.dataset.adaptiveCustomize)));
  host.querySelectorAll("[data-adaptive-ask]").forEach(button => button.addEventListener("click", () => askAboutChart(`auto:${button.dataset.adaptiveAsk}`)));
  refreshChartChoices();
}


function customizeRecommendedChart(chartId) {
  const template = (state.intake?.adaptive_dashboard?.charts || []).find(item => item.id === chartId);
  if (!template) return toast("The suggested chart is no longer available in this dataset.");
  openCustomEditor();
  const fields = (template.source_columns || []).filter(name => state.intake.columns.includes(name));
  if (!fields.length) return;
  $("custom-chart-type").value = ["bar", "line", "donut"].includes(template.type) ? template.type : "bar";
  let x = fields[0], y = "", agg = "count", grain = "none";
  if (["recorded_amount_by_group", "units_by_group"].includes(template.id) && fields.length >= 2) {
    x = fields[1]; y = fields[0]; agg = "sum";
  } else if (template.id === "recorded_amount_trend" && fields.length >= 2) {
    x = fields[0]; y = fields[1]; agg = "sum"; grain = "month";
  } else if (template.id === "activity_over_time") {
    grain = "month";
  }
  $("custom-chart-x").value = x;
  $("custom-chart-y").value = y;
  $("custom-chart-agg").value = agg;
  $("custom-chart-grain").value = grain;
  $("custom-chart-sort").value = (grain !== "none") ? "x_asc" : "value_desc";
  $("custom-chart-title").value = template.title.slice(0, 100);
  $("custom-chart-feedback").textContent = "Starting from an automatic suggestion. Adjust fields and chart type; the new chart is your editable copy, while the automatic original stays unchanged.";
}

// Manager-defined charts: full-dataset calculations are performed by the local
// validated Python endpoint, never from a sampled preview or executable code.
function customChartNumber(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("en-US", {maximumFractionDigits: 6});
}
function customChartSVG(spec) {
  const typ = spec.chart_type;
  if (typ === "table") {
    return `<div class="custom-chart-table-wrap"><table class="custom-chart-table"><thead><tr><th>${html(spec.x)}</th><th>${html(spec.aggregation === "count" ? "Rows" : spec.aggregation + " of " + spec.y)}</th></tr></thead><tbody>${spec.values.map(item => `<tr><td>${html(item.label)}</td><td>${customChartNumber(item.value)}</td></tr>`).join("")}</tbody></table></div>`;
  }
  if (typ === "scatter") {
    const points = spec.points || [];
    const xs = points.map(p => Number(p.x)), ys = points.map(p => Number(p.y));
    let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    if (x0 === x1) { x0 -= 1; x1 += 1; }
    if (y0 === y1) { y0 -= 1; y1 += 1; }
    const marks = points.map(p => `<circle cx="${(62 + 514 * (p.x - x0) / (x1 - x0)).toFixed(2)}" cy="${(208 - 174 * (p.y - y0) / (y1 - y0)).toFixed(2)}" r="3" fill="#48d9d0" fill-opacity=".55"><title>${html(spec.x)}: ${customChartNumber(p.x)}; ${html(spec.y)}: ${customChartNumber(p.y)}</title></circle>`).join("");
    return `<svg class="custom-chart-svg" viewBox="0 0 640 265" role="img" aria-label="Scatter chart ${html(spec.x)} versus ${html(spec.y)}"><line x1="62" y1="208" x2="580" y2="208" stroke="#718b9f"/><line x1="62" y1="30" x2="62" y2="208" stroke="#718b9f"/>${marks}<text x="62" y="231" fill="#aec0d1" font-size="11">${customChartNumber(x0)}</text><text x="580" y="231" fill="#aec0d1" font-size="11" text-anchor="end">${customChartNumber(x1)}</text><text x="56" y="35" fill="#aec0d1" font-size="11" text-anchor="end">${customChartNumber(y1)}</text><text x="56" y="208" fill="#aec0d1" font-size="11" text-anchor="end">${customChartNumber(y0)}</text><text x="325" y="255" fill="#c2d3df" text-anchor="middle" font-size="12">${html(spec.x)}</text></svg>`;
  }
  const values = (spec.values || []).map(p => ({label: String(p.label), value: Number(p.value)}));
  if (!values.length) return `<p>No displayable chart values.</p>`;
  if (typ === "horizontal_bar") {
    const max = Math.max(1, ...values.map(p => Math.abs(p.value)));
    return `<div class="custom-hbars">${values.map(p => `<div class="custom-hbar"><div title="${html(p.label)}">${html(p.label)}</div><div class="custom-hbar-track"><span style="width:${(Math.abs(p.value) / max * 100).toFixed(2)}%;background:${p.value < 0 ? "#ea9b80" : "#38c4b6"}"></span></div><strong>${customChartNumber(p.value)}</strong></div>`).join("")}</div>`;
  }
  if (typ === "pie" || typ === "donut") {
    const total = values.reduce((sum, p) => sum + p.value, 0);
    if (total <= 0) return `<p>No positive values.</p>`;
    const palette = ["#3dd0c4", "#729fec", "#bc9ce7", "#f4bd88", "#eb869b", "#b9d37e", "#80c1b8", "#d89fc7", "#e8cc77", "#9ed7ee"];
    let offset = 0;
    const arcs = values.map((p, i) => { const percent = 100 * p.value / total; const start = offset; offset += percent;
      return `<circle cx="90" cy="90" r="${typ === "pie" ? 43 : 61}" fill="none" stroke="${palette[i % palette.length]}" stroke-width="${typ === "donut" ? 30 : 86}" stroke-dasharray="${percent} ${100-percent}" stroke-dashoffset="${-start}" pathLength="100" transform="rotate(-90 90 90)"><title>${html(p.label)}: ${customChartNumber(p.value)} (${percent.toFixed(1)}% of shown values)</title></circle>`; }).join("");
    return `<div class="custom-pie"><svg viewBox="0 0 180 180" role="img" aria-label="${html(typ)} chart"><circle cx="90" cy="90" r="${typ === "pie" ? 43 : 61}" fill="none" stroke="#294457" stroke-width="${typ === "pie" ? 86 : 34}"/>${arcs}${typ === "donut" ? `<text x="90" y="95" text-anchor="middle" fill="#e7f7f7" font-size="13">${html(customChartNumber(total))}</text>` : ""}</svg><div class="custom-pie-legend">${values.map((p, i) => `<div><i style="background:${palette[i % palette.length]}"></i><span title="${html(p.label)}">${html(p.label)}</span><strong>${(p.value / total * 100).toFixed(1)}%</strong></div>`).join("")}</div></div>`;
  }
  // Grouped lines / area / vertical bars / numeric histograms. Include a zero
  // baseline even when values are negative; no silent clipping of signed data.
  const high = Math.max(0, ...values.map(p => p.value));
  const low = Math.min(0, ...values.map(p => p.value));
  const spread = high - low || 1;
  const top = 24, bottom = 218, left = 60, right = 604;
  const yPos = n => bottom - (n - low) / spread * (bottom - top);
  const baseline = yPos(0);
  let shapes = `<line x1="${left}" y1="${bottom}" x2="${right}" y2="${bottom}" stroke="#4c6a84"/><line x1="${left}" y1="${top}" x2="${left}" y2="${bottom}" stroke="#4c6a84"/><line x1="${left}" y1="${baseline.toFixed(2)}" x2="${right}" y2="${baseline.toFixed(2)}" stroke="#7890a4" stroke-dasharray="4 5"/>`;
  const coords = values.map((p, i) => [left + (i + .5) * (right - left) / values.length, yPos(p.value)]);
  if (typ === "line" || typ === "area") {
    const segments = coords.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
    if (typ === "area") {
      const polygon = `${coords[0][0].toFixed(2)},${baseline.toFixed(2)} ${segments} ${coords[coords.length-1][0].toFixed(2)},${baseline.toFixed(2)}`;
      shapes += `<polygon points="${polygon}" fill="#2eacb3" fill-opacity=".20"/>`;
    }
    shapes += `<polyline points="${segments}" fill="none" stroke="#3ed7cd" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`;
    shapes += coords.map(([x, y], i) => `<circle cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="3.3" fill="#a0e7df"><title>${html(values[i].label)}: ${customChartNumber(values[i].value)}</title></circle>`).join("");
  } else {
    const band = (right - left) / values.length;
    const width = Math.max(1, band * .72);
    shapes += values.map((p, i) => { const x = left + i * band + (band - width) / 2; const y = yPos(p.value);
      return `<rect x="${x.toFixed(2)}" y="${Math.min(y,baseline).toFixed(2)}" width="${width.toFixed(2)}" height="${Math.max(1, Math.abs(y-baseline)).toFixed(2)}" rx="2" fill="${p.value < 0 ? "#ee9d80" : "#39beb8"}"><title>${html(p.label)}: ${customChartNumber(p.value)}</title></rect>`; }).join("");
  }
  const every = Math.max(1, Math.ceil(values.length / 8));
  shapes += values.map((p, i) => i % every === 0 || i === values.length - 1 ? `<text x="${coords[i][0].toFixed(2)}" y="239" text-anchor="middle" fill="#b0c5d2" font-size="10">${html(p.label.slice(0, 13))}</text>` : "").join("");
  shapes += `<text x="54" y="${top+4}" text-anchor="end" fill="#b0c5d2" font-size="11">${html(customChartNumber(high))}</text><text x="54" y="${bottom+3}" text-anchor="end" fill="#b0c5d2" font-size="11">${html(customChartNumber(low))}</text>`;
  return `<svg class="custom-chart-svg" viewBox="0 0 640 260" role="img" aria-label="${html(typ)} chart, X ${html(spec.x)}, Y ${html(spec.y || "row count")}">${shapes}</svg>`;
}
function currentChartCatalog() {
  if (!state.intake?.loaded) return [];
  const defaults = (state.intake.adaptive_dashboard?.charts || []).map(item => ({
    key: `auto:${item.id}`, kind: "automatic", id: item.id
  }));
  const custom = state.customCharts.map((item, i) => ({
    key: `custom:${i}`, kind: "custom", options: {
      chart_type:item.spec.chart_type, x:item.spec.x, y:item.spec.y,
      aggregation:item.spec.aggregation, date_grain:item.spec.date_grain,
      sort:item.spec.sort, limit:item.spec.limit
    }
  }));
  return [...defaults, ...custom];
}
function refreshChartChoices() {
  const sel = $("copilot-chart-focus");
  if (!sel) return;
  const previous = sel.value;
  const defaults = state.intake?.adaptive_dashboard?.charts || [];
  const opts = ['<option value="">All current charts / general dataset</option>'];
  defaults.forEach(item => opts.push(`<option value="auto:${html(item.id)}">Automatic · ${html(item.title)}</option>`));
  state.customCharts.forEach((item, i) => opts.push(`<option value="custom:${i}">Custom ${i+1} · ${html(item.title || (item.spec.y || 'Rows') + ' by ' + item.spec.x)}</option>`));
  sel.innerHTML = opts.join("");
  sel.value = [...sel.options].some(option=>option.value===previous) ? previous : "";
  $("chart-chat-selector").classList.toggle("hidden", !state.intake?.loaded);
}
function askAboutChart(key) {
  refreshChartChoices();
  const select=$("copilot-chart-focus");
  if (!([...select.options].some(x=>x.value===key))) return toast("That chart is not available for the current dataset.");
  select.value=key;
  $("copilot-context").value="local_dataset";
  syncCopilotContext();
  navigate("copilot");
  $("chat-question").value="Explain what this chart shows, the main pattern, how the values were calculated, and any limitations.";
  $("chat-question").focus();
}
function renderCustomCharts() {
  const host = $("custom-chart-cards");
  if (!host) return;
  const cards = state.customCharts || [];
  $("custom-chart-empty").classList.toggle("hidden", cards.length > 0);
  host.innerHTML = cards.map((entry, index) => `<article class="panel custom-chart-card" data-custom-index="${index}">
    <div class="custom-chart-card-header"><div class="panel-kicker">${html(entry.spec.chart_type.replaceAll("_", " ").toUpperCase())} · ${html(entry.spec.aggregation)}</div><div class="custom-chart-card-actions"><button type="button" class="secondary-action custom-ask-button" data-custom-ask="${index}">Ask AEGIS</button><button type="button" class="secondary-action" data-custom-edit="${index}">Edit</button><button type="button" class="secondary-action" data-custom-duplicate="${index}">Duplicate</button><button type="button" class="secondary-action" data-custom-remove="${index}">Remove</button></div></div>
    <h3>${html(entry.title || `${entry.spec.x} vs ${entry.spec.y || "record count"}`)}</h3><p class="custom-chart-axis">X: ${html(entry.spec.x)} · Y: ${html(entry.spec.y || "Rows")} · ${html(entry.spec.aggregation.replaceAll("_", " "))}${entry.spec.date_grain !== "none" ? " · " + html(entry.spec.date_grain) : ""}</p>
    ${customChartSVG(entry.spec)}<p class="custom-chart-note">${html(entry.spec.note)}</p><p class="custom-chart-caution">${html(entry.spec.caution)}</p>
  </article>`).join("");
  host.querySelectorAll("[data-custom-edit]").forEach(btn => btn.addEventListener("click", () => openCustomEditor(Number(btn.dataset.customEdit))));
  host.querySelectorAll("[data-custom-ask]").forEach(btn => btn.addEventListener("click", () => askAboutChart(`custom:${btn.dataset.customAsk}`)));
  host.querySelectorAll("[data-custom-remove]").forEach(btn => btn.addEventListener("click", () => { state.customCharts.splice(Number(btn.dataset.customRemove), 1); renderCustomCharts(); }));
  host.querySelectorAll("[data-custom-duplicate]").forEach(btn => btn.addEventListener("click", () => { if (state.customCharts.length >= 12) return toast("Keep up to 12 custom charts at a time."); const entry = state.customCharts[Number(btn.dataset.customDuplicate)]; state.customCharts.push({spec: entry.spec, title: `${entry.title} (copy)`}); renderCustomCharts(); }));
  refreshChartChoices();
}
function setCustomChartOptions() {
  const columns = state.intake?.columns || [];
  const key = columns.join("\u001f");
  if (state.customFieldsKey === key) return;
  state.customFieldsKey = key;
  const opts = columns.map(name => `<option value="${html(name)}">${html(name)}</option>`).join("");
  $("custom-chart-x").innerHTML = `<option value="">Choose X-axis field</option>${opts}`;
  $("custom-chart-y").innerHTML = `<option value="">No Y field (count rows)</option>${opts}`;
  $("custom-chart-agg").value = "count";
  $("custom-chart-type").value = "bar";
}
function openCustomEditor(index = -1) {
  if (!state.intake?.loaded) { toast("Upload a dataset first."); return; }
  setCustomChartOptions();
  state.customEditing = index;
  $("custom-chart-editor").classList.remove("hidden");
  $("custom-chart-toggle").setAttribute("aria-expanded", "true");
  $("custom-chart-save").textContent = index >= 0 ? "Update chart" : "Create chart";
  if (index >= 0) {
    const {spec, title} = state.customCharts[index];
    for (const [name, value] of Object.entries({type:spec.chart_type, x:spec.x, y:spec.y || "", agg:spec.aggregation,
      grain:spec.date_grain, sort:spec.sort, limit:String(spec.limit), title})) {
      const control = $("custom-chart-" + name);
      if (control) control.value = value;
    }
  } else {
    $("custom-chart-title").value = "";
    $("custom-chart-y").value = "";
    $("custom-chart-agg").value = "count";
    $("custom-chart-grain").value = "none";
    $("custom-chart-sort").value = "value_desc";
    $("custom-chart-limit").value = "20";
  }
  $("custom-chart-feedback").textContent = "Each saved chart is computed read-only from every accepted source row.";
  $("custom-chart-editor").scrollIntoView({behavior: "smooth", block: "nearest"});
}
function closeCustomEditor() {
  state.customEditing = -1;
  $("custom-chart-editor").classList.add("hidden");
  $("custom-chart-toggle").setAttribute("aria-expanded", "false");
}
function setupCustomCharts() {
  state.customCharts = [];
  state.customEditing = -1;
  state.customFieldsKey = null;
  state.customDatasetKey = null;
  $("custom-chart-toggle").addEventListener("click", () => $("custom-chart-editor").classList.contains("hidden") ? openCustomEditor() : closeCustomEditor());
  $("custom-chart-cancel").addEventListener("click", closeCustomEditor);
  $("custom-chart-swap").addEventListener("click", () => {
    const x = $("custom-chart-x"), y = $("custom-chart-y");
    if (!y.value) return toast("Choose a Y field first to swap axes.");
    [x.value, y.value] = [y.value, x.value];
  });
  $("custom-chart-type").addEventListener("change", () => {
    const typ = $("custom-chart-type").value;
    if (typ === "scatter") { $("custom-chart-agg").value = "count"; $("custom-chart-grain").value = "none"; }
    if (typ === "histogram") { $("custom-chart-y").value = ""; $("custom-chart-agg").value = "count"; $("custom-chart-grain").value = "none"; }
    if (typ === "line" || typ === "area") $("custom-chart-sort").value = "x_asc";
    $("custom-chart-feedback").textContent = typ === "scatter" ? "Scatter plots individual numeric X/Y pairs; up to 300 points are displayed with the exact limit disclosed." :
      typ === "histogram" ? "Histogram counts numeric values from X in chosen bins; no Y field is needed." :
      typ === "pie" || typ === "donut" ? "Pie/donut charts require nonnegative, comparable groups. Use bar or table for signed values." :
      "Choose any columns. AEGIS will validate whether the calculation and chart type make sense.";
  });
  $("custom-chart-y").addEventListener("change", () => {
    if ($("custom-chart-y").value && $("custom-chart-agg").value === "count" && !["scatter", "histogram"].includes($("custom-chart-type").value)) $("custom-chart-agg").value = "sum";
  });
  $("custom-chart-editor").addEventListener("submit", async event => {
    event.preventDefault();
    if (!state.intake?.loaded) return;
    if (state.customEditing < 0 && state.customCharts.length >= 12) return toast("Keep up to 12 custom charts at a time.");
    const spec = {chart_type: $("custom-chart-type").value, x: $("custom-chart-x").value,
      y: $("custom-chart-y").value || null, aggregation: $("custom-chart-agg").value,
      date_grain: $("custom-chart-grain").value, sort: $("custom-chart-sort").value,
      limit: Number($("custom-chart-limit").value)};
    const title = $("custom-chart-title").value.trim().slice(0,100);
    $("custom-chart-save").disabled = true;
    $("custom-chart-feedback").textContent = "Calculating from the current uploaded dataset…";
    try {
      const answer = await request("/api/intake/chart", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(spec)});
      if (!state.intake?.loaded || answer.dataset_revision !== state.intake.dataset_revision) throw Error("The current uploaded dataset changed. Recreate the chart.");
      const entry = {spec:answer, title};
      if (state.customEditing >= 0) state.customCharts[state.customEditing] = entry;
      else state.customCharts.push(entry);
      renderCustomCharts();
      closeCustomEditor();
      toast("Your chart was created from the uploaded data.");
    } catch (error) { $("custom-chart-feedback").textContent = error.message; toast(error.message); }
    finally { $("custom-chart-save").disabled = false; }
  });
}

function renderVisualizations(data) {
  const ready=!!data?.loaded;
  $("viz-empty").classList.toggle("hidden",ready);
  $("viz-ready").classList.toggle("hidden",!ready);
  if(!ready) { refreshChartChoices(); return; }
  const v=data.visualizations || {};
  renderAdaptiveCharts(data.adaptive_dashboard);
  setCustomChartOptions();
  renderCustomCharts();
  $("viz-filename").textContent=data.filename;
  $("viz-rows").textContent=fmt(v.row_count);
  $("viz-columns").textContent=fmt(v.column_count);
  $("viz-quality").textContent=`${fixed(v.completeness_pct,1)}%`;
  $("viz-mapped").textContent=String(data.insights.mapped_roles);
  $("viz-category-title").textContent=v.categories_source_column ? `Grouped by ${v.categories_source_column}` : "Record distribution";
  $("viz-category-caption").textContent="Source value counts — not estimated business risk";
  managerBars("viz-categories",v.categories || [],v.row_count,"Map a supplier or region field, or upload a dataset with categorical values.");
  managerBars("viz-completeness",(v.completeness_by_field || []).slice(0,12),v.row_count,"No columns available.");
  $("viz-timeline-panel").classList.toggle("hidden",!(v.timeline_last_12_periods || []).length);
  $("viz-timeline-caption").textContent=`From mapped ${v.monthly_source_column || "date"} field · last 12 parseable months`;
  managerBars("viz-timeline",v.timeline_last_12_periods || [],0,"Map a purchase timestamp to see the trend.");
  $("viz-outcome-panel").classList.toggle("hidden",!(v.delivery_date_comparison || []).length);
  managerBars("viz-outcomes",v.delivery_date_comparison || [],v.delivery_comparable_rows,"Map promise and delivery dates to compare them.");
  $("viz-priorities").innerHTML=(data.review_priorities||[]).map((item,i)=>
    `<div class="manager-priority"><span class="manager-priority-index">${i+1}</span><div><strong>${html(item.title)}</strong><p>${html(item.evidence)}</p><small>${html(item.next_step)}</small></div></div>`).join("");
}

function renderIntake(data) {
  state.intake = data.loaded ? data : null;
  const datasetKey = data.loaded ? String(data.dataset_revision) : null;
  if (state.customDatasetKey !== datasetKey) {
    state.customCharts = [];
    state.customFieldsKey = null;
    state.customDatasetKey = datasetKey;
    state.copilotSessionId = null;
    state.chatHistory = [];
    if ($("copilot-chart-focus")) $("copilot-chart-focus").value = "";
    if ($("custom-chart-editor")) closeCustomEditor();
  }

  // A file loaded after initial General chat must become the active evidence.
  // Natural Qwen stays enabled locally; no raw records are passed to the model.
  if (data.loaded && $("copilot-context").value === "general") {
    $("copilot-context").value = "local_dataset";
    syncCopilotContext();
  } else if (!data.loaded && $("copilot-context").value === "local_dataset") {
    $("copilot-context").value = "general";
    syncCopilotContext();
  }
  renderVisualizations(state.intake);
  $("intake-loaded").classList.toggle("hidden", !data.loaded);
  if (!data.loaded) {
    $("intake-upload-message").textContent = "No local dataset loaded";
    return;
  }
  $("intake-filename").textContent = data.filename;
  $("intake-file-detail").textContent = `${data.format} · ${fmt(data.size_bytes)} bytes · held only until you remove it or exit AEGIS`;
  $("intake-upload-message").textContent = `${data.filename} inspected locally`;
  $("intake-rows").textContent = fmt(data.rows);
  $("intake-columns").textContent = fmt(data.columns.length);
  $("intake-mapped").textContent = fmt(data.insights.mapped_roles);
  const options = data.columns.map(name => `<option value="${html(name)}">${html(name)}</option>`).join("");
  $("intake-mapping-fields").innerHTML = Object.entries(data.roles).map(([key, label]) => {
    const chosen = data.mapping[key] || "";
    return `<label class="intake-role"><span>${html(label)}</span><select data-role="${html(key)}" aria-label="Map ${html(label)}"><option value="">Not available / not sure</option>${options}</select></label>`;
  }).join("");
  $("intake-mapping-fields").querySelectorAll("select[data-role]").forEach(select => {
    select.value = data.mapping[select.dataset.role] || "";
  });
  const info = data.insights;
  const insights = [
    ["Fields you mapped", `${info.mapped_roles} of ${Object.keys(data.roles).length}`, "Manual selections; not proof of business meaning"],
    ["Repeat order references", info.duplicate_order_rows === null ? "Not mapped" : fmt(info.duplicate_order_rows), "Repeated IDs can be normal in order-line data"],
    ["Comparable timestamp pairs", info.timestamp_pairs === null ? "Not mapped" : fmt(info.timestamp_pairs), "Strict ISO date comparison only"],
    ["Recorded after promise", info.recorded_after_promise === null ? "Not mapped" : fmt(info.recorded_after_promise), "Not a certified late-delivery rate"],
  ];
  $("intake-insights").innerHTML = insights.map(([title, value, note]) => `<div class="intake-insight"><span>${html(title)}</span><strong>${html(value)}</strong><small>${html(note)}</small></div>`).join("");
  $("intake-profile-body").innerHTML = data.column_profiles.map(field => {
    const completeness = Math.max(0, 100 - Number(field.blank_pct));
    return `<tr><td><span class="order-ref">${html(field.name)}</span></td><td>${fmt(field.blank_count)}</td><td>${fixed(field.blank_pct, 2)}%</td><td><div class="intake-quality-bar"><span style="width:${completeness}%"></span></div></td></tr>`;
  }).join("");
  $("intake-preview-head").innerHTML = `<tr><th>#</th>${data.columns.map(name => `<th>${html(name)}</th>`).join("")}</tr>`;
  $("intake-preview-body").innerHTML = data.preview.map((row, index) => `<tr><td>${index + 1}</td>${data.columns.map(name => `<td title="${html(row[name])}">${html(String(row[name] ?? "").slice(0, 120))}</td>`).join("")}</tr>`).join("");
  const warnings = [...data.warnings, ...info.warnings];
  $("intake-warnings").innerHTML = warnings.length ? `<div class="panel intake-note"><div class="panel-kicker">INTERPRETATION NOTES</div>${warnings.map(line => `<p>• ${html(line)}</p>`).join("")}</div>` : "";
}

async function uploadIntakeFile(file) {
  if (!file || state.intakeBusy) return;
  if (!/\.(csv|xlsx)$/i.test(file.name)) { toast("Choose a CSV or XLSX file."); return; }
  if (!file.size || file.size > 20 * 1024 * 1024) { toast("File must be non-empty and smaller than 20 MB."); return; }
  state.intakeBusy = true;
  $("intake-choose").disabled = true;
  $("intake-upload-message").textContent = `Inspecting ${file.name}...`;
  try {
    const result = await request(`/api/intake/upload?name=${encodeURIComponent(file.name)}`, {
      method: "POST", headers: {"Content-Type": "application/octet-stream", "X-AEGIS-Upload": "1"}, body: file,
    });
    renderIntake(result);
    state.chatHistory = []; // Never carry one company's context into another upload.
    toast("Dataset loaded. Explore the charts, then verify any relevant field mappings.");
    navigate("visualizations");
  } catch (error) {
    $("intake-upload-message").textContent = `Import not accepted: ${error.message}`;
    toast(error.message);
  } finally {
    state.intakeBusy = false;
    $("intake-choose").disabled = false;
    $("intake-file").value = "";
  }
}

function setupIntake() {
  const picker = $("intake-file");
  const drop = $("intake-drop");
  $("intake-choose").addEventListener("click", () => picker.click());
  drop.addEventListener("click", () => picker.click());
  drop.addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); picker.click(); }
  });
  picker.addEventListener("change", () => uploadIntakeFile(picker.files[0]));
  drop.addEventListener("dragover", event => { event.preventDefault(); drop.classList.add("dragover"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("dragover"));
  drop.addEventListener("drop", event => {
    event.preventDefault(); drop.classList.remove("dragover");
    uploadIntakeFile(event.dataTransfer.files[0]);
  });
  $("intake-save-mapping").addEventListener("click", async () => {
    if (!state.intake || state.intakeBusy) return;
    const mapping = {};
    $("intake-mapping-fields").querySelectorAll("select[data-role]").forEach(select => {
      if (select.value) mapping[select.dataset.role] = select.value;
    });
    try {
      const result = await request("/api/intake/mapping", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({mapping})});
      renderIntake(result);
      toast("Mapping saved. Charts and review priorities are updated.");
      navigate("visualizations");
    } catch (error) { toast(error.message); }
  });
  $("intake-clear").addEventListener("click", async () => {
    if (!confirm("Remove the uploaded dataset from memory? Your original AEGIS research data will not be affected.")) return;
    try {
      renderIntake(await request("/api/intake/clear", {method:"POST", headers:{"Content-Type":"application/json"}, body:"{}"}));
      state.chatHistory = [];
      toast("Session dataset removed. Original research remains unchanged.");
    } catch (error) { toast(error.message); }
  });
  $("intake-ask").addEventListener("click", () => {
    $("copilot-context").value = "local_dataset";
    syncCopilotContext();
    navigate("copilot");
    $("chat-question").focus();
  });
}
function renderGovernance() {
  const limits=state.status?.limitations||[];
  $("limitations-list").innerHTML=limits.map(item=>`<div class="limitation"><strong>${html(item.title)}</strong><p>${html(item.detail)}</p></div>`).join("");
  const snap=state.status;
  if(!snap?.ready){$("provenance-data").textContent="Awaiting verified notebook research export";return;}
  const fields=[
    ["RESEARCH SNAPSHOT",String(snap.exported_at||"—").replace("T"," ").slice(0,19)+" UTC"],
    ["SCORING SCOPE",`${fmt(snap.summary.scored_orders)} historical orders`],
    ["ORIGINAL REGISTRY",`${fmt(snap.summary.source_orders)} unique source IDs`],
    ["OPTIMIZATION",`${snap.summary.scenarios} synthetic scenarios`],
    ["RUNTIME", "Local / 127.0.0.1 only"],
    ["BUSINESS ACTION", "NONE / NOT GRANTED"],
  ];
  $("provenance-data").innerHTML=fields.map(([name,value])=>`<div class="provenance-item"><span>${html(name)}</span><strong>${html(value)}</strong></div>`).join("");
}

function renderModelValidation(evidence) {
  const status = $("model-validation-status");
  const table = $("model-validation-table");
  const alerts = $("model-validation-alerts");
  if (!evidence?.available) {
    status.textContent = evidence?.error || "Archived validation evidence is unavailable for this research bundle.";
    table.innerHTML = `<tr><td colspan="5">No verified archived evidence for this bundle.</td></tr>`;
    alerts.textContent = "Metrics withheld until the archived report matches the frozen research bundle.";
    return;
  }
  status.textContent = "Archived retrospective audit: 23/23 software/source checks passed. Research-only; never operationally certified.";
  const names = ["TRAIN", "VALIDATION", "TEST", "ALL"];
  table.innerHTML = names.map(name => {
    const p = evidence.phases[name];
    return `<tr><td>${html(name)}</td><td>${fmt(p.count)}</td><td>${fixed(p.roc_auc, 4)}</td><td>${fixed(100*p.observed_late_rate, 2)}%</td><td>${fixed(100*p.mean_frozen_score, 2)}%</td></tr>`;
  }).join("");
  alerts.innerHTML = evidence.alerts.map(line => `<div class="limitation"><p>${html(line)}</p></div>`).join("");
}

function renderJointCapacity(report) {
  const status = $("joint-capacity-status");
  const summary = $("joint-capacity-summary");
  const tbody = $("joint-capacity-table");
  if (!report?.available) {
    status.textContent = report?.error || "Synthetic capacity evidence not available.";
    summary.textContent = "No allocation shown without source-derived evidence.";
    tbody.innerHTML = `<tr><td colspan="4">No verified source-derived synthetic allocation</td></tr>`;
    return;
  }
  const scope = report.scope;
  status.textContent = `Source-derived synthetic ${html(scope.month)} component ${html(scope.component)} · ${fmt(scope.orders)} whole orders · ${fmt(scope.eligible_pairs)} eligible order–supplier pairs. ${report.exact_cost_optimum_certified_for_synthetic_problem ? "Exact source-capacity cost optimum verified in this limited problem." : "Feasible solution only; optimality not certified."}`;
  const fields = [
    ["TOTAL UNITS",fmt(scope.total_order_units)],
    ["BASELINE SYNTHETIC COST",`$${fixed(report.baseline_landed_cost_usd)}`],
    ["SYNTHETIC JOINT ALLOCATION COST",report.result_landed_cost_usd == null ? "Not feasible" : `$${fixed(report.result_landed_cost_usd)}`],
    ["HYPOTHETICAL COST DIFFERENCE",report.hypothetical_cost_difference_usd == null ? "Not available" : `$${fixed(report.hypothetical_cost_difference_usd)}`],
    ["SUPPLIER CAPACITY CHECK",report.checks.all_monthly_capacities_respected ? "PASS — monthly component scope" : "NOT ESTABLISHED"],
    ["INDEPENDENT REFERENCE",report.independent_exact_reference?.matches_solver ? "Exact knapsack reference agrees" : "Not available"],
  ];
  summary.innerHTML = fields.map(([a,b])=>`<div class="provenance-item"><span>${html(a)}</span><strong>${html(b)}</strong></div>`).join("");
  tbody.innerHTML = Object.entries(report.capacity_by_supplier||{}).map(([supplier,cap])=>
    `<tr><td>${html(supplier)}</td><td>${fmt(cap.monthly_capacity_units)}</td><td>${fmt(cap.assigned_units)}</td><td>${fmt(cap.remaining_units)}</td></tr>`
  ).join("");
}

const sourceDescriptions={
  auto:"Automatic evidence routing · checked source shown after reply",
  joint_capacity:"Synthetic joint monthly capacity assignment",
  historical_order:"Real historical Olist research",headroom:"Synthetic capacity optimization",
  legacy_policy:"Synthetic sourcing policies",readiness:"Operational readiness contract",
  local_dataset:"Local user upload · unverified",
  general:"Local Qwen general conversation · no connected business evidence",
};
function syncCopilotContext(){
  const context=$("copilot-context").value;
  $("copilot-order-group").classList.toggle("hidden",!(["historical_order","auto"].includes(context)));
  $("copilot-scenario-group").classList.toggle("hidden",context!=="headroom");
  $("historical-outcome-panel").classList.toggle("hidden",!(["historical_order","auto"].includes(context)));
  if (context !== state.lastCopilotContext &&
      !(["general", "local_dataset"].includes(context) &&
        ["general", "local_dataset"].includes(state.lastCopilotContext))) {
    $("copilot-qwen").checked = false; // Changing to unrelated research evidence needs a fresh opt-in.
  }
  $("copilot-qwen").disabled = false;
  $("copilot-qwen-title").textContent = "Natural conversation with local Qwen (opt-in)";
  $("copilot-qwen-help").textContent = "Qwen runs locally. When you enable it, uploaded data is available for read-only calculations and bounded matching-row previews. The complete file is not pasted into Qwen.";
  state.lastCopilotContext = context;
  $("copilot-source-label").textContent=sourceDescriptions[context];
}

function renderHistoricalOutcomes(data) {
  state.historicalOutcomes = data;
  const node=$("historical-outcome-status");
  if(data.loaded){
    const c=data.summary;
    node.textContent=`Original Olist source attached · ${fmt(c.source_orders)} orders · ${fmt(c.comparable)} comparable dates. Before: ${fmt(c.before)}, on date: ${fmt(c.on)}, after: ${fmt(c.after)}.`;
    $("historical-outcome-remove").classList.remove("hidden");
  }else{
    node.textContent="Outcome dates unavailable. The frozen research scores do not include actual deliveries.";
    $("historical-outcome-remove").classList.add("hidden");
  }
}

function setupHistoricalOutcomes() {
  const section=document.createElement("section");
  section.id="historical-outcome-panel";
  section.className="historical-outcome-panel";
  section.innerHTML=`<div class="historical-outcome-heading">HISTORICAL DELIVERY EVIDENCE</div>
    <p id="historical-outcome-status">Checking original Olist outcomes...</p>
    <input id="historical-outcome-file" type="file" accept=".csv,text/csv" class="hidden" aria-label="Choose original Olist orders CSV">
    <button type="button" id="historical-outcome-choose" class="outcome-upload-button">Attach original Olist CSV</button>
    <button type="button" id="historical-outcome-remove" class="outcome-remove-button hidden">Detach</button>
    <small>Use <code>olist_orders_dataset.csv</code>. AEGIS checks every original order ID; dates stay in memory for this session. Estimated date ≠ certified customer promise.</small>`;
  $("copilot-order-group").insertAdjacentElement("afterend",section);
  const picker=$("historical-outcome-file");
  $("historical-outcome-choose").addEventListener("click",()=>picker.click());
  picker.addEventListener("change",async()=>{
    const file=picker.files?.[0];
    if(!file || state.outcomeBusy)return;
    if(!/\.csv$/i.test(file.name)||file.size>30*1024*1024||!file.size){toast("Choose the original Olist CSV (up to 30 MB).");picker.value="";return;}
    state.outcomeBusy=true;$("historical-outcome-choose").disabled=true;
    $("historical-outcome-status").textContent=`Checking original order IDs in ${file.name}...`;
    try{
      const data=await request(`/api/historical-outcomes/upload?name=${encodeURIComponent(file.name)}`,{
        method:"POST",headers:{"Content-Type":"application/octet-stream","X-AEGIS-Upload":"1"},body:file,
      });
      renderHistoricalOutcomes(data);
      state.chatHistory=state.chatHistory.filter(item=>item.context!=="historical_order");
      toast("Historical outcomes attached separately. Try the delivery-count question again.");
    }catch(error){
      renderHistoricalOutcomes(await request("/api/historical-outcomes"));
      toast(`Outcome import: ${error.message}`);
    }finally{state.outcomeBusy=false;$("historical-outcome-choose").disabled=false;picker.value="";}
  });
  $("historical-outcome-remove").addEventListener("click",async()=>{
    if(!confirm("Detach the original Olist outcome table from this session? Research scores remain untouched."))return;
    try{
      renderHistoricalOutcomes(await request("/api/historical-outcomes/clear",{
        method:"POST",headers:{"Content-Type":"application/json"},body:"{}",
      }));
      state.chatHistory=state.chatHistory.filter(item=>item.context!=="historical_order");
      toast("Original outcome table detached. Frozen research remains unchanged.");
    }catch(error){toast(error.message);}
  });
}
function addBubble(role, text, metadata) {
  const host=$("chat-messages");
  const welcome=host.querySelector(".welcome-message");
  if(welcome)welcome.remove();
  const bubble=document.createElement("div");
  bubble.className=`chat-bubble ${role}`;
  if(role==="assistant"){
    const label=document.createElement("div");label.className="bubble-head";label.textContent="✦  AEGIS";bubble.append(label);
  }
  const body=document.createElement("div");body.textContent=text;bubble.append(body);
  if(metadata && metadata.evidence_source !== "SOCIAL_DIALOGUE_NO_BUSINESS_DATA"){
    const foot=document.createElement("div");foot.className="bubble-evidence";
    foot.textContent=`Source: ${metadata.evidence_source}  ·  Routing: ${metadata.routing_mode}  ·  Business action: NONE`
      + (metadata.notice ? `\n${metadata.notice}` : "");
    bubble.append(foot);
  }
  // A recommendation is a *validated configuration*, not a browser-supplied
  // calculation. Chart creation asks the local server to recalculate it again.
  if(role === "assistant" && metadata?.chart_suggestion){
    const suggestion=metadata.chart_suggestion;
    const action=document.createElement("button");
    action.type="button";
    action.className="primary-action chart-recommendation-action";
    action.textContent=suggestion.kind === "automatic" ? "View recommended chart" : "Create recommended chart";
    action.addEventListener("click",()=>applyRecommendedChart(suggestion));
    bubble.append(action);
  }
  host.append(bubble);host.scrollTop=host.scrollHeight;
  return bubble;
}
async function applyRecommendedChart(suggestion){
  if(!state.intake?.loaded || suggestion?.dataset_revision !== state.intake.dataset_revision){
    return toast("The dataset changed. Ask AEGIS for a new chart recommendation.");
  }
  if(suggestion.kind === "automatic"){
    const exists=(state.intake.adaptive_dashboard?.charts||[]).some(x=>x.id===suggestion.chart_id);
    if(!exists)return toast("That automatically selected chart is no longer available.");
    navigate("visualizations");
    const card=[...document.querySelectorAll("[data-chart-id]")].find(x=>x.dataset.chartId===suggestion.chart_id);
    if(card)card.scrollIntoView({behavior:"smooth",block:"center"});
    return;
  }
  if(suggestion.kind !== "custom" || !suggestion.options)return toast("Unsupported recommendation.");
  if(state.customCharts.length >= 12)return toast("Keep up to 12 custom charts at a time.");
  try{
    const computed=await request("/api/intake/chart",{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(suggestion.options)
    });
    if(!state.intake?.loaded || computed.dataset_revision !== suggestion.dataset_revision){
      throw Error("The dataset changed during calculation. Ask for a new recommendation.");
    }
    state.customCharts.push({spec:computed,title:String(suggestion.title||"").slice(0,100)});
    navigate("visualizations");
    renderCustomCharts();
    const cards=document.querySelectorAll(".custom-chart-card");
    if(cards.length)cards[cards.length-1].scrollIntoView({behavior:"smooth",block:"center"});
    toast("Suggested chart created. Use Edit to change the axes or chart type.");
  }catch(error){toast(`Could not build the chart: ${error.message}`);}
}
async function submitQuestion(event) {
  if(event)event.preventDefault();
  if(state.busy)return;
  const question=$("chat-question").value.trim();
  if(!question)return;
  const context=$("copilot-context").value;
  if(context === "local_dataset" && !state.intake){toast("Upload a dataset in Data Workspace first.");return;}
  if(!["local_dataset","general"].includes(context) && !state.ready){toast("First load your frozen research bundle.");return;}
  const payload={question,context,use_local_llm:$("copilot-qwen").checked,
    session_id:state.copilotSessionId,
    order_id:["auto","historical_order"].includes(context) ? $("copilot-order").value.trim() : null,
    scenario_id:context === "headroom" ? ($("copilot-scenario").value || null) : null};
  if(state.intake?.loaded){
    payload.chart_catalog=currentChartCatalog();
    payload.chart_focus=$("copilot-chart-focus").value || null;
    payload.dataset_revision=state.intake.dataset_revision;
  }
  const conversation=state.chatHistory.filter(item => item.context === context
    && item.order_id === payload.order_id && item.scenario_id === payload.scenario_id);
  payload.history = conversation.slice(-4).map(item => ({question:item.question}));
  // The previous resolved source is a routing hint, NOT an authorization or an evidence source.
  payload.last_context = conversation.length ? conversation[conversation.length-1].resolved_context : null;
  state.busy=true;$("chat-send").disabled=true;
  addBubble("user",question);$("chat-question").value="";
  const pending=addBubble("assistant",payload.use_local_llm
    ? "Checking your data, then putting the answer into natural language with local Qwen..."
    : "Checking the selected evidence...");
  try{
    const response=await request("/api/copilot",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    pending.remove();addBubble("assistant",response.answer,response);
    state.copilotSessionId=response.session_id || null;
    if(response.context && sourceDescriptions[response.context]) {
      $("copilot-source-label").textContent=sourceDescriptions[response.context];
      // When a data question is routed from General mode, keep the evidence
      // selector synchronized so the next "why?" retains the dataset scope.
      if (context === "general" && response.context === "local_dataset") {
        $("copilot-context").value = "local_dataset";
        syncCopilotContext();
      }
    }
    state.chatHistory.push({context,question,order_id:payload.order_id,
      scenario_id:payload.scenario_id,resolved_context:response.context});
    state.chatHistory = state.chatHistory.slice(-18);
  }catch(error){pending.remove();addBubble("assistant",`I couldn't complete this request: ${error.message}. No operational action was performed.`);}
  finally{state.busy=false;$("chat-send").disabled=false;}
}
function setupCopilot(){
  setupHistoricalOutcomes();
  $("copilot-context").value="local_dataset";
  $("copilot-context").addEventListener("change",syncCopilotContext);syncCopilotContext();
  $("copilot-chart-focus").addEventListener("change", () => {
    if ($("copilot-chart-focus").value) {$("copilot-context").value="local_dataset"; syncCopilotContext();}
  });
  refreshChartChoices();
  // A visible, opt-in switch prevents the natural-language mode being buried in settings.
  const qwenToggle=$("copilot-qwen").closest(".toggle-line");
  qwenToggle.classList.add("manager-llm-toggle");
  $("chat-form").before(qwenToggle);
  $("chat-new").addEventListener("click",async()=>{
    const oldSession=state.copilotSessionId;
    state.copilotSessionId=null;
    state.chatHistory=[];
    $("chat-messages").innerHTML='<div class="welcome-message"><h2>New conversation</h2><p>Ask about the selected evidence source, or choose General conversation for open-ended questions.</p></div>';
    if(oldSession){
      try {await request("/api/copilot/reset",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({session_id:oldSession})});}
      catch(error){toast("Conversation cleared in browser; local session could not be confirmed cleared.");}
    }
  });
  $("chart-goal-form").addEventListener("submit",event=>{
    event.preventDefault();
    if(!state.intake?.loaded)return toast("Upload a dataset first.");
    const goal=$("chart-goal-question").value.trim();
    if(!goal)return toast("Describe what you want to investigate.");
    $("copilot-context").value="local_dataset";
    syncCopilotContext();
    navigate("copilot");
    $("chat-question").value="Recommend a chart to answer this question: "+goal;
    submitQuestion();
  });
  $("viz-ask-copilot").addEventListener("click",()=>{
    $("copilot-context").value="local_dataset";syncCopilotContext();
    navigate("copilot");$("chat-question").value="What should we prioritize based on this dataset?";
    $("chat-question").focus();
  });
  $("copilot-qwen").addEventListener("change", async () => {
    if (!$("copilot-qwen").checked) return;
    try {
      const result = await request("/api/local-model");
      if (!result.available) {
        $("copilot-qwen").checked = false;
        $("copilot-qwen-help").textContent = `${result.message} Run Ollama with qwen3.5:4b locally.`;
        toast("Local Qwen is not ready. The grounded conversation rules still work.");
      } else {
        $("copilot-qwen-help").textContent = "Qwen is ready. For uploaded datasets, local Qwen can request read-only calculations across every accepted row and bounded record previews; data stays local.";
        toast("Local Qwen conversation enabled. Your data remains on this computer.");
      }
    } catch (error) {
      $("copilot-qwen").checked = false;
      toast(`Local Qwen status unavailable: ${error.message}`);
    }
  });
  $("chat-form").addEventListener("submit",submitQuestion);
  $("chat-question").addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();submitQuestion();}});
  document.querySelectorAll("[data-suggestion]").forEach(el=>el.addEventListener("click",()=>{
    const prompt=el.dataset.suggestion;
    if(prompt.toLowerCase().includes("joint-capacity"))$("copilot-context").value="joint_capacity";
    else if(prompt.toLowerCase().includes("scenario"))$("copilot-context").value="headroom";
    if(prompt.toLowerCase().includes("readiness")||prompt.toLowerCase().includes("real-world"))$("copilot-context").value="readiness";
    syncCopilotContext();$("chat-question").value=prompt;$("chat-question").focus();
  }));
}

async function bootstrap(){
  setupNavigation();setupOrders();setupScenarios();setupCopilot();setupConnections();setupCustomCharts();setupIntake();
  $("drawer-close").addEventListener("click",closeDrawer);
  $("drawer-backdrop").addEventListener("click",closeDrawer);
  try{
    const status=await request("/api/status");renderStatus(status);
    await loadModelSelection();
    const initialDataset=await request("/api/intake");
    renderIntake(initialDataset);
    // New installations can chat without uploading a file, but still need Qwen
    // for open-ended answers. No dataset evidence is silently invented.
    if(!initialDataset.loaded){$("copilot-context").value="general";syncCopilotContext();}
    renderHistoricalOutcomes(await request("/api/historical-outcomes"));
    await loadConnections();
    try { renderModelValidation(await request("/api/model-validation")); }
    catch(error) { renderModelValidation({available:false,error:error.message}); }
    try { renderJointCapacity(await request("/api/joint-capacity")); }
    catch(error) { renderJointCapacity({available:false,error:error.message}); }
    if(!state.ready)return;
    const [overview,scenarios,policies,readiness]=await Promise.all([
      request("/api/overview"),request("/api/scenarios"),request("/api/policies"),request("/api/readiness"),
    ]);
    state.summary=overview.summary;
    state.scenarios=scenarios.items;
    state.policies=policies.items;
    state.readiness=readiness.items;
    renderScenarios();renderPolicies();renderReadiness();await loadOrders();
  }catch(error){toast(`AEGIS startup: ${error.message}`);}
}
document.addEventListener("DOMContentLoaded",bootstrap);
