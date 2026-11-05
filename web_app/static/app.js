/* ── FutureWallet Dashboard – Client-side logic ───────────────────── */
'use strict';

const API = window.location.origin;   // FastAPI aynı port'ta çalışır

/* ── Helpers ──────────────────────────────────────────────────────── */
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};
function toast(msg, type = 'info', dur = 3500) {
  const c = $('#toastContainer');
  const t = el('div', 'toast ' + type, msg);
  c.appendChild(t);
  setTimeout(() => { t.remove(); }, dur);
}
function req(path, params = {}) {
  const u = new URL(API + path);
  for (const [k, v] of Object.entries(params))
    if (v !== undefined && v !== null) u.searchParams.set(k, String(v));
  const headers = { 'Content-Type': 'application/json' };
  const token = sessionStorage.getItem('apiToken');
  if (token) headers['Authorization'] = 'Bearer ' + token;
  return fetch(u.toString(), { headers }).then(r => {
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  });
}
function fmtTL(n, currency = 'TRY') {
  return new Intl.NumberFormat('tr-TR', { style: 'currency', currency, maximumFractionDigits: 0 }).format(n ?? 0);
}
function fmtPct(v) {
  return (v == null ? '—' : (v >= 0 ? '+' : '') + v.toFixed(2) + '%');
}
function badge(label) {
  const b = el('span', 'badge ' + (label || 'OPEN').replace(/\s+/g, '_').toUpperCase());
  b.textContent = label || 'OPEN';
  return b;
}

/* ── Health check ─────────────────────────────────────────────────── */
async function checkHealth() {
  const pulse = $('#healthPulse');
  const label = $('#healthLabel');
  try {
    const r = await fetch(API + '/health');
    if (r.ok) { pulse.className = 'pulse ok';   label.textContent = 'API: online'; }
    else      { pulse.className = 'pulse fail'; label.textContent = 'API: hata'; }
  } catch (e) {
    pulse.className = 'pulse fail'; label.textContent = 'API: erişilemez';
  }
}

/* ── Chart (global registry, tek Canvas) ─────────────────────────── */
const charts = new Map();

function destroyChart(key) {
  const c = charts.get(key);
  if (c) { c.destroy(); charts.delete(key); }
}
function newChart(key, canvas, cfg) {
  destroyChart(key);
  const ctx = canvas.getContext('2d');
  const ch = new Chart(ctx, cfg);
  charts.set(key, ch);
  return ch;
}

/* ── Panel 1: Snapshot ────────────────────────────────────────────── */
let snapshotChart = null;

async function loadSnapshot() {
  const date = $('#snapshotDate').value || new Date().toISOString().slice(0, 10);
  $('#btnSnapshot').disabled = true;
  $('#btnSnapshot').textContent = 'Yükleniyor…';
  try {
    const data = await req('/api/portfolio/snapshot', { date });
    // KV grid
    const kv = $('#snapshotKV');
    kv.innerHTML = '';
    const rows = [
      ['Toplam Değer',        fmtTL(data.total_value)],
      ['Varlık Sayısı',       data.holdings?.length ?? 0],
      ['Tarih',               data.as_of_date ?? date],
    ];
    for (const [label, value] of rows) {
      const div = el('div', 'kv-item');
      div.appendChild(el('div', '', label));
      div.appendChild(el('div', 'value', value));
      kv.appendChild(div);
    }
    // Tek spot chart
    const holdings = data.holdings || [];
    const canvas = $('#snapshotChart');
    canvas.parentElement.style.minHeight = '200px';
    newChart('snapshot', canvas, {
      type: 'bar',
      data: {
        labels: holdings.map(h => h.asset_symbol || '?'),
        datasets: [{
          label: 'Değer (₺)',
          data: holdings.map(h => h.value || 0),
          backgroundColor: ['#3b82f6','#10b981','#f59e0b','#8b5cf6','#ec4899','#14b8a6','#f97316'][0] || '#3b82f6',
          borderRadius: 4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, ticks: { callback: v => fmtTL(v) } },
          x: { grid: { display: false } },
        },
      },
    });
    toast('Snapshot yüklendi: ' + fmtTL(data.total_value), 'success');
  } catch (e) {
    toast('Snapshot hatası: ' + e.message, 'error');
  } finally {
    $('#btnSnapshot').disabled = false;
    $('#btnSnapshot').textContent = 'Güncelle';
  }
}

