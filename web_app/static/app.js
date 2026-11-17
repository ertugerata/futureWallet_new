/* FutureWallet dashboard — PB JWT auth + paneller.
   CSP uyumlu: inline handler/histogram innerHTML yok, tüm DOM textContent ile kurulur. */
'use strict';

const API = '';
const PB_BASE = (document.querySelector('meta[name="pb-base"]') || {}).content || '';

/* ── yardımcılar ─────────────────────────────────────────────────── */
const $ = (sel) => document.querySelector(sel);

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = String(text);
  return n;
}

function toast(msg, type = 'info', dur = 3500) {
  const c = $('#toastContainer');
  if (!c) return;
  const t = el('div', 'toast ' + type, msg);
  c.appendChild(t);
  setTimeout(() => t.remove(), dur);
}

window._currency = 'TRY';

function fmtCurrency(n, currency = 'TRY') {
  return new Intl.NumberFormat('tr-TR', { style: 'currency', currency, maximumFractionDigits: 0 }).format(n ?? 0);
}
function fmtTL(n) { return fmtCurrency(n, window._currency); }
function fmtPct(v) { return (v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(2) + '%'); }
function badge(label) {
  const b = el('span', 'badge ' + (label || 'OPEN').replace(/\s+/g, '_').toUpperCase());
  b.textContent = label || 'OPEN';
  return b;
}

/* ── auth + istek katmanı (P14/P6: PB JWT) ───────────────────────── */
function authHeaders() {
  const h = { 'Content-Type': 'application/json' };
  const t = sessionStorage.getItem('pb_token');
  if (t) h['Authorization'] = 'Bearer ' + t;
  return h;
}

function toLogin() {
  sessionStorage.removeItem('pb_token');
  window.location.href = '/web/login';
}

async function api(path, opts = {}) {
  const u = new URL(API + path, window.location.origin);
  for (const [k, v] of Object.entries(opts.params || {})) {
    if (v !== undefined && v !== null && v !== '') u.searchParams.set(k, String(v));
  }
  const res = await fetch(u.toString(), {
    method: opts.method || 'GET',
    headers: authHeaders(),
    body: opts.body != null ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 401) {
    toast('Oturum süresi doldu — yeniden giriş gerekiyor', 'error');
    toLogin();
    throw new Error('401 Unauthorized');
  }
  if (res.status === 204) return null;
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || d.message || ('HTTP ' + res.status));
  }
  return res.json();
}

async function refreshToken() {
  const t = sessionStorage.getItem('pb_token');
  if (!t) { toLogin(); return false; }
  try {
    const res = await fetch(PB_BASE + '/api/collections/users/auth-refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: t },
      body: JSON.stringify({}),
    });
    if (!res.ok) { toLogin(); return false; }
    const data = await res.json();
    if (data.token) sessionStorage.setItem('pb_token', data.token);
    return true;
  } catch (e) {
    // PB erişilemez (ağ): API kendi doğrulamasını yapar, devam et
    console.warn('auth-refresh denendi, erişilemedi:', e.message);
    return true;
  }
}

/* ── health ──────────────────────────────────────────────────────── */
async function checkHealth() {
  const pulse = $('#healthPulse');
  const label = $('#healthLabel');
  try {
    const r = await fetch(API + '/health');
    if (r.ok) { pulse.className = 'pulse ok'; label.textContent = 'API: online'; }
    else { pulse.className = 'pulse fail'; label.textContent = 'API: hata'; }
  } catch (e) {
    pulse.className = 'pulse fail'; label.textContent = 'API: erişilemez';
  }
}

/* ── chart registry ──────────────────────────────────────────────── */
const charts = new Map();
function destroyChart(key) {
  const c = charts.get(key);
  if (c) { c.destroy(); charts.delete(key); }
}
function newChart(key, canvas, cfg) {
  destroyChart(key);
  const ch = new Chart(canvas.getContext('2d'), cfg);
  charts.set(key, ch);
  return ch;
}

