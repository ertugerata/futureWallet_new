/* Karar girişi sayfası — pb_token auth, 401 → /web/login */
'use strict';

(function () {
  var form = document.getElementById('decisionForm');
  var errEl = document.getElementById('formError');

  function showError(msg) {
    errEl.textContent = msg;
    errEl.hidden = false;
  }

  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    errEl.hidden = true;
    var data = {};
    for (var kv of new FormData(form)) {
      if (kv[1] !== '' && kv[1] != null) data[kv[0]] = kv[1];
    }
    var headers = { 'Content-Type': 'application/json' };
    var token = sessionStorage.getItem('pb_token');
    if (token) headers['Authorization'] = 'Bearer ' + token;
    try {
      var res = await fetch('/api/decisions', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(data),
      });
      if (res.status === 401) {
        sessionStorage.removeItem('pb_token');
        window.location.href = '/web/login';
        return;
      }
      if (res.ok) {
        window.location.href = '/web/';
      } else {
        var err = await res.json().catch(function () { return { detail: res.statusText }; });
        var msg = Array.isArray(err.detail)
          ? err.detail.map(function (d) { return (d.loc || []).join('.') + ': ' + d.msg; }).join('\n')
          : (err.detail || res.statusText);
        showError('Hata: ' + msg);
      }
    } catch (err2) {
      showError('Bağlantı hatası: ' + err2.message);
    }
  });
})();
