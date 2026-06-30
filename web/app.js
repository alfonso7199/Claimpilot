// ClaimPilot frontend logic

const $ = (s) => document.querySelector(s);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
};
const icon = (id) => `<svg><use href="#${id}"/></svg>`;
// Escape any model/user text before injecting via innerHTML.
const esc = (s) =>
  String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
  );

const MAX_FILE_MB = 25;
const MAX_FILES = 12;
const ACCEPTED = new Set([
  "txt", "eml", "md", "text", "pdf",
  "png", "jpg", "jpeg", "webp", "gif", "bmp",
  "mp3", "wav", "m4a", "ogg", "oga", "webm", "mp4", "mpga", "flac",
]);

const state = { files: [], example: null, exampleText: "" };
const session = { dossier: "" };

function appendAudit(summary) {
  const audit = document.querySelector(".audit");
  if (!audit) return;
  const ts = new Date().toISOString().slice(0, 19).replace("T", " ");
  const line = el("div");
  line.innerHTML = `<span class="a-time">[${ts}]</span> <span class="a-agent">Reviewer</span>: ${esc(summary)}`;
  audit.appendChild(line);
}

const dropzone = $("#dropzone");
const fileInput = $("#file-input");
const fileList = $("#file-list");
const runBtn = $("#run-btn");
const hint = $("#input-hint");

// ---------- file type icons ----------
function extOf(name) { return (name.toLowerCase().split(".").pop() || ""); }
function extIcon(name) {
  const e = extOf(name);
  if (["mp3", "wav", "m4a", "ogg", "oga", "webm", "mp4", "mpga", "flac"].includes(e)) return "i-mic";
  if (["png", "jpg", "jpeg", "webp", "gif", "bmp"].includes(e)) return "i-image";
  if (e === "pdf") return "i-pdf";
  return "i-doc";
}

// ---------- input handling ----------
function renderFiles() {
  fileList.innerHTML = "";
  state.files.forEach((f, i) => {
    const li = el("li");
    li.innerHTML =
      `<svg class="fl-icon"><use href="#${extIcon(f.name)}"/></svg>` +
      `<span class="fl-name">${esc(f.name)}</span>` +
      `<span class="fl-kind">${(f.size / 1024).toFixed(0)} KB</span>` +
      `<button class="fl-x" title="Remove">&times;</button>`;
    li.querySelector(".fl-x").onclick = () => {
      state.files.splice(i, 1);
      renderFiles();
      updateRun();
    };
    fileList.appendChild(li);
  });
}

function addFiles(list) {
  const warnings = [];
  for (const f of list) {
    const ext = extOf(f.name);
    if (!ACCEPTED.has(ext)) { warnings.push(`${f.name}: unsupported type`); continue; }
    if (f.size > MAX_FILE_MB * 1024 * 1024) { warnings.push(`${f.name}: over ${MAX_FILE_MB} MB`); continue; }
    if (state.files.some((x) => x.name === f.name && x.size === f.size)) continue; // dedupe
    if (state.files.length >= MAX_FILES) { warnings.push(`max ${MAX_FILES} files`); break; }
    state.files.push(f);
  }
  renderFiles();
  updateRun();
  if (warnings.length) { hint.textContent = "Skipped — " + warnings.join("; "); }
}

function updateRun() {
  const has = state.files.length || state.example || $("#text-input").value.trim();
  runBtn.disabled = !has;
  hint.textContent = "";
}

dropzone.onclick = () => fileInput.click();
dropzone.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } };
fileInput.onchange = () => { addFiles(fileInput.files); fileInput.value = ""; };
["dragover", "dragenter"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("drag"); })
);
["dragleave", "drop"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove("drag"); })
);
dropzone.addEventListener("drop", (e) => { if (e.dataTransfer && e.dataTransfer.files) addFiles(e.dataTransfer.files); });
$("#text-input").addEventListener("input", updateRun);