/* ── Panel: Snapshot & Time-Travel ───────────────────────────────── */
window._lastSnapshot = null;

async function loadSnapshot() {
  const date = $('#snapshotDate').value || new Date().toISOString().slice(0, 10);
  $('#btnSnapshot').disabled = true;
  try {
    const data = await api('/api/portfolio/snapshot', { params: { date } });
    window._lastSnapshot = data;
    const cashHoldings = (data.holdings || []).filter(h => h.type === 'cash');
    const cashTotal = cashHoldings.reduce((a, h) => a + (h.quantity || 0), 0);
    const kv = $('#snapshotKV');
    kv.replaceChildren();
    const rows = [
      ['Toplam Değer', fmtTL(data.total_value), true],
      ['Toplam Maliyet', fmtTL(data.total_cost)],
      ['K/Z', fmtTL(data.pnl) + '  ' + fmtPct(data.pnl_pct), true],
      ['Nakit Kovası', fmtTL(cashTotal)],
      ['Temettü Geliri', fmtTL(data.cash_received)],
      ['Varlık Sayısı', (data.holdings || []).length - cashHoldings.length],
      ['Tarih', data.as_of],
    ];
    for (const [label, value, isMoney] of rows) {
      const div = el('div', 'kv-item');
      div.appendChild(el('div', '', label));
      const v = el('div', 'value' + (isMoney ? ' value-display' : ''), value);
      if (isMoney) v.dataset.value = String(label === 'K/Z' ? data.pnl : data.total_value);
      div.appendChild(v);
      kv.appendChild(div);
    }
    const holdings = (data.holdings || []).filter(h => h.type !== 'cash');
    newChart('snapshot', $('#snapshotChart'), {
      type: 'bar',
      data: {
        labels: holdings.map(h => h.asset_symbol),
        datasets: [{
          label: 'Değer',
          data: holdings.map(h => h.current_value || 0),
          backgroundColor: '#3b82f6',
          borderRadius: 4,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true }, x: { grid: { display: false } } },
      },
    });
  } catch (e) {
    if (e.message !== '401 Unauthorized') toast('Snapshot hatası: ' + e.message, 'error');
  } finally {
    $('#btnSnapshot').disabled = false;
  }
}

async function runTimeTravel() {
  const tStart = $('#ttStart').value;
  const tTarget = $('#ttTarget').value || new Date().toISOString().slice(0, 10);
  if (!tStart) { toast('Başlangıç tarihi gerekli', 'warn'); return; }
  const wrap = $('#ttResult');
  wrap.replaceChildren(el('div', 'kv-empty', 'Hesaplanıyor…'));
  try {
    const r = await api('/api/portfolio/time-travel', { params: { t_start: tStart, t_target: tTarget } });
    wrap.replaceChildren();
    for (const [label, value] of [
      ['Değer (T_start)', fmtTL(r.value_at_start)],
      ['Değer (T_target)', fmtTL(r.value_at_target)],
      ['Nominal K/Z', fmtTL(r.pnl) + '  ' + fmtPct(r.pnl_pct)],
    ]) {
      const div = el('div', 'kv-item');
      div.appendChild(el('div', '', label));
      div.appendChild(el('div', 'value', value));
      wrap.appendChild(div);
    }
  } catch (e) {
    wrap.replaceChildren(el('div', 'kv-empty', 'Hata: ' + e.message));
  }
}

/* ── Panel: Karar Günlüğü ────────────────────────────────────────── */
async function loadSentimentSummary() {
  const card = $('#sentimentSummary');
  if (!card) return;
  try {
    const res = await api('/api/decisions/stats');
    const counts = res.sentiment_counts || {};
    const entries = Object.entries(counts);
    if (entries.length === 0) {
      card.replaceChildren(el('div', 'summary-loading', 'Veri yok'));
      return;
    }
    const total = entries.reduce((a, [, c]) => a + c, 0);
    card.replaceChildren();
    for (const [sentiment, count] of entries) {
      const stat = el('div', 'sentiment-stat');
      stat.appendChild(el('div', 'sentiment-label', sentiment));
      stat.appendChild(el('div', 'sentiment-count', count));
      stat.appendChild(el('div', 'sentiment-pct', (100 * count / total).toFixed(1) + '%'));
      card.appendChild(stat);
    }
    if (res.insufficient_data) {
      card.appendChild(el('div', 'summary-loading', 'Yeterli veri yok (n < 3) — sonuç ortalaması hesaplanmadı'));
    }
  } catch (e) { /* sessiz: panel opsiyonel */ }
}

