/**
 * 登录页逻辑
 *
 * 与后端契约（见 backend/app.py）：
 *   POST /api/v1/auth/register  {email, username, password} → {token, user}
 *   POST /api/v1/auth/login     {account, password}         → {token, user}
 *   GET  /api/v1/auth/me        Authorization: Bearer <token>
 *
 * token 存 localStorage（勾选「记住我」）或 sessionStorage（不勾，关浏览器即失效）。
 */
(function () {
  'use strict';

  var API_BASE = (window.CS_API_BASE || 'http://127.0.0.1:8000') + '/api/v1';
  var TOKEN_KEY = 'cs_token';

  // -------------------------------------------------------------------------
  // 主题切换（书脊里的 5 个色点）——与主站同一套逻辑，只是不需要弹窗确认
  // -------------------------------------------------------------------------
  var THEMES = {
    red:    { '--theme-color': '#ff0000', '--theme-color-dark': '#cc0000', '--theme-color-light': '#ff4d4d', '--theme-color-glow': 'rgba(255,0,0,.45)' },
    green:  { '--theme-color': '#00c800', '--theme-color-dark': '#008a00', '--theme-color-light': '#33d633', '--theme-color-glow': 'rgba(0,200,0,.45)' },
    blue:   { '--theme-color': '#0040ff', '--theme-color-dark': '#002db3', '--theme-color-light': '#4079ff', '--theme-color-glow': 'rgba(0,64,255,.45)' },
    orange: { '--theme-color': '#ff6f00', '--theme-color-dark': '#cc5800', '--theme-color-light': '#ff8c33', '--theme-color-glow': 'rgba(255,111,0,.45)' },
    purple: { '--theme-color': '#7A0080', '--theme-color-dark': '#5a0060', '--theme-color-light': '#a039a6', '--theme-color-glow': 'rgba(122,0,128,.45)' }
  };

  function applyTheme(name) {
    var vars = THEMES[name];
    if (!vars) return;
    var root = document.documentElement;
    Object.keys(vars).forEach(function (k) {
      root.style.setProperty(k, vars[k]);
    });
    document.querySelectorAll('.theme-tab').forEach(function (tab) {
      var on = tab.dataset.theme === name;
      tab.classList.toggle('active', on);
      tab.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    try { localStorage.setItem('shopmod-theme', name); } catch (e) { /* 忽略 */ }
  }

  function initTheme() {
    var saved = null;
    try { saved = localStorage.getItem('shopmod-theme'); } catch (e) { /* 忽略 */ }
    var fromUrl = null;
    try { fromUrl = new URLSearchParams(location.search).get('theme'); } catch (e) { /* 忽略 */ }
    applyTheme(fromUrl && THEMES[fromUrl] ? fromUrl : (saved && THEMES[saved] ? saved : 'purple'));

    document.querySelectorAll('.theme-tab').forEach(function (tab) {
      tab.addEventListener('click', function () {
        applyTheme(tab.dataset.theme);
      });
    });
  }

  // -------------------------------------------------------------------------
  // HTTP
  // -------------------------------------------------------------------------
  function request(path, options) {
    options = options || {};
    var headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
    return fetch(API_BASE + path, {
      method: options.method || 'GET',
      headers: headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
      credentials: 'omit'
    }).then(function (res) {
      return res.text().then(function (text) {
        var data = null;
        try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
        if (!res.ok) {
          var msg = (data && (data.detail || data.title)) || ('请求失败（' + res.status + '）');
          var err = new Error(msg);
          err.status = res.status;
          err.data = data;
          throw err;
        }
        return data;
      });
    });
  }

  function saveToken(token, remember) {
    try {
      localStorage.removeItem(TOKEN_KEY);
      sessionStorage.removeItem(TOKEN_KEY);
      (remember ? localStorage : sessionStorage).setItem(TOKEN_KEY, token);
    } catch (e) { /* 隐私模式下可能失败，忽略 */ }
  }

  function readToken() {
    try {
      return localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY) || '';
    } catch (e) { return ''; }
  }

  // -------------------------------------------------------------------------
  // 表单
  // -------------------------------------------------------------------------
  function $(id) { return document.getElementById(id); }

  function setError(el, message) {
    if (!el) return;
    el.textContent = message || '';
  }

  function setLoading(btn, loading) {
    if (!btn) return;
    btn.disabled = loading;
    btn.classList.toggle('is-loading', loading);
  }

  // 给校验失败的输入框加标记（CSS 靠 .is-invalid 判断，
  // 静态 :invalid 会把空的 required 框也标红，误伤太重）
  function markInvalid(el, bad) {
    if (!el) return;
    el.classList.toggle('is-invalid', !!bad);
    if (bad) el.setAttribute('aria-invalid', 'true');
    else el.removeAttribute('aria-invalid');
  }

  function switchTab(which) {
    var isLogin = which === 'login';
    $('tabLogin').classList.toggle('active', isLogin);
    $('tabLogin').setAttribute('aria-selected', isLogin ? 'true' : 'false');
    $('tabRegister').classList.toggle('active', !isLogin);
    $('tabRegister').setAttribute('aria-selected', !isLogin ? 'true' : 'false');
    $('loginForm').hidden = !isLogin;
    $('registerForm').hidden = isLogin;
    setError($('loginError'), '');
    setError($('registerError'), '');
    var focusEl = isLogin ? $('loginAccount') : $('regEmail');
    if (focusEl) focusEl.focus();
  }

  // 客户端预校验（服务端仍会再验一遍，这里只是为了少发一次请求）
  function clientCheckEmail(v) {
    return /^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$/.test(v);
  }

  function clientCheckPassword(v) {
    if (v.length < 8) return '密码至少 8 位';
    if (!/[A-Za-z]/.test(v)) return '密码必须包含字母';
    if (!/\d/.test(v)) return '密码必须包含数字';
    return '';
  }

  function onSubmitLogin(e) {
    e.preventDefault();
    var account = $('loginAccount').value.trim();
    var password = $('loginPassword').value;
    var errEl = $('loginError');
    var btn = $('loginSubmit');

    if (!account) { markInvalid($('loginAccount'), true); setError(errEl, '请输入邮箱或用户名'); $('loginAccount').focus(); return; }
    if (!password) { markInvalid($('loginPassword'), true); setError(errEl, '请输入密码'); $('loginPassword').focus(); return; }

    setError(errEl, '');
    setLoading(btn, true);

    request('/auth/login', { method: 'POST', body: { account: account, password: password } })
      .then(function (data) {
        saveToken(data.token, $('rememberMe').checked);
        // 记下用户名，主站顶栏可以显示
        try { localStorage.setItem('cs_user', JSON.stringify(data.user)); } catch (e2) { /* 忽略 */ }
        location.href = 'index.html?login=1';
      })
      .catch(function (err) {
        setError(errEl, err.message);
        setLoading(btn, false);
      });
  }

  function onSubmitRegister(e) {
    e.preventDefault();
    var email = $('regEmail').value.trim();
    var username = $('regUsername').value.trim();
    var password = $('regPassword').value;
    var errEl = $('registerError');
    var btn = $('registerSubmit');

    if (!clientCheckEmail(email)) { markInvalid($('regEmail'), true); setError(errEl, '邮箱格式不正确'); $('regEmail').focus(); return; }
    if (username.length < 2) { markInvalid($('regUsername'), true); setError(errEl, '用户名至少 2 个字符'); $('regUsername').focus(); return; }
    var pwErr = clientCheckPassword(password);
    if (pwErr) { markInvalid($('regPassword'), true); setError(errEl, pwErr); $('regPassword').focus(); return; }

    setError(errEl, '');
    setLoading(btn, true);

    request('/auth/register', { method: 'POST', body: { email: email, username: username, password: password } })
      .then(function (data) {
        saveToken(data.token, true);
        try { localStorage.setItem('cs_user', JSON.stringify(data.user)); } catch (e2) { /* 忽略 */ }
        location.href = 'index.html?register=1';
      })
      .catch(function (err) {
        setError(errEl, err.message);
        setLoading(btn, false);
      });
  }

  // -------------------------------------------------------------------------
  // 启动
  // -------------------------------------------------------------------------
  function init() {
    initTheme();

    $('tabLogin').addEventListener('click', function () { switchTab('login'); });
    $('tabRegister').addEventListener('click', function () { switchTab('register'); });

    $('loginForm').addEventListener('submit', onSubmitLogin);
    $('registerForm').addEventListener('submit', onSubmitRegister);

    var forgot = $('forgotLink');
    if (forgot) {
      forgot.addEventListener('click', function (e) {
        e.preventDefault();
        setError($('loginError'), '暂未开放密码找回，请联系管理员重置');
      });
    }

    var label = $('apiBaseLabel');
    if (label) label.textContent = API_BASE.replace('/api/v1', '');

    // 已登录就直接回商城
    var token = readToken();
    if (token) {
      request('/auth/me', { headers: { Authorization: 'Bearer ' + token } })
        .then(function () { location.href = 'index.html'; })
        .catch(function () {
          try { localStorage.removeItem(TOKEN_KEY); sessionStorage.removeItem(TOKEN_KEY); } catch (e) { /* 忽略 */ }
        });
    }

    var focusEl = $('loginAccount');
    if (focusEl) focusEl.focus();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