// ---------- examples ----------
async function loadExamples() {
  try {
    const names = await (await fetch("/api/examples")).json();
    const box = $("#example-chips");
    if (!Array.isArray(names)) return;
    names.forEach((n) => {
      const chip = el("button", "chip");
      chip.textContent = n.replace(/_/g, " ");
      chip.onclick = async () => {
        const wasActive = state.example === n;
        document.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
        if (wasActive) { state.example = null; state.exampleText = ""; }
        else {
          chip.classList.add("active");
          state.example = n;
          try {
            const d = await (await fetch("/api/example/" + encodeURIComponent(n))).json();
            state.exampleText = d.text || "";
          } catch (e) { state.exampleText = ""; }
        }
        updateRun();
      };
      box.appendChild(chip);
    });
  } catch (e) { /* examples are optional */ }
}

// ---------- timeline ----------
const STEPS = [
  { key: "evidence", label: "Evidence intake", desc: "Normalizing audio, images, PDFs and text" },
  { key: "intake", label: "Intake", desc: "Extracting structured claim data" },
  { key: "policy", label: "Policy check", desc: "Verifying coverage with cited clauses" },
  { key: "triage", label: "Triage", desc: "Routing decision and confidence" },
  { key: "ready", label: "Claim file ready", desc: "Prepared for human review" },
];
const AGENT_STEP = {
  EvidenceIntake: "evidence", IntakeAgent: "intake", InfoRequestAgent: "intake",
  PolicyAgent: "policy", TriageAgent: "triage", Manager: "ready",
};

function buildTimeline() {
  const ol = $("#timeline");
  ol.innerHTML = "";
  STEPS.forEach((s) => {
    const li = el("li");
    li.dataset.key = s.key;
    li.innerHTML =
      `<span class="tl-dot">${icon("i-check")}</span>` +
      `<div class="tl-label">${s.label}</div>` +
      `<div class="tl-desc">${s.desc}</div>`;
    ol.appendChild(li);
  });
}
function setStep(key, status) {
  const order = STEPS.map((s) => s.key);
  const idx = order.indexOf(key);
  if (idx < 0) return;
  document.querySelectorAll("#timeline li").forEach((li) => {
    const i = order.indexOf(li.dataset.key);
    li.classList.remove("active", "done");
    if (i < idx) li.classList.add("done");
    else if (i === idx) li.classList.add(status === "done" ? "done" : "active");
  });
}
function finishTimeline(upTo) {
  const order = STEPS.map((s) => s.key);
  const idx = order.indexOf(upTo);
  document.querySelectorAll("#timeline li").forEach((li) => {
    const i = order.indexOf(li.dataset.key);
    li.classList.remove("active", "done");
    if (i <= idx) li.classList.add("done");
  });
}

function addEvidence(name, kind) {
  const li = el("li");
  li.innerHTML = `<svg><use href="#${extIcon(name || "")}"/></svg><span>${esc(name)}</span><span class="ev-kind">${esc(kind)}</span>`;
  $("#evidence-list").appendChild(li);
}

// ---------- run ----------
function startJob(fd) {
  $("#input-card").classList.add("hidden");
  buildTimeline();
  $("#evidence-list").innerHTML = "";
  $("#run-card").classList.remove("hidden");
  $("#result-card").classList.add("hidden");
  $("#reset-row").classList.add("hidden");
  $("#run-card").scrollIntoView({ behavior: "smooth", block: "start" });

  (async () => {
    let job;
    try {
      const resp = await fetch("/api/process", { method: "POST", body: fd });
      job = await resp.json();
    } catch (e) {
      return showError("Could not reach the server. Is it running?");
    }
    if (!job || !job.job_id) return showError("The server did not start a job.");

    let done = false;
    const es = new EventSource("/api/events/" + job.job_id);
    es.onmessage = (msg) => {
      let ev;
      try { ev = JSON.parse(msg.data); } catch (e) { return; }
      if (ev.type === "progress") setStep(AGENT_STEP[ev.agent] || "evidence", "active");
      else if (ev.type === "evidence") addEvidence(ev.name, ev.kind);
      else if (ev.type === "note") addEvidence(ev.message, "note");
      else if (ev.type === "result") { done = true; es.close(); session.dossier = ev.dossier || session.dossier; renderResult(ev.data); }
      else if (ev.type === "error") { done = true; es.close(); showError(ev.message); }
    };
    es.onerror = () => {
      es.close();
      if (!done) showError("Lost connection to the server during processing. Please retry.");
    };
  })();
}