async function retroDecision(id, btn) {
  btn.disabled = true;
  btn.textContent = '…';
  try {
    const r = await api(`/api/decisions/${id}/retrospective`, { method: 'POST' });
    toast('Retrospektif hazır', 'success');
    loadDecisions();
    return r;
  } catch (e) {
    toast('Retrospektif: ' + e.message, 'error');
    btn.disabled = false;
    btn.textContent = 'AI';
  }
}

async function closeDecision(id) {
  try {
    await api(`/api/decisions/${id}/close`, { method: 'POST' });
    toast('Karar kapatıldı (REVIEWED)', 'success');
    loadDecisions();
  } catch (e) { toast('Kapatma: ' + e.message, 'error'); }
}

async function deleteDecision(id) {
  if (!confirm('Karar ve bağlı gölge pozisyonlar silinecek. Emin misin?')) return;
  try {
    await api(`/api/decisions/${id}`, { method: 'DELETE' });
    toast('Karar silindi', 'success');
    loadDecisions();
  } catch (e) { toast('Silme: ' + e.message, 'error'); }
}

async function loadDecisions() {
  const tbody = $('#decisionsBody');
  tbody.replaceChildren();
  const loader = el('tr');
  const td = el('td', 'empty-row', 'Yükleniyor…');
  td.colSpan = 9;
  loader.appendChild(td);
  tbody.appendChild(loader);
  try {
    const list = await api('/api/decisions');
    tbody.replaceChildren();
    if (!list.length) {
      const empty = el('tr');
      const etd = el('td', 'empty-row', 'Karar yok — "+ Yeni Karar" ile ekleyin.');
      etd.colSpan = 9;
      empty.appendChild(etd);
      tbody.appendChild(empty);
      return;
    }
    for (const d of list) {
      const tr = el('tr');
      tr.appendChild(el('td', '', (d.date || '—')));
      tr.appendChild(el('td', '', d.asset_symbol || '—'));
      tr.appendChild(el('td', '', d.action || '—'));
      const tdS = el('td'); tdS.appendChild(badge(d.sentiment)); tr.appendChild(tdS);
      tr.appendChild(el('td', '', d.target_price != null ? d.target_price.toFixed(2) : '—'));
      tr.appendChild(el('td', '', d.target_date || '—'));
      const tdSt = el('td'); tdSt.appendChild(badge(d.status)); tr.appendChild(tdSt);
      tr.appendChild(el('td', '', d.outcome_return_pct != null ? fmtPct(d.outcome_return_pct) : '—'));
      const tdA = el('td', 'row-actions');
      const bR = el('button', 'btn btn-ghost btn-sm', d.ai_retrospective ? 'AI ✓' : 'AI Retro');
      bR.title = d.ai_retrospective ? d.ai_retrospective.slice(0, 300) : 'AI retrospektifi üret';
      bR.addEventListener('click', () => retroDecision(d.id, bR));
      const bC = el('button', 'btn btn-ghost btn-sm', 'Kapat');
      bC.addEventListener('click', () => closeDecision(d.id));
      const bD = el('button', 'btn btn-danger btn-sm', 'Sil');
      bD.addEventListener('click', () => deleteDecision(d.id));
      tdA.appendChild(bR); tdA.appendChild(bC); tdA.appendChild(bD);
      tr.appendChild(tdA);
      tbody.appendChild(tr);
    }
  } catch (e) {
    if (e.message !== '401 Unauthorized') toast('Karar listesi: ' + e.message, 'error');
  }
}

