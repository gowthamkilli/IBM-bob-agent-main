/**
 * Witness Dashboard — app.js
 * Reads run JSON from dashboard/data/run-<id>.json
 * Replays lane results with simulated timing.
 * Zero backend, zero network calls, zero agent invocations.
 * Works with file:// protocol.
 */

(function () {
  "use strict";

  // ── Bootstrap ────────────────────────────────────────────────────────────

  const params = new URLSearchParams(window.location.search);
  const runId = params.get("run");

  if (!runId) {
    showError("No run ID specified. Add ?run=<id> to the URL.");
    return;
  }

  const dataPath = `data/run-${runId}.json`;

  // file:// fetch workaround: use XMLHttpRequest
  loadJson(dataPath, function (err, data) {
    if (err) {
      showError(`Could not load ${dataPath}: ${err}`);
      return;
    }
    render(data);
  });

  // ── Data loading ─────────────────────────────────────────────────────────

  function loadJson(path, cb) {
    const xhr = new XMLHttpRequest();
    xhr.open("GET", path, true);
    xhr.onload = function () {
      if (xhr.status === 0 || xhr.status === 200) {
        try {
          cb(null, JSON.parse(xhr.responseText));
        } catch (e) {
          cb("JSON parse error: " + e.message);
        }
      } else {
        cb("HTTP " + xhr.status);
      }
    };
    xhr.onerror = function () { cb("Network error"); };
    xhr.send();
  }

  // ── Render ───────────────────────────────────────────────────────────────

  function render(run) {
    renderMeta(run);
    renderLedger(run.ledger || []);
    renderBranches(run);
    replayLanes(run.lanes || [], run);
    renderFindings(run.findings || {});
    renderBench(run.bench || []);
  }

  function renderMeta(run) {
    const el = document.getElementById("run-meta");
    if (!el) return;
    el.innerHTML =
      `Run <strong>${esc(run.run_id)}</strong> · ` +
      `Mode: <strong>${esc(run.mode)}</strong> · ` +
      `Head: <code>${esc(run.head_sha || "?")}</code>` +
      (run.base_sha ? ` · Base: <code>${esc(run.base_sha)}</code>` : "") +
      (run.branches && run.branches.length
        ? ` · Branches: ${run.branches.map(b => `<code>${esc(b)}</code>`).join(", ")}`
        : "");
  }

  function renderLedger(ledger) {
    const tbody = document.getElementById("ledger-body");
    if (!tbody) return;
    if (!ledger.length) {
      tbody.innerHTML = '<tr><td colspan="4" style="color:var(--muted)">No ledger data</td></tr>';
      return;
    }
    tbody.innerHTML = ledger.map(g => `
      <tr>
        <td><strong>${esc(g.id)}</strong></td>
        <td>${esc(g.statement)}</td>
        <td>${(g.provenance || []).map(p => `<code>${esc(p)}</code>`).join("<br>")}</td>
        <td>${g.covered_by_test
          ? `<span class="badge badge-covered">✓ ${esc(g.covered_by_test)}</span>`
          : '<span class="badge badge-uncovered">✗ uncovered</span>'}</td>
      </tr>`).join("");
  }

  function renderBranches(run) {
    const el = document.getElementById("branches-list");
    if (!el) return;
    const branches = run.branches || [];
    if (!branches.length) {
      el.innerHTML = '<p style="color:var(--muted)">No branch data</p>';
      return;
    }
    el.innerHTML = branches.map(b =>
      `<div style="display:inline-block;margin:4px;padding:6px 12px;border:1px solid var(--border);border-radius:4px;font-family:monospace">${esc(b)}</div>`
    ).join("");
  }

  function replayLanes(lanes, run) {
    const container = document.getElementById("lanes-container");
    if (!container) return;
    container.innerHTML = "";

    // Create all cards immediately in pending state
    const cards = lanes.map((lane, i) => {
      const card = document.createElement("div");
      card.className = "lane-card";
      card.id = `lane-card-${lane.lane_id}`;
      card.innerHTML = `
        <h4>Lane ${esc(lane.lane_id)}</h4>
        <div class="lane-status">Candidate: ${esc(lane.candidate_id)}</div>
        <span class="badge badge-inconclusive">⏳ running…</span>`;
      container.appendChild(card);
      return { card, lane };
    });

    // Replay with simulated timing (300ms per lane, staggered)
    cards.forEach(({ card, lane }, i) => {
      setTimeout(() => {
        const verdictClass = `verdict-${(lane.verdict || "inconclusive").toLowerCase()}`;
        const badgeClass = `badge-${(lane.verdict || "inconclusive").toLowerCase()}`;
        card.className = `lane-card ${verdictClass}`;
        card.innerHTML = `
          <h4>Lane ${esc(lane.lane_id)}</h4>
          <div class="lane-status">Candidate: ${esc(lane.candidate_id)}</div>
          <span class="badge ${badgeClass}">${esc(lane.verdict || "?")}</span>
          ${lane.verdict === "PROVEN" ? `<div style="margin-top:8px;font-size:0.8rem">
            <strong>base:</strong> ${verdictBadge(lane.base_result)}&nbsp;
            <strong>head:</strong> ${verdictBadge(lane.head_result)}
          </div>` : ""}
          <div style="font-size:0.75rem;color:var(--muted);margin-top:6px">${esc(lane.death_note || "")}</div>`;

        // Populate split view if this is the winning lane
        if (lane.verdict === "PROVEN") {
          populateSplitView(lane, run);
        }
      }, (i + 1) * 350);
    });
  }

  function populateSplitView(lane, run) {
    const baseEl = document.getElementById("split-base-output");
    const headEl = document.getElementById("split-head-output");
    if (baseEl) baseEl.textContent = `Result: ${lane.base_result}\n\n${lane.stderr_excerpt || "(no output)"}`;
    if (headEl) headEl.textContent = `Result: ${lane.head_result}\n\n${lane.stderr_excerpt || "(no output)"}`;
  }

  function renderFindings(findings) {
    renderDefeated(findings.defeated || []);
    renderUndefended(findings.undefended || []);
  }

  function renderDefeated(defeated) {
    const el = document.getElementById("findings-defeated");
    if (!el) return;
    if (!defeated.length) {
      el.innerHTML = '<p style="color:var(--pass)">✅ No guarantees defeated.</p>';
      return;
    }
    el.innerHTML = defeated.map(f => `
      <div class="finding-card defeated">
        <h4>❌ DEFEATED — Guarantee ${esc(f.guarantee_id)}</h4>
        <dl>
          <dt>Guarantee</dt><dd>${esc(f.statement || "")}</dd>
          <dt>Where stated</dt><dd>${(f.provenance || []).map(p => `<code>${esc(p)}</code>`).join(", ")}</dd>
          <dt>Why it exists</dt><dd>${esc(f.why || "")}</dd>
          <dt>What defeats it</dt><dd>${esc(f.claim || "")}</dd>
          <dt>Proof test</dt><dd><code>${esc(f.test_path || "")}</code></dd>
          <dt>Reproduce</dt><dd><code>python -m pytest ${esc(f.test_path || "")} -x</code></dd>
        </dl>
      </div>`).join("");
  }

  function renderUndefended(undefended) {
    const el = document.getElementById("findings-undefended");
    if (!el) return;
    if (!undefended.length) return;
    el.innerHTML = "<h3>⚠️ UNDEFENDED</h3>" + undefended.map(f => `
      <div class="finding-card undefended">
        <h4>Guarantee ${esc(f.guarantee_id)}</h4>
        <dl>
          <dt>Guarantee</dt><dd>${esc(f.statement || "")}</dd>
          <dt>Provenance</dt><dd>${(f.provenance || []).map(p => `<code>${esc(p)}</code>`).join(", ")}</dd>
          <dt>Coverage</dt><dd>No test in this suite covers this guarantee.</dd>
        </dl>
      </div>`).join("");
  }

  function renderBench(bench) {
    const tbody = document.getElementById("bench-body");
    if (!tbody || !bench.length) return;
    tbody.innerHTML = bench.map(row => `
      <tr>
        <td>${esc(row.case)}</td>
        <td>${esc(row.guarantee)}</td>
        <td>${esc(row.green_alone)}</td>
        <td>${esc(row.textual_conflict)}</td>
        <td>${esc(row.suite_caught)}</td>
        <td><span class="badge badge-${(row.witness_verdict||"").toLowerCase()}">${esc(row.witness_verdict)}</span></td>
        <td><code>${esc(row.proof_test)}</code></td>
      </tr>`).join("");
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  function verdictBadge(v) {
    if (!v) return "";
    const cls = v === "PASS" ? "badge-pass" : "badge-fail";
    return `<span class="badge ${cls}">${esc(v)}</span>`;
  }

  function esc(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function showError(msg) {
    document.body.innerHTML = `
      <div style="padding:40px;font-family:system-ui;color:#b31d28">
        <h2>Witness Dashboard Error</h2>
        <p>${esc(msg)}</p>
        <p style="color:#57606a;margin-top:16px">
          Usage: open <code>index.html?run=&lt;run-id&gt;</code><br>
          Example: <code>index.html?run=20260925-001</code>
        </p>
      </div>`;
  }
})();