runBtn.onclick = () => {
  const fd = new FormData();
  fd.append("text", $("#text-input").value || "");
  if (state.example) fd.append("examples", state.example);
  state.files.forEach((f) => fd.append("files", f, f.name));
  startJob(fd);
};

function showError(message) {
  finishTimeline("evidence");
  const r = $("#result-card");
  r.classList.remove("hidden");
  r.innerHTML = `<div class="panel"><h3>${icon("i-alert")} Could not complete</h3>
    <p class="para">${esc(message)}</p>
    <p class="para muted">Tips: confirm OPENAI_API_KEY is set in .env, that you ran setup_vectorstore.py,
    and that the evidence is readable.</p></div>`;
  $("#reset-row").classList.remove("hidden");
}

// ---------- result rendering ----------
const fmtEUR = (v) => (typeof v === "number" && !isNaN(v) ? "€" + Number(v).toLocaleString("en-US") : "N/A");
const pct = (v) => (v == null || isNaN(Number(v)) ? "—" : (Number(v) * 100).toFixed(0) + "%");
const tags = (arr, cls) => (Array.isArray(arr) && arr.length)
  ? `<div class="tagrow">${arr.map((t) => `<span class="tag ${cls || ""}">${esc(t)}</span>`).join("")}</div>` : "";

const ROUTE = {
  straight_through: "Direct payment (fast track)",
  adjuster: "Assign to adjuster",
  investigation: "Investigation (possible fraud)",
  pending_information: "Pending information",
};
const reasonList = (arr) => (Array.isArray(arr) && arr.length)
  ? `<ul class="next">${arr.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>`
  : `<p class="para muted">—</p>`;