/* modal karar formu */
async function createDecision(formData) {
  const body = {};
  for (const [k, v] of formData.entries()) {
    if (v === '' || v == null) continue;
    body[k] = v;
  }
  try {
    await api('/api/decisions', { method: 'POST', body });
    toast('Karar kaydedildi', 'success');
    $('#decisionModal').hidden = true;
    loadDecisions();
    loadSentimentSummary();
  } catch (e) {
    if (e.message !== '401 Unauthorized') toast('Kaydetme: ' + e.message, 'error');
  }
}

/* ── Panel: İşlemler ─────────────────────────────────────────────── */
async function loadTransactions() {
  const tbody = $('#txBody');
  if (!tbody) return;
  tbody.replaceChildren();
  try {
    const list = await api('/api/transactions', { params: { limit: 100 } });
    if (!list.length) {
      const tr = el('tr'); const td = el('td', 'empty-row', 'İşlem yok.'); td.colSpan = 7;
      tr.appendChild(td); tbody.appendChild(tr); return;
    }
    for (const t of list) {
      const tr = el('tr');
      tr.appendChild(el('td', '', String(t.timestamp || '').slice(0, 10)));
      tr.appendChild(el('td', '', t.asset_symbol));
      const tdT = el('td'); tdT.appendChild(badge(t.type)); tr.appendChild(tdT);
      tr.appendChild(el('td', '', t.quantity));
      tr.appendChild(el('td', '', t.price));
      tr.appendChild(el('td', '', t.fee || 0));
      const tdA = el('td', 'row-actions');
      if (!t.voided) {
        const b = el('button', 'btn btn-danger btn-sm', 'İptal Et');
        b.addEventListener('click', async () => {
          if (!confirm('İşlem void edilecek (soft delete). Emin misin?')) return;
          try {
            await api(`/api/transactions/${t.id}`, { method: 'DELETE' });
            toast('İşlem void edildi', 'success');
            loadTransactions(); loadSnapshot();
          } catch (e) { toast('Void: ' + e.message, 'error'); }
        });
        tdA.appendChild(b);
      } else {
        tdA.appendChild(el('span', 'badge VOIDED', 'VOID'));
      }
      tr.appendChild(tdA);
      tbody.appendChild(tr);
    }
  } catch (e) {
    if (e.message !== '401 Unauthorized') toast('İşlem listesi: ' + e.message, 'error');
  }
}

async function addTransaction(e) {
  e.preventDefault();
  const f = e.target;
  const body = {
    asset_symbol: f.txSymbol.value.trim().toUpperCase(),
    tx_type: f.txType.value,
    quantity: parseFloat(f.txQty.value),
    price: parseFloat(f.txPrice.value),
    fee: parseFloat(f.txFee.value || '0'),
  };
  if (f.txDate.value) body.timestamp = f.txDate.value;
  try {
    await api('/api/transactions', { method: 'POST', body });
    toast('İşlem eklendi', 'success');
    f.reset();
    loadTransactions();
    loadSnapshot();
  } catch (err) {
    if (err.message !== '401 Unauthorized') toast('İşlem: ' + err.message, 'error');
  }
}

