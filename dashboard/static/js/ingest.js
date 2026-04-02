/* Ingest page logic */

async function handleIngest(e) {
  e.preventDefault();
  const source = $("#ingest-source").value;
  const text = $("#ingest-text").value.trim();
  const resultEl = $("#ingest-result");
  const btn = $("#ingest-btn");

  if (!text) {
    resultEl.innerHTML = '<div class="empty-state">Enter signal text first.</div>';
    return;
  }

  btn.disabled = true;
  btn.textContent = "Ingesting...";

  try {
    const data = await api.ingest(source, text);
    let parsedHtml = "";
    if (data.parsed && data.parsed.length) {
      parsedHtml = data.parsed.map((s, i) => `
        <tr>
          <td>${data.signal_ids[i] || "-"}</td>
          <td>${s.team_or_player || "?"}</td>
          <td>${s.market || "ML"}</td>
          <td>${s.line || "-"}</td>
          <td>${oddsLabel(s.odds, s.odds_decimal)}</td>
        </tr>
      `).join("");
    }

    resultEl.innerHTML = `
      <div class="card mt-2">
        <div class="card-header">
          <span class="card-title text-green">Ingested ${data.signals_stored} signal(s)</span>
          <span class="text-muted">raw id: ${data.raw_id}</span>
        </div>
        ${data.parsed && data.parsed.length ? `
        <table class="mt-1">
          <thead><tr><th>ID</th><th>Team/Player</th><th>Market</th><th>Line</th><th>Odds</th></tr></thead>
          <tbody>${parsedHtml}</tbody>
        </table>
        ` : '<div class="text-muted mt-1">Raw message stored, but no picks could be parsed.</div>'}
      </div>
    `;
    $("#ingest-text").value = "";
  } catch (e) {
    resultEl.innerHTML = `<div class="empty-state text-red">Error: ${e.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Ingest";
  }
}