function renderResult(d) {
  const r = $("#result-card");
  r.innerHTML = "";
  r.classList.remove("hidden");
  finishTimeline("ready");

  if (!d || !d.triage) {
    // Defensive: pipeline returned without a triage (should not happen)
    if (d && d.needs_more_info) r.appendChild(gapsPanel(d.intake || {}, d.info_request_email));
    auditPanelInto(r, (d && d.audit_log) || []);
    reevalPanel(r);
    qaPanel(r);
    $("#reset-row").classList.remove("hidden");
    r.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }

  const ix = d.intake || {}, cov = d.coverage || {}, tr = d.triage || {};
  const routeLabel = ROUTE[tr.route] || esc(tr.route || "—");

  // banner
  const banner = el("div", "banner route-" + (tr.route || "unknown"));
  banner.innerHTML =
    `<span class="b-dot"></span>` +
    `<div><div class="b-main">${routeLabel}</div>` +
    `<div class="b-sub">${esc(tr.rationale || "")}</div></div>` +
    `<span class="b-conf">confidence ${pct(tr.confidence)}</span>`;
  r.appendChild(banner);

  if (tr.requires_human_review) {
    r.appendChild(el("div", "review-note", `${icon("i-alert")} Guardrail triggered — requires human review before continuing.`));
  }

  if (d.needs_more_info) r.appendChild(gapsPanel(ix, d.info_request_email));

  // data + coverage row
  const row = el("div", "grid-2");

  const data = el("div", "panel");
  data.innerHTML = `<h3>Claim data ${icon("i-doc")}</h3>
    <dl class="kv">
      <dt>Policy</dt><dd>${esc(ix.policy_number || "N/A")}</dd>
      <dt>Claimant</dt><dd>${esc(ix.claimant_name || "N/A")}</dd>
      <dt>Email</dt><dd>${esc(ix.claimant_email || "N/A")}</dd>
      <dt>Type</dt><dd>${esc(ix.incident_type || "N/A")}</dd>
      <dt>Date</dt><dd>${esc(ix.incident_date || "N/A")}</dd>
      <dt>Location</dt><dd>${esc(ix.location || "N/A")}</dd>
      <dt>Est. amount</dt><dd>${fmtEUR(ix.estimated_amount_eur)}</dd>
    </dl>
    <p class="para">${esc(ix.description || "")}</p>
    ${tags(ix.damages)}
    ${Array.isArray(ix.fraud_indicators) && ix.fraud_indicators.length ? `<p class="para muted" style="margin-top:14px">Fraud indicators</p>${tags(ix.fraud_indicators, "bad")}` : ""}
    ${Array.isArray(ix.missing_fields) && ix.missing_fields.length ? `<p class="para muted" style="margin-top:14px">Information gaps</p>${tags(ix.missing_fields, "warn")}` : ""}`;
  row.appendChild(data);

  const coverage = el("div", "panel");
  const flag = cov.covered
    ? `<span class="cover-flag cover-yes">${icon("i-check")} Covered</span>`
    : `<span class="cover-flag cover-no">${icon("i-alert")} Not covered</span>`;
  coverage.innerHTML = `<h3>Coverage ${icon("i-search")}</h3>
    ${flag}
    <dl class="kv" style="margin-top:14px">
      <dt>Limit</dt><dd>${fmtEUR(cov.limit_eur)}</dd>
      <dt>Deductible</dt><dd>${fmtEUR(cov.deductible_eur)}</dd>
    </dl>
    <p class="para">${esc(cov.reasoning || "")}</p>
    ${Array.isArray(cov.exclusions_triggered) && cov.exclusions_triggered.length ? tags(cov.exclusions_triggered, "warn") : ""}
    ${Array.isArray(cov.caveats) && cov.caveats.length ? `<p class="para muted" style="margin-top:12px">Caveats</p>${tags(cov.caveats, "warn")}` : ""}
    ${(Array.isArray(cov.clause_citations) ? cov.clause_citations : []).map((c) => `<div class="cite"><div class="c-id">${esc(c.clause)}</div><div class="c-quote">${esc(c.quote)}</div></div>`).join("")}`;
  row.appendChild(coverage);
  r.appendChild(row);

  // triage panel
  const triage = el("div", "panel");
  triage.innerHTML = `<h3>Triage ${icon("i-route")}</h3>
    <dl class="kv">
      <dt>Route</dt><dd>${routeLabel}</dd>
      <dt>Est. payout</dt><dd>${fmtEUR(tr.estimated_payout_eur)}</dd>
      <dt>Confidence</dt><dd>${pct(tr.confidence)}</dd>
    </dl>
    <p class="para">${esc(tr.rationale || "")}</p>
    <div class="reasons">
      <div><p class="muted r-h">Reasons to approve</p>${reasonList(tr.accept_reasons)}</div>
      <div><p class="muted r-h">Reasons to decline / hold</p>${reasonList(tr.decline_reasons)}</div>
    </div>
    ${Array.isArray(tr.fraud_flags) && tr.fraud_flags.length ? `<p class="para muted" style="margin-top:14px">Fraud flags</p>${tags(tr.fraud_flags, "bad")}` : ""}`;
  r.appendChild(triage);

  auditPanelInto(r, d.audit_log, d);
  reevalPanel(r);
  qaPanel(r);

  $("#reset-row").classList.remove("hidden");
  r.scrollIntoView({ behavior: "smooth", block: "start" });
}