/* ── Panel: Gölge Portföy + Ne Olurdu ────────────────────────────── */
async function loadShadowPositions() {
  const tbody = $('#shadowBody');
  if (!tbody) return;
  tbody.replaceChildren();
  try {
    const list = await api('/api/counterfactual/shadow-positions');
    if (!list.length) {
      const tr = el('tr'); const td = el('td', 'empty-row', 'Gölge pozisyon yok.'); td.colSpan = 6;
      tr.appendChild(td); tbody.appendChild(tr); return;
    }
    for (const p of list) {
      const tr = el('tr');
      tr.appendChild(el('td', '', p.entry_date || '—'));
      tr.appendChild(el('td', '', p.asset_symbol));
      const tdT = el('td'); tdT.appendChild(badge(p.shadow_type)); tr.appendChild(tdT);
      tr.appendChild(el('td', '', p.quantity));
      tr.appendChild(el('td', '', p.entry_price));
      const tdA = el('td', 'row-actions');
      const b = el('button', 'btn btn-danger btn-sm', 'Sil');
      b.addEventListener('click', async () => {
        if (!confirm('Gölge pozisyon silinsin mi?')) return;
        try {
          await api(`/api/counterfactual/shadow-positions/${p.id}`, { method: 'DELETE' });
          toast('Gölge pozisyon silindi', 'success');
          loadShadowPositions();
        } catch (e) { toast('Silme: ' + e.message, 'error'); }
      });
      tdA.appendChild(b);
      tr.appendChild(tdA);
      tbody.appendChild(tr);
    }
  } catch (e) {
    if (e.message !== '401 Unauthorized') toast('Gölge liste: ' + e.message, 'error');
  }
}

async function addShadowPosition(e) {
  e.preventDefault();
  const f = e.target;
  try {
    await api('/api/counterfactual/shadow-positions', {
      method: 'POST',
      body: {
        decision_id: f.shadowDecisionId.value.trim(),
        asset_symbol: f.shadowSymbol.value.trim().toUpperCase(),
        shadow_type: f.shadowType.value,
        quantity: parseFloat(f.shadowQty.value),
        entry_price: parseFloat(f.shadowPrice.value),
      },
    });
    toast('Gölge pozisyon eklendi', 'success');
    f.reset();
    loadShadowPositions();
  } catch (e2) {
    if (e2.message !== '401 Unauthorized') toast('Gölge ekleme: ' + e2.message, 'error');
  }
}

async function runCounterfactual() {
  const id = $('#cfDecisionId').value.trim();
  const wrap = $('#cfResult');
  wrap.replaceChildren();
  if (!id) {
    wrap.appendChild(el('div', 'cf-empty', 'Karar ID girin.'));
    return;
  }
  wrap.appendChild(el('div', 'cf-empty', 'Yükleniyor…'));
  try {
    const result = await api('/api/counterfactual', { params: { decision_id: id } });
    wrap.replaceChildren();
    const rp = result.real_portfolio_value ?? 0;
    const sp = result.shadow_portfolio_value ?? 0;
    const op = result.opportunity_cost ?? 0;
    const oppct = result.opportunity_cost_pct ?? 0;
    const isWin = oppct >= 0;
    const stats = el('div', 'cf-stats');
    const makeStat = (label, value, cls) => {
      const s = el('div', 'cf-stat ' + cls);
      s.appendChild(el('div', 'cf-stat-label', label));
      s.appendChild(el('div', 'cf-stat-value', fmtTL(value)));
      return s;
    };
    stats.appendChild(makeStat('Gerçek Portföy', rp, ''));
    stats.appendChild(makeStat('Gölge Portföy', sp, ''));
    stats.appendChild(makeStat('Fırsat Maliyeti', op, isWin ? 'positive' : 'negative'));
    wrap.appendChild(stats);
    wrap.appendChild(el('p', '', `Fırsat maliyeti: ${(oppct * 100).toFixed(2)}% — ${isWin ? 'gölge senaryo daha iyi' : 'gerçek karar daha iyi'}`));
  } catch (e) {
    wrap.replaceChildren(el('div', 'cf-empty', 'Hata: ' + e.message));
  }
}

