/* Grading page logic */

async function loadPending() {
  const el = $("#pending-content");
  try {
    const pending = await api.pending();
    if (!pending.length) {
      el.innerHTML = '<div class="empty-state">No pending signals to grade.</div>';
      return;
    }
    el.innerHTML = `
      <table>
        <thead><tr><th>ID</th><th>Team/Player</th><th>Market</th><th>Odds</th><th>Source</th><th>Created</th><th>Actions</th></tr></thead>
        <tbody>
          ${pending.map(s => `
            <tr id="row-${s.id}">
              <td>${s.id}</td>
              <td>${s.team_or_player || "?"}</td>
              <td>${s.market || "ML"}${s.line ? " " + s.line : ""}</td>
              <td>${oddsLabel(s.odds, s.odds_decimal)}</td>
              <td>${s.source}</td>
              <td>${(s.created_at || "").slice(0, 16)}</td>
              <td>
                <div class="btn-group">
                  <button class="btn btn-win" onclick="gradeSignal(${s.id},'win')">W</button>
                  <button class="btn btn-loss" onclick="gradeSignal(${s.id},'loss')">L</button>
                  <button class="btn btn-push" onclick="gradeSignal(${s.id},'push')">P</button>
                  <button class="btn btn-void" onclick="gradeSignal(${s.id},'void')">V</button>
                </div>
              </td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  } catch (e) {
    el.innerHTML = `<div class="empty-state text-red">Error: ${e.message}</div>`;
  }
}

async function gradeSignal(id, status) {
  const row = document.getElementById(`row-${id}`);
  const btns = row.querySelectorAll("button");
  btns.forEach(b => b.disabled = true);

  try {
    await api.grade(id, status);
    row.style.opacity = "0.3";
    row.querySelector("td:last-child").innerHTML = `<span class="badge badge-${status === 'win' ? 'reliable' : status === 'loss' ? '' : 'developing'}">${status.toUpperCase()}</span>`;
  } catch (e) {
    alert("Grade failed: " + e.message);
    btns.forEach(b => b.disabled = false);
  }
}

async function loadResults() {
  const date = $("#results-date").value;
  const el = $("#results-content");
  if (!date) return;

  try {
    const results = await api.results(date);
    if (!results.length) {
      el.innerHTML = `<div class="empty-state">No graded results for ${date}.</div>`;
      return;
    }

    const wins = results.filter(r => r.status === "win").length;
    const losses = results.filter(r => r.status === "loss").length;
    const pushes = results.filter(r => r.status === "push").length;

    el.innerHTML = `
      <div class="mb-1 text-muted">${wins}W ${losses}L ${pushes}P</div>
      <table>
        <thead><tr><th>Status</th><th>Team/Player</th><th>Market</th><th>Odds</th><th>Source</th></tr></thead>
        <tbody>
          ${results.map(r => {
            const icon = {win:"W",loss:"L",push:"P",void:"V"}[r.status] || "?";
            const cls = r.status === "win" ? "text-green" : r.status === "loss" ? "text-red" : "text-yellow";
            return `<tr>
              <td class="${cls}">[${icon}]</td>
              <td>${r.team_or_player || "?"}</td>
              <td>${r.market || "ML"}</td>
              <td>${r.odds || "n/a"}</td>
              <td>${r.source || "?"}</td>
            </tr>`;
          }).join("")}
        </tbody>
      </table>
    `;
  } catch (e) {
    el.innerHTML = `<div class="empty-state text-red">Error: ${e.message}</div>`;
  }
}