function gapsPanel(ix, email) {
  const recipient = ix.claimant_email || "";
  const p = el("div", "panel gaps");
  p.innerHTML = `<h3>${icon("i-alert")} Information gaps — automated outreach</h3>
    <p class="para">Some essential fields are missing. ClaimPilot still prepared a provisional
    file (data, coverage and triage below) and drafted a request to collect the missing data automatically.</p>
    ${tags(ix.missing_fields || [], "warn")}
    <p class="para muted" style="margin-top:16px">Auto-drafted request${recipient ? " to " + esc(recipient) : " to the customer"}</p>
    <div class="info-email">${esc(email || "")}</div>
    <div class="actions" style="margin-top:16px">
      <button class="btn-approve btn-send">${icon("i-arrow")} Send request to customer</button>
      <button class="btn-ghost btn-copy2">Copy message</button>
    </div>
    <div class="send-note muted" style="margin-top:12px"></div>`;
  const note = p.querySelector(".send-note");
  const sendBtn = p.querySelector(".btn-send");
  sendBtn.onclick = async () => {
    sendBtn.disabled = true;
    note.style.color = "var(--slate)";
    note.innerHTML = `<span class="spinner"></span> Sending...`;
    try {
      const res = await (await fetch("/api/outreach", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ recipient: recipient || "unknown@customer", message: email || "" }),
      })).json();
      note.style.color = "var(--green)";
      note.textContent = `Request sent to ${res.recipient} · saved to ${res.file}. The claim will resume automatically once the customer replies.`;
      const audit = document.querySelector(".audit");
      if (audit) {
        const line = el("div");
        line.innerHTML = `<span class="a-time">[${esc(res.timestamp)}]</span> <span class="a-agent">Outreach</span>: request sent to ${esc(res.recipient)} (${esc(res.file)})`;
        audit.appendChild(line);
      }
    } catch (e) {
      note.style.color = "var(--coral)";
      note.textContent = "Could not send the request. Please retry.";
      sendBtn.disabled = false;
    }
  };
  p.querySelector(".btn-copy2").onclick = () => navigator.clipboard && navigator.clipboard.writeText(email || "");
  return p;
}

function auditPanelInto(r, log, full) {
  const p = el("div", "panel");
  let html = `<h3>Audit trail ${icon("i-shield")}</h3><div class="audit">` +
    (Array.isArray(log) ? log : []).map((e) =>
      `<div><span class="a-time">[${esc(e.timestamp)}]</span> <span class="a-agent">${esc(e.agent)}</span>: ${esc(e.summary)}</div>`
    ).join("") +
    `</div>`;
  if (full) {
    const cur = (full.triage && full.triage.route) || "";
    const opts = Object.keys(ROUTE)
      .map((k) => `<option value="${k}"${k === cur ? " selected" : ""}>${ROUTE[k]}</option>`)
      .join("");
    html += `<div class="override">
        <label class="ov-label">Decision route
          <select class="ov-route">${opts}</select>
        </label>
        <textarea class="ov-note" rows="2" placeholder="Reviewer note (optional) — recorded in the audit trail"></textarea>
      </div>
      <div class="actions" style="margin-top:14px">
        <button class="btn-approve">${icon("i-check")} Approve</button>
        <button class="btn-reject">Reject</button>
        <button class="btn-ghost btn-dl">${icon("i-download")} Download JSON</button>
      </div><div class="decision-made muted" style="margin-top:14px"></div>`;
  }
  p.innerHTML = html;
  if (full) {
    const note = p.querySelector(".decision-made");
    const approveBtn = p.querySelector(".btn-approve");
    const rejectBtn = p.querySelector(".btn-reject");
    const routeSel = p.querySelector(".ov-route");
    const noteEl = p.querySelector(".ov-note");

    async function finalize(decision) {
      approveBtn.disabled = rejectBtn.disabled = true;
      note.style.color = "var(--slate)";
      note.innerHTML = `<span class="spinner"></span> Triggering downstream action...`;
      const chosenRoute = routeSel ? routeSel.value : (full.triage && full.triage.route);
      const reviewerNote = noteEl ? noteEl.value.trim() : "";
      const overridden = full.triage && chosenRoute !== full.triage.route;
      const triage = Object.assign({}, full.triage, { route: chosenRoute });
      try {
        const fin = await (await fetch("/api/finalize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision, intake: full.intake, coverage: full.coverage, triage, note: reviewerNote }),
        })).json();
        if (fin.error) {
          note.textContent = "Could not finalize: " + fin.error;
          note.style.color = "var(--coral)";
          approveBtn.disabled = rejectBtn.disabled = false;
          return;
        }
        note.textContent = "";
        appendAudit(
          `${decision}` +
          (overridden ? ` · route overridden to ${ROUTE[chosenRoute] || chosenRoute}` : "") +
          (reviewerNote ? ` · note: ${reviewerNote}` : "")
        );
        renderOutcome(decision, fin, r, full, { approveBtn, rejectBtn, note });
      } catch (e) {
        note.textContent = "Could not finalize. Please retry.";
        note.style.color = "var(--coral)";
        approveBtn.disabled = rejectBtn.disabled = false;
      }
    }
    approveBtn.onclick = () => finalize("approved");
    rejectBtn.onclick = () => finalize("rejected");
    p.querySelector(".btn-dl").onclick = () => {
      const blob = new Blob([JSON.stringify(full, null, 2)], { type: "application/json" });
      const a = el("a"); a.href = URL.createObjectURL(blob); a.download = "claim_file.json"; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    };
  }
  r.appendChild(p);
}