/* ── Panel: Monte Carlo + Stres ──────────────────────────────────── */
function drawHistogram(canvas, histogram, p5, p50, p95) {
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  const bins = histogram.bins, counts = histogram.counts;
  const barCount = bins.length - 1;
  const pad = 50;
  const barWidth = (W - 2 * pad) / barCount;
  const maxCount = Math.max(...counts, 1);
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = '#3b82f6';
  for (let i = 0; i < barCount; i++) {
    const x = pad + i * barWidth;
    const hgt = (counts[i] / maxCount) * (H - 60);
    ctx.fillRect(x, H - hgt - 30, barWidth - 2, hgt);
  }
  const scaleX = (val) => pad + ((val - bins[0]) / (bins[bins.length - 1] - bins[0] || 1)) * (W - 2 * pad);
  const line = (val, color, label) => {
    ctx.strokeStyle = color; ctx.setLineDash([5, 5]); ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(scaleX(val), 10); ctx.lineTo(scaleX(val), H - 30); ctx.stroke();
    ctx.setLineDash([]); ctx.fillStyle = color; ctx.font = '12px sans-serif';
    ctx.fillText(label + ': ' + Math.round(val), scaleX(val) + 4, 20);
  };
  line(p5, '#ef4444', 'p5');
  line(p50, '#22c55e', 'p50');
  line(p95, '#3b82f6', 'p95');
}

async function runMonteCarlo() {
  const assets = $('#simAssets').value;
  const days = parseInt($('#simDays').value, 10) || 126;
  const sims = parseInt($('#simSims').value, 10) || 10000;
  $('#btnSimRun').disabled = true;
  const mcSummary = $('#mcSummary');
  mcSummary.replaceChildren(el('div', 'mc-empty', 'Simülasyon çalıştırılıyor…'));
  try {
    const result = await api('/api/simulation/monte-carlo', {
      params: { assets, days, simulations: sims, percentiles: '5,50,95' },
    });
    if (result.currency) {
      const sel = $('#currencySelect');
      sel.value = result.currency;
      setCurrency(result.currency);
    }
    const pv = (result.percentile_values || {}).portfolio || {};
    const init = result.total_initial_value ?? 0;
    mcSummary.replaceChildren();
    const sum = el('div', 'mc-summary');
    const mkC = (label, key, cls) => {
      const c = el('div', 'mc-card ' + cls);
      c.appendChild(el('div', 'mc-card-label', label));
      c.appendChild(el('div', 'mc-card-value value-display', fmtTL(pv[key] ?? 0)));
      c.querySelector('.value-display').dataset.value = String(pv[key] ?? 0);
      return c;
    };
    sum.appendChild(mkC('%5 Bear (En kötü)', 'p5', 'p5'));
    sum.appendChild(mkC('%50 Medyan (Base)', 'p50', 'p50'));
    sum.appendChild(mkC('%95 Bull (En iyi)', 'p95', 'p95'));
    const initCard = el('div', 'mc-card init');
    initCard.appendChild(el('div', 'mc-card-label', 'Başlangıç Değeri'));
    const initV = el('div', 'mc-card-value value-display', fmtTL(init));
    initV.dataset.value = String(init);
    initCard.appendChild(initV);
    sum.appendChild(initCard);
    mcSummary.replaceChildren(sum);
    if (result.data_quality === 'estimated') {
      mcSummary.appendChild(el('p', 'kv-empty', 'Veri kalitesi: tahmini (tarihsel seride eksik varlık)'));
    }
    if (result.histogram && result.histogram.bins) {
      destroyChart('mc');
      drawHistogram($('#mcChart'), result.histogram, pv.p5 ?? 0, pv.p50 ?? 0, pv.p95 ?? 0);
    }
    await loadNarrative(result);
  } catch (e) {
    mcSummary.replaceChildren(el('div', 'mc-empty', 'Monte Carlo hatası: ' + e.message));
    if (e.message !== '401 Unauthorized') toast('Monte Carlo: ' + e.message, 'error');
  } finally {
    $('#btnSimRun').disabled = false;
  }
}

async function loadNarrative(simResult) {
  const box = $('#aiNarrative');
  box.replaceChildren(el('div', 'ai-empty', 'AI anlatısı yükleniyor…'));
  try {
    const r = await api('/api/simulation/narrative', { method: 'POST', body: { simulation_result: simResult } });
    box.replaceChildren();
    box.appendChild(el('div', 'ai-content', r.narrative || '—'));
    box.appendChild(el('div', 'ai-disclaimer', '⚠️ Bu AI analizi yatırım tavsiyesi değildir. Kararlarınız kendi araştırmanıza dayanmalıdır.'));
  } catch (e) {
    box.replaceChildren(el('div', 'ai-empty', 'AI risk anlatısı kullanılamıyor (' + e.message + '). OPENROUTER_API_KEY tanımlayın.'));
  }
}

