/* Dashboard page logic */

async function loadDashboard() {
  const el = $("#dashboard-content");
  try {
    const d = await api.dashboard();
    let sourceRows = "";
    if (d.sources && d.sources.length) {
      sourceRows = d.sources.map(s => `
        <tr>
          <td>${s.source}</td>
          <td>${s.total_picks}</td>
          <td>${s.wins}W-${s.losses}L</td>
          <td>${pct(s.win_rate)}</td>
          <td class="${roiClass(s.roi)}">${roiStr(s.roi)}</td>
        </tr>
      `).join("");
    }

    el.innerHTML = `
      <div class="stat-grid">
        <div class="stat-card">
          <div class="label">Pending Signals</div>
          <div class="value text-accent">${d.pending_count}</div>
        </div>
        <div class="stat-card">
          <div class="label">Today's Signals</div>
          <div class="value">${d.today_count}</div>
        </div>
        <div class="stat-card">
          <div class="label">Tracked Sources</div>
          <div class="value">${d.source_count}</div>
        </div>
        <div class="stat-card">
          <div class="label">Overall Win Rate</div>
          <div class="value ${d.overall_win_rate >= 0.5 ? 'text-green' : 'text-red'}">${pct(d.overall_win_rate)}</div>
        </div>
      </div>
      ${d.sources && d.sources.length ? `
      <h2>Source Summary</h2>
      <table>
        <thead><tr><th>Source</th><th>Picks</th><th>Record</th><th>Win Rate</th><th>ROI</th></tr></thead>
        <tbody>${sourceRows}</tbody>
      </table>
      ` : '<div class="empty-state">No source data yet. Ingest and grade signals to get started.</div>'}
    `;
  } catch (e) {
    el.innerHTML = `<div class="empty-state">Could not load dashboard: ${e.message}</div>`;
  }
}

// Auto-refresh every 60s
let _dashInterval;
function startDashboard() {
  loadDashboard();
  _dashInterval = setInterval(loadDashboard, 60000);
}
function stopDashboard() {
  clearInterval(_dashInterval);
}
