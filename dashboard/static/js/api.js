/* Prometheus Market Intelligence — Multi-endpoint API client */

const _BASE = 'http://localhost:8000/api/v1';

async function _get(path) {
  const res = await fetch(`${_BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`);
  return res.json();
}

async function _post(path, body) {
  const res = await fetch(`${_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`);
  return res.json();
}

const API = {
  // ── Sports Signals ─────────────────────────────────────
  signals: {
    dashboard()               { return _get('/signals/dashboard'); },
    pending()                 { return _get('/signals/pending'); },
    straights()               { return _get('/signals/straights'); },
    parlays()                 { return _get('/signals/parlays'); },
    sources()                 { return _get('/signals/sources'); },
    results(date)             { return _get(`/signals/results?date=${date || ''}`); },
    ingest(source, text)      { return _post('/signals/ingest', { source, text }); },
    grade(signalId, status)   { return _post('/signals/grade', { signal_id: signalId, status }); },
  },

  // ── Political Intelligence ─────────────────────────────
  politics: {
    dashboard()               { return _get('/politics/dashboard'); },
    alerts(limit = 20)        { return _get(`/politics/alerts?limit=${limit}`); },
    trades(days = 90)         { return _get(`/politics/trades?days=${days}`); },
    bills(minScore = 0.3)     { return _get(`/politics/bills?min_score=${minScore}`); },
    profile(name)             { return _get(`/politics/profile/${encodeURIComponent(name)}`); },
    briefing()                { return _get('/politics/briefing'); },
    collect(congress = 119)   { return _post(`/politics/collect?congress=${congress}`, {}); },
  },

  // ── Live Odds ──────────────────────────────────────────
  odds: {
    sports()                      { return _get('/odds/sports'); },
    fetch(sport, regions, markets) {
      const p = new URLSearchParams({ sport, regions: regions || 'us', markets: markets || 'h2h,spreads' });
      return _get(`/odds/odds?${p}`);
    },
    movement(team, market, hours) {
      const p = new URLSearchParams({ market: market || 'spreads', hours: hours || 24 });
      return _get(`/odds/movement/${encodeURIComponent(team)}?${p}`);
    },
    best(eventId, market)         { return _get(`/odds/best/${encodeURIComponent(eventId)}?market=${market || 'h2h'}`); },
  },

  // ── Council of AI Agents ───────────────────────────────
  council: {
    analyze(topic, context = '') { return _post('/council/analyze', { topic, context }); },
    debate(id)                   { return _get(`/council/debate/${id}`); },
    history(limit = 20)          { return _get(`/council/history?limit=${limit}`); },
    agents()                     { return _get('/council/agents'); },
  },

  // ── System ────────────────────────────────────────────
  health()  { return fetch(`http://localhost:8000/health`).then(r => r.json()); },
  skills()  { return _get('/skills'); },
};
