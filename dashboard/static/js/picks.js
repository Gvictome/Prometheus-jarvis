/* Picks page logic */

async function loadPicks() {
  const straightsEl = $("#straights-content");
  const parlaysEl = $("#parlays-content");

  try {
    const [straights, parlays] = await Promise.all([
      api.straights(),
      api.parlays(),
    ]);

    // Straights
    if (straights.length) {
      straightsEl.innerHTML = straights.map((p, i) => `
        <div class="card">
          <div class="card-header">
            <span class="card-title">${i + 1}. ${p.team_or_player || "Unknown"}</span>
            <span class="text-muted">${p.source}</span>
          </div>
          <div style="display:flex;gap:1.5rem;flex-wrap:wrap;font-size:0.9rem;color:var(--text-muted)">
            <span>${p.market || "ML"}${p.line ? " " + p.line : ""}</span>
            <span>${oddsLabel(p.odds, p.odds_decimal)}</span>
            <span>WR: ${pct(p.source_win_rate)}</span>
            <span class="${roiClass(p.source_roi)}">ROI: ${roiStr(p.source_roi)}</span>
          </div>
          <div class="mt-1">
            <div style="display:flex;align-items:center;gap:0.5rem">
              <span style="font-size:0.8rem;color:var(--text-muted)">${Math.round(p.confidence_score * 100)}%</span>
              ${confBar(p.confidence_score)}
            </div>
          </div>
        </div>
      `).join("");
    } else {
      straightsEl.innerHTML = '<div class="empty-state">No qualified straight bets. Need more graded picks to rank sources.</div>';
    }

    // Parlays
    if (parlays.length) {
      parlaysEl.innerHTML = parlays.map((p, i) => {
        const legsHtml = p.legs.map(l => `
          <div class="parlay-leg">${l.team_or_player || "?"} ${l.market || "ML"}${l.line ? " " + l.line : ""} (${oddsLabel(l.odds, l.odds_decimal)}) — ${l.source}</div>
        `).join("");
        return `
          <div class="card">
            <div class="card-header">
              <span class="card-title">Parlay ${i + 1} (${p.num_legs} legs)</span>
              <span class="text-accent">${p.combined_odds_american}</span>
            </div>
            <div class="parlay-legs">${legsHtml}</div>
            <div class="mt-1 text-muted" style="font-size:0.85rem">Est. probability: ${pct(p.est_hit_probability)}</div>
          </div>
        `;
      }).join("");
    } else {
      parlaysEl.innerHTML = '<div class="empty-state">No qualifying parlays. Check source performance or ingest more signals.</div>';
    }
  } catch (e) {
    straightsEl.innerHTML = `<div class="empty-state text-red">Error: ${e.message}</div>`;
    parlaysEl.innerHTML = "";
  }
}