$('#btnSnapshot').addEventListener('click', loadSnapshot);
$('#snapshotDate').addEventListener('change', loadSnapshot);
// Varsayılan bugünkü tarih
(function setDefaultDate() {
  const d = new Date().toISOString().slice(0, 10);
  $('#snapshotDate').value = d;
})();

/* ── Panel 2: Decisions ───────────────────────────────────────────── */
async function loadDecisions() {
  const tbody = $('#decisionsBody');
  tbody.innerHTML = '';
  const loaderRow = el('tr');
  const loaderTd = el('td', 'empty-row', 'Yükleniyor…');
  loaderTd.colSpan = 8;
  loaderRow.appendChild(loaderTd);
  tbody.appendChild(loaderRow);
  try {
    const list = await req('/api/decisions');
    if (!list || list.length === 0) {
      tbody.textContent = '';
      const emptyRow = el('tr');
      const emptyTd = el('td', 'empty-row', 'Karar yok — yukarıdaki + butonuna tıklayın.');
      emptyTd.colSpan = 8;
      emptyRow.appendChild(emptyTd);
      tbody.appendChild(emptyRow);
      return;
    }
    tbody.innerHTML = '';
    for (const d of list) {
      const tr = el('tr');
      tr.appendChild(el('td', '', d.date ? d.date.slice(0, 10) : '—'));
      tr.appendChild(el('td', '', d.asset_symbol || '—'));
      tr.appendChild(el('td', '', d.action || '—'));
      tr.appendChild(el('td', '', badge(d.sentiment)));
      tr.appendChild(el('td', '', d.target_price != null ? d.target_price.toFixed(2) : '—'));
      tr.appendChild(el('td', '', d.target_date || '—'));
      tr.appendChild(el('td', '', badge(d.status)));
      // AI retrospective badge
      const tdAI = el('td');
      if (d.ai_retrospective) {
        tdAI.appendChild(el('span', 'badge STRATEGIC', 'AI ✅'));
        tdAI.title = d.ai_retrospective.slice(0, 200);
      } else if (d.status === 'REVIEWED') {
        tdAI.appendChild(el('span', 'badge EXPIRED', '—'));
      } else {
        tdAI.appendChild(el('span', 'badge OPEN', ' Beklemede'));
      }
      tr.appendChild(tdAI);
      tbody.appendChild(tr);
    }
  } catch (e) {
    toast('Karar listeleme hatası: ' + e.message, 'error');
  }
}