async function runStressTest() {
  const pvValue = (window._lastSnapshot && window._lastSnapshot.total_value) || parseFloat($('#stressValue').value || '0') || 100000;
  const days = parseInt($('#simDays').value, 10) || 126;
  $('#btnStress').disabled = true;
  const wrap = $('#stressResult');
  wrap.replaceChildren(el('div', 'mc-empty', 'Stres testi çalıştırılıyor…'));
  try {
    const r = await api('/api/simulation/stress-test', {
      method: 'POST',
      body: { portfolio_value: pvValue, days, n_simulations: 1000 },
    });
    wrap.replaceChildren();
    const table = el('table', 'data-table');
    const head = el('tr');
    for (const h of ['Senaryo', 'Beklenen', 'p5', 'p50', 'p95', 'Etki']) head.appendChild(el('th', '', h));
    table.appendChild(head);
    for (const [name, v] of Object.entries(r.stressed_values || {})) {
      const tr = el('tr', name === r.worst_case_name ? 'stress-worst' : '');
      tr.appendChild(el('td', '', v.description || name));
      tr.appendChild(el('td', '', fmtTL(v.expected_value)));
      tr.appendChild(el('td', '', fmtTL(v.p5)));
      tr.appendChild(el('td', '', fmtTL(v.p50)));
      tr.appendChild(el('td', '', fmtTL(v.p95)));
      tr.appendChild(el('td', '', fmtPct((v.loss_pct || 0) * 100)));
      table.appendChild(tr);
    }
    wrap.appendChild(table);
    wrap.appendChild(el('p', 'kv-empty', 'En kötü senaryo: ' + (r.worst_case_name || '—')));
  } catch (e) {
    wrap.replaceChildren(el('div', 'mc-empty', 'Stres testi: ' + e.message));
  } finally {
    $('#btnStress').disabled = false;
  }
}

/* ── para birimi seçicisi ────────────────────────────────────────── */
function setCurrency(cur) {
  window._currency = cur;
  document.querySelectorAll('.value-display').forEach((node) => {
    const val = parseFloat(node.dataset.value);
    if (!isNaN(val)) node.textContent = fmtCurrency(val, cur);
  });
}

/* ── boot ────────────────────────────────────────────────────────── */
(async function boot() {
  if (!(await refreshToken())) return;

  $('#btnSnapshot').addEventListener('click', loadSnapshot);
  $('#snapshotDate').addEventListener('change', loadSnapshot);
  $('#btnTT').addEventListener('click', runTimeTravel);
  $('#btnShowDecisionForm').addEventListener('click', () => {
    $('#decisionModal').hidden = false;
    $('#decisionForm').reset();
  });
  $('#btnCloseModal').addEventListener('click', () => { $('#decisionModal').hidden = true; });
  $('#btnCancelModal').addEventListener('click', () => { $('#decisionModal').hidden = true; });
  $('#decisionForm').addEventListener('submit', (e) => { e.preventDefault(); createDecision(new FormData(e.target)); });
  $('#txForm').addEventListener('submit', addTransaction);
  $('#shadowForm').addEventListener('submit', addShadowPosition);
  $('#btnCfCompare').addEventListener('click', runCounterfactual);
  $('#btnSimRun').addEventListener('click', runMonteCarlo);
  $('#btnStress').addEventListener('click', runStressTest);
  $('#currencySelect').addEventListener('change', (e) => setCurrency(e.target.value));
  $('#btnLogout').addEventListener('click', toLogin);

  const d = new Date().toISOString().slice(0, 10);
  $('#snapshotDate').value = d;

  await checkHealth();
  await loadSnapshot();
  await loadSentimentSummary();
  await loadDecisions();
  await loadTransactions();
  await loadShadowPositions();
  setInterval(checkHealth, 30000);
})();