const ACTION_LABEL = {
  payment_scheduled: "Payment scheduled",
  assigned_adjuster: "Assigned to adjuster",
  investigation_opened: "Investigation opened",
  claim_declined: "Claim declined",
};

function renderOutcome(decision, fin, r, full, controls) {
  full.decision = decision;
  full.finalization = fin;
  const ok = decision === "approved";
  const p = el("div", "panel");
  p.innerHTML =
    `<h3>Outcome ${icon(ok ? "i-check" : "i-alert")}</h3>` +
    `<div class="cover-flag ${ok ? "cover-yes" : "cover-no"}">${icon(ok ? "i-check" : "i-alert")} ` +
      `${esc(ACTION_LABEL[fin.action] || fin.action || "")} — ${esc(fin.action_summary || "")}</div>` +
    `<p class="para muted" style="margin-top:16px">Customer communication</p>` +
    `<div class="info-email">${esc(fin.customer_message || "")}</div>` +
    (Array.isArray(fin.next_steps) && fin.next_steps.length
      ? `<p class="para muted" style="margin-top:16px">Next steps</p>` +
        `<ul class="next">${fin.next_steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>`
      : "") +
    `<div class="actions" style="margin-top:18px">
        <button class="btn-ghost btn-copy">Copy message</button>
        <button class="btn-ghost btn-reopen">${icon("i-arrow")} Reopen for review</button>
     </div>`;
  p.querySelector(".btn-copy").onclick = () => navigator.clipboard && navigator.clipboard.writeText(fin.customer_message || "");
  p.querySelector(".btn-reopen").onclick = () => {
    p.remove();
    if (controls) {
      controls.approveBtn.disabled = false;
      controls.rejectBtn.disabled = false;
      controls.note.textContent = "";
    }
    appendAudit("case reopened for review");
  };
  r.appendChild(p);
  p.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ---------- re-evaluate with more info ----------
function reevalPanel(r) {
  const p = el("div", "panel");
  p.innerHTML = `<h3>${icon("i-upload")} Add information &amp; re-evaluate</h3>
    <p class="para muted">Got the missing data or new evidence (e.g. the customer replied)? Add it here and ClaimPilot re-runs the full assessment, merged with the current file.</p>
    <textarea class="re-text" rows="3" placeholder="e.g. Policy number is AUTO-2026-00733; incident date 2026-06-09"></textarea>
    <div class="actions" style="margin-top:12px">
      <label class="btn-ghost re-file-label">${icon("i-upload")} Add files</label>
      <input type="file" class="re-files" multiple hidden>
      <span class="re-fname muted"></span>
      <button class="btn-approve re-run">${icon("i-arrow")} Re-evaluate</button>
    </div>`;
  const fileInputR = p.querySelector(".re-files");
  const fname = p.querySelector(".re-fname");
  let extra = [];
  p.querySelector(".re-file-label").onclick = () => fileInputR.click();
  fileInputR.onchange = () => { extra = Array.from(fileInputR.files); fname.textContent = extra.map((f) => f.name).join(", "); };
  p.querySelector(".re-run").onclick = () => {
    const txt = p.querySelector(".re-text").value.trim();
    if (!txt && !extra.length) { fname.textContent = "Add a note or a file first."; return; }
    const fd = new FormData();
    const combined = (session.dossier || "") +
      "\n\n=== ADDITIONAL INFORMATION (provided by reviewer/customer) ===\n" + txt;
    fd.append("text", combined);
    extra.forEach((f) => fd.append("files", f, f.name));
    startJob(fd);
  };
  r.appendChild(p);
}

// ---------- Q&A over the claim ----------
function qaPanel(r) {
  const p = el("div", "panel");
  p.innerHTML = `<h3>${icon("i-search")} Ask about this claim</h3>
    <div class="qa-thread"></div>
    <div class="qa-input">
      <input class="qa-q" placeholder="e.g. Is theft without a police report covered?">
      <button class="btn-approve qa-send">Ask</button>
    </div>`;
  const thread = p.querySelector(".qa-thread");
  const input = p.querySelector(".qa-q");
  const sendBtn = p.querySelector(".qa-send");
  async function ask() {
    const q = input.value.trim();
    if (!q) return;
    input.value = "";
    const qEl = el("div", "qa-msg qa-user"); qEl.textContent = q; thread.appendChild(qEl);
    const aEl = el("div", "qa-msg qa-bot"); aEl.innerHTML = `<span class="spinner"></span> Thinking...`; thread.appendChild(aEl);
    aEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
    sendBtn.disabled = true;
    try {
      const res = await (await fetch("/api/ask", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, dossier: session.dossier }),
      })).json();
      aEl.textContent = res.error ? ("Could not answer: " + res.error) : (res.answer || "No answer.");
    } catch (e) { aEl.textContent = "Could not answer. Please retry."; }
    sendBtn.disabled = false;
  }
  sendBtn.onclick = ask;
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") ask(); });
  r.appendChild(p);
}