async function apiFetch(path, opts = {}) {
  const u = new URL(API + path);
  for (const [k, v] of Object.entries(opts.params || {}))
    if (v !== undefined && v !== null) u.searchParams.set(k, String(v));
  const res = await fetch(u.toString(), {
    method: opts.method || 'GET',
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    const msg = detail.detail || detail.message || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return res.json();
}

async function createDecision(formData) {
  const body = {};
  for (const [k, v] of formData.entries()) {
    if (v === '' || v == null) continue;
    body[k] = v;
  }
  try {
    await apiFetch('/api/decisions', {
      method: 'POST',
      body,
    });
    toast('Karar kaydedildi', 'success');
    $('#decisionModal').hidden = true;
    loadDecisions();
  } catch (e) {
    toast('Kaydetme hatası: ' + e.message, 'error');
  }
}

$('#btnShowDecisionForm').addEventListener('click', () => {
  $('#decisionModal').hidden = false;
  $('#decisionForm').reset();
});
$('#btnCloseModal').addEventListener('click', () => { $('#decisionModal').hidden = true; });
$('#btnCancelModal').addEventListener('click', () => { $('#decisionModal').hidden = true; });
$('#decisionForm').addEventListener('submit', e => {
  e.preventDefault();
  const fd = new FormData(e.target);
  createDecision(fd);
});

/* ── Panel 3: Counterfactual ──────────────────────────────────────── */
async function runCounterfactual() {
  const id = $('#cfDecisionId').value.trim();
  const elWrap = $('#cfResult');
  elWrap.innerHTML = '';
  if (!id) {
    const msg = document.createElement('div');
    msg.className = 'cf-empty';
    msg.textContent = 'Karar ID girin.';
    elWrap.appendChild(msg);
    return;
  }
  const loading = document.createElement('div');
  loading.className = 'cf-empty';
  loading.textContent = 'Yükleniyor…';
  elWrap.appendChild(loading);
  try {
    const result = await req('/api/counterfactual', { decision_id: id });
    if (result.error) {
      elWrap.innerHTML = '';
      const err = document.createElement('div');
      err.className = 'cf-empty';
      err.textContent = result.error;
      elWrap.appendChild(err);
      return;
    }
    const sp = result.shadow_portfolio_value ?? 0;
    const op = result.opportunity_cost ?? 0;
    const oppct = result.opportunity_cost_pct ?? 0;
    const isWin = oppct >= 0;
    elWrap.innerHTML = '';
    // Stats
    const stats = el('div', 'cf-stats');
    const makeStat = (label, value, cls, fmt) => {
      const s = el('div', 'cf-stat ' + cls);
      s.appendChild(el('div', 'cf-stat-label', label));
      s.appendChild(el('div', 'cf-stat-value', fmt(value)));
      return s;
    };
    stats.appendChild(makeStat('Gerçek Portföy', rp, '', fmtTL));
    stats.appendChild(makeStat('Gölge Portföy', sp, '', fmtTL));
    stats.appendChild(makeStat('Fırsat Maliyeti', op, isWin ? 'positive' : 'negative', fmtTL));
    elWrap.appendChild(stats);
    // Bar
    const maxV = Math.max(Math.abs(rp), Math.abs(sp), 1);
    const bar = el('div', 'cf-bar-track');
    const fill = el('div', 'cf-bar-fill ' + (isWin ? 'good' : 'bad'));
    fill.style.width = Math.abs(oppct / 100) * 100 + '%';
    bar.appendChild(fill);
    elWrap.appendChild(el('p', '', `Fırsat maliyeti: ${fmtPct(oppct)} — ${isWin ? 'kararın doğru yönde' : 'kararın ters yönde'}`));
    toast('Gölge kıyaslaması yüklendi', 'success');
  } catch (e) {
    toast('Kıyaslama hatası: ' + e.message, 'error');
  }
}
$('#btnCfCompare').addEventListener('click', runCounterfactual);

/* ── Panel 4: Monte Carlo ─────────────────────────────────────────── */
let mcChart = null;

async function runMonteCarlo() {
  const assets = $('#simAssets').value;
  const days   = parseInt($('#simDays').value) || 126;
  const sims   = parseInt($('#simSims').value) || 10000;
  $('#btnSimRun').disabled = true;
  $('#btnSimRun').textContent = 'Çalıştırılıyor…';
  const mcSummary = $('#mcSummary');
  mcSummary.innerHTML = '';
  const loadingSum = el('div', 'mc-empty', 'Simülasyon çalıştırılıyor…');
  mcSummary.appendChild(loadingSum);
  const aiNarrative = $('#aiNarrative');
  aiNarrative.innerHTML = '';
  const loadingAI = el('div', 'ai-empty', 'AI analiz yükleniyor…');
  aiNarrative.appendChild(loadingAI);
  $('#mcChart').parentElement.style.minHeight = '300px';

  try {
    const result = await req('/api/simulation/monte-carlo', {
      assets, days, simulations: sims,
      percentiles: '5,50,95',
    });
    // Summary kartları
    const pv    = result.percentile_values?.portfolio ?? {};
    const init  = result.total_initial_value ?? 0;
    const gpct  = init > 0 ? ((pv.p50 - init) / init * 100) : 0;
    const sum   = el('div', 'mc-summary');
    const mkC   = (label, key, cls) => {
      const c = el('div', 'mc-card ' + cls);
      c.appendChild(el('div', 'mc-card-label', label));
      c.appendChild(el('div', 'mc-card-value', fmtTL(pv[key] ?? 0)));
      return c;
    };
    sum.appendChild(mkC('%5 Bear (En kötü)',  'p5',  'p5'));
    sum.appendChild(mkC('%50 Medyan (Base)', 'p50', 'p50'));
    sum.appendChild(mkC('%95 Bull (En iyi)', 'p95', 'p95'));
    mcSummary.innerHTML = '';
    mcSummary.appendChild(sum);

    // Histogram placeholder (tek No0st buyout dağılımı gösterimi)
    const canvas = $('#mcChart');
    newChart('mc', canvas, {
      type: 'doughnut',
      data: {
        labels: ['En kötü %5', 'Olası %45', 'Medyan %50', 'En iyi %5'],
        datasets: [{
          data: [pv.p5 ?? 0, (pv.p50 - pv.p5) * 0.45, (pv.p50 - pv.p5) * 0.45, pv.p95 ?? 0],
          backgroundColor: ['#dc2626','#f59e0b','#3b82f6','#16a34a'],
          borderWidth: 0,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 12, padding: 12 } },
          tooltip: { callbacks: { label: ctx => ctx.raw.toLocaleString('tr-TR') + ' ₺' } },
        },
      },
    });

    // AI narrative
    if (result.narrative) {
      const content = document.createElement('div');
      content.className = 'ai-content';
      content.textContent = result.narrative;
      $('#aiNarrative').appendChild(content);
      
      // Disclaimer
      const disclaimer = document.createElement('div');
      disclaimer.className = 'ai-disclaimer';
      disclaimer.style.marginTop = '1rem';
      disclaimer.style.padding = '0.5rem';
      disclaimer.style.borderTop = '1px solid #ddd';
      disclaimer.style.fontSize = '0.8rem';
      disclaimer.style.color = '#666';
      disclaimer.textContent = '⚠️ Bu AI analizi yatırım tavsiyesi değildir. Kararlarınız kendi araştırmanıza dayanmalıdır.';
      $('#aiNarrative').appendChild(disclaimer);
    } else {
      const content = document.createElement('div');
      content.className = 'ai-content';
      content.textContent = [
        '📊 Simülasyon Özeti:',
        '   Başlangıç: ' + fmtTL(init) + ' → Medyan ' + fmtTL(pv.p50 ?? 0) + ' (' + fmtPct(gpct) + ')',
        '   Bear  %5:  ' + fmtTL(pv.p5  ?? 0),
        '   Bull  %95: ' + fmtTL(pv.p95 ?? 0),
        '',
        '   Öneri: AI risk anlatısı için Google API key ekleyin.',
        '   (config.py → GOOGLE_API_KEY)',
      ].join('\n');
      $('#aiNarrative').appendChild(content);
    }
    toast('Monte Carlo tamamlandı', 'success');
  } catch (e) {
    toast('Monte Carlo hatası: ' + e.message, 'error');
  } finally {
    $('#btnSimRun').disabled = false;
    $('#btnSimRun').textContent = 'Çalıştır';
  }
}
$('#btnSimRun').addEventListener('click', runMonteCarlo);

/* ── Boot ─────────────────────────────────────────────────────────── */
(async function boot() {
  await checkHealth();
  await loadSnapshot();
  await loadDecisions();
  // Tarih değişince snapshot'ı otomatik yenile
  setInterval(checkHealth, 30_000);
})();
