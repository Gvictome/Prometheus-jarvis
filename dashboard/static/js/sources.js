/* Sources page logic */

async function loadSources() {
  const el = $("#sources-content");
  try {
    const sources = await api.sources();
    if (!sources.length) {
      el.innerHTML = '<div class="empty-state">No source data yet. Ingest and grade picks first.</div>';
      return;
    }

    el.innerHTML = sources.map((s, i) => `
      <div class="card">
        <div class="card-header">
          <span class="card-title">#${i + 1} ${s.source}</span>
          ${reliabilityBadge(s.reliability || 0)}
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:0.75rem;margin-top:0.5rem">
          <div>
            <div class="text-muted" style="font-size:0.75rem">RECORD</div>
            <div>${s.wins}W-${s.losses}L${s.pushes ? "-" + s.pushes + "P" : ""} / ${s.total_picks}</div>
          </div>
          <div>
            <div class="text-muted" style="font-size:0.75rem">WIN RATE</div>
            <div class="${s.win_rate >= 0.5 ? 'text-green' : 'text-red'}">${pct(s.win_rate)}</div>
          </div>
          <div>
            <div class="text-muted" style="font-size:0.75rem">ROI (ALL)</div>
            <div class="${roiClass(s.roi)}">${roiStr(s.roi)}</div>
          </div>
          <div>
            <div class="text-muted" style="font-size:0.75rem">ROI (30D)</div>
            <div class="${roiClass(s.roi_30d)}">${roiStr(s.roi_30d)}</div>
          </div>
          <div>
            <div class="text-muted" style="font-size:0.75rem">COMPOSITE</div>
            <div>${Math.round((s.composite_score || 0) * 100)}</div>
          </div>
        </div>
      </div>
    `).join("");
  } catch (e) {
    el.innerHTML = `<div class="empty-state text-red">Error: ${e.message}</div>`;
  }
}
