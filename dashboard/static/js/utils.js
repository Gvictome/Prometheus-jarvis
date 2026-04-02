/* Shared formatters and helpers */

function pct(val) {
  return (val * 100).toFixed(1) + "%";
}

function roiStr(val) {
  const s = val.toFixed(1) + "%";
  return val >= 0 ? "+" + s : s;
}

function roiClass(val) {
  return val >= 0 ? "text-green" : "text-red";
}

function oddsLabel(odds, dec) {
  if (odds) return odds;
  if (dec) {
    if (dec >= 2.0) return "+" + Math.round((dec - 1) * 100);
    return String(Math.round(-100 / (dec - 1)));
  }
  return "n/a";
}

function reliabilityBadge(score) {
  if (score >= 0.6) return '<span class="badge badge-reliable">Reliable</span>';
  if (score >= 0.3) return '<span class="badge badge-developing">Developing</span>';
  return '<span class="badge badge-unproven">Unproven</span>';
}

function confBar(score) {
  const w = Math.round(score * 100);
  return `<div class="conf-bar-container"><div class="conf-bar" style="width:${w}%"></div></div>`;
}

function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

function setActive(page) {
  $$("nav .links a").forEach(a => {
    a.classList.toggle("active", a.dataset.page === page);
  });
}

function today() {
  return new Date().toISOString().slice(0, 10);
}
