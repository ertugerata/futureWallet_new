/* FutureWallet giriş ekranı — PB auth-with-password → sessionStorage.pb_token */
(function () {
  'use strict';
  var PB_BASE = (document.querySelector('meta[name="pb-base"]') || {}).content || '';
  var form = document.getElementById('loginForm');
  var errEl = document.getElementById('loginError');
  var btn = document.getElementById('btnLogin');

  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    btn.disabled = true;
    btn.textContent = 'Girişiliyor…';
    errEl.hidden = true;
    try {
      var res = await fetch(PB_BASE + '/api/collections/users/auth-with-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          identity: document.getElementById('email').value.trim(),
          password: document.getElementById('password').value,
        }),
      });
      if (!res.ok) {
        var detail = await res.json().catch(function () { return {}; });
        throw new Error(detail.message || ('HTTP ' + res.status));
      }
      var data = await res.json();
      sessionStorage.setItem('pb_token', data.token);
      window.location.href = '/web/';
    } catch (err) {
      errEl.textContent = 'Giriş başarısız: ' + err.message;
      errEl.hidden = false;
      btn.disabled = false;
      btn.textContent = 'Giriş Yap';
    }
  });
})();