// ---------- reset ----------
$("#reset-btn").onclick = () => {
  state.files = []; state.example = null; state.exampleText = "";
  fileInput.value = ""; $("#text-input").value = "";
  renderFiles();
  document.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
  $("#result-card").classList.add("hidden");
  $("#run-card").classList.add("hidden");
  $("#reset-row").classList.add("hidden");
  $("#input-card").classList.remove("hidden");
  updateRun();
  window.scrollTo({ top: 0, behavior: "smooth" });
};

loadExamples();

/* ============================================================
   Bring-your-own OpenAI key (for public / self-hosted demo).
   Adds a top-bar button; stores the key in localStorage and
   sends it as X-OpenAI-Key on every /api/ request. The server
   uses it if present, otherwise falls back to its .env key.
   ============================================================ */
(function () {
  var KEY = "OPENAI_KEY";
  var _fetch = window.fetch.bind(window);
  window.fetch = function (url, opts) {
    opts = opts || {};
    var k = localStorage.getItem(KEY);
    if (k && typeof url === "string" && url.indexOf("/api/") === 0) {
      opts = Object.assign({}, opts);
      opts.headers = Object.assign({}, opts.headers || {}, { "X-OpenAI-Key": k });
    }
    return _fetch(url, opts);
  };

  var ACC = "var(--accent, var(--teal, var(--accent-deep, #2563eb)))";
  var CARD = "var(--card, var(--panel, var(--paper, #ffffff)))";
  var INK = "var(--ink, #1a1a1a)";
  var LINE = "var(--line, #dddddd)";
  var MUTED = "var(--muted, var(--slate, var(--muted-ink, #888888)))";
  var css =
    ".kk-btn{display:inline-flex;align-items:center;gap:7px;border:1px solid " + LINE + ";background:" + CARD + ";color:" + INK + ";font:inherit;font-size:12.5px;font-weight:600;padding:7px 12px;border-radius:999px;cursor:pointer}" +
    ".kk-btn:hover{border-color:" + ACC + "}" +
    ".kk-dot{width:8px;height:8px;border-radius:50%;background:#d9a33a}" +
    ".kk-dot.on{background:#2aa676}" +
    ".kk-ov{position:fixed;inset:0;background:rgba(10,15,20,.55);display:grid;place-items:center;z-index:99999;padding:20px}" +
    ".kk-card{background:" + CARD + ";color:" + INK + ";border:1px solid " + LINE + ";border-radius:14px;max-width:440px;width:100%;padding:24px;box-shadow:0 30px 80px -30px rgba(0,0,0,.5);font-family:inherit}" +
    ".kk-card h4{margin:0 0 6px;font-size:18px}" +
    ".kk-card p{margin:0 0 14px;font-size:13px;color:" + MUTED + "}" +
    ".kk-card input{width:100%;box-sizing:border-box;border:1px solid " + LINE + ";border-radius:10px;padding:11px 13px;font:inherit;font-size:14px;background:" + CARD + ";color:" + INK + "}" +
    ".kk-card input:focus{outline:none;border-color:" + ACC + "}" +
    ".kk-row{display:flex;gap:10px;margin-top:14px}" +
    ".kk-save{flex:1;border:none;cursor:pointer;background:" + ACC + ";color:#fff;border-radius:10px;padding:11px;font:inherit;font-weight:600}" +
    ".kk-clear{border:1px solid " + LINE + ";background:transparent;color:" + INK + ";border-radius:10px;padding:11px 16px;cursor:pointer;font:inherit;font-weight:600}" +
    ".kk-note{margin-top:12px;font-size:11.5px;color:" + MUTED + ";line-height:1.5}";
  var st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);

  var btn = document.createElement("button");
  btn.className = "kk-btn";
  btn.type = "button";
  function refresh() {
    var has = !!localStorage.getItem(KEY);
    btn.innerHTML = '<span class="kk-dot' + (has ? " on" : "") + '"></span>' + (has ? "API key set" : "Add API key");
  }
  function mount() {
    var h = document.querySelector(".nav-inner") || document.querySelector(".topbar");
    if (!h) {
      btn.style.position = "fixed"; btn.style.top = "14px"; btn.style.right = "16px"; btn.style.zIndex = "9998";
      document.body.appendChild(btn);
    } else {
      h.appendChild(btn);
    }
    refresh();
  }
  btn.onclick = function () {
    var ov = document.createElement("div"); ov.className = "kk-ov";
    var cur = localStorage.getItem(KEY) || "";
    var card = document.createElement("div"); card.className = "kk-card";
    card.innerHTML =
      "<h4>OpenAI API key</h4>" +
      "<p>Use your own key to run this demo. It is stored only in this browser and sent to your local server with each request.</p>" +
      '<input type="password" class="kk-in" placeholder="sk-..." autocomplete="off">' +
      '<div class="kk-row"><button class="kk-save" type="button">Save</button><button class="kk-clear" type="button">Clear</button></div>' +
      '<div class="kk-note">Stored in your browser (localStorage) on this device only. Never commit your key to the repo. If you leave this empty, the server uses its own .env key.</div>';
    ov.appendChild(card);
    card.querySelector(".kk-in").value = cur;
    ov.addEventListener("click", function (e) { if (e.target === ov) ov.remove(); });
    card.querySelector(".kk-save").onclick = function () {
      var v = card.querySelector(".kk-in").value.trim();
      if (v) localStorage.setItem(KEY, v); else localStorage.removeItem(KEY);
      refresh(); ov.remove();
    };
    card.querySelector(".kk-clear").onclick = function () { localStorage.removeItem(KEY); refresh(); ov.remove(); };
    document.body.appendChild(ov);
    card.querySelector(".kk-in").focus();
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
})();
