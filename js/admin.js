/**
 * 后台（商家 / 管理员）共用逻辑
 *
 * merchant.html 用：统计、商品管理、订单发货
 * admin.html   用：用户列表、角色分配、启用/禁用
 *
 * 后端按角色返回 403，前端只做「入口是否显示」，
 * 真正的权限判定始终在服务端。
 */
(function () {
  'use strict';

  // API 地址：后端托管前端时一律同源相对路径（本机 8000 / Radmin 虚拟 IP / 任何域名）。
// 只有从本机其它端口的独立静态服务器（如 8777）打开时，才回退到 127.0.0.1:8000。
// 不能写死 127.0.0.1 —— 对外访问时会变成请求访问者自己的电脑，导致登录态立即失效。
var IS_LOCAL_STATIC = /^(127\.0\.0\.1|localhost|\[::1\])$/.test(location.hostname) &&
  location.port !== '' && location.port !== '80' &&
  location.port !== '443' && location.port !== '8000';
var API_ORIGIN = window.CS_API_BASE || (IS_LOCAL_STATIC ? 'http://127.0.0.1:8000' : '');
  var API = API_ORIGIN + '/api/v1';
  var TOKEN_KEY = 'cs_token';

  var state = { me: null, role: null };

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function readToken() {
    try {
      return localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY) || '';
    } catch (e) { return ''; }
  }

  function request(path, options) {
    options = options || {};
    var token = readToken();
    var headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
    if (token) headers.Authorization = 'Bearer ' + token;

    return fetch(API + path, {
      method: options.method || 'GET',
      headers: headers,
      body: options.body ? JSON.stringify(options.body) : undefined
    }).then(function (res) {
      return res.text().then(function (text) {
        var data = null;
        try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
        if (!res.ok) {
          var err = new Error((data && (data.detail || data.title)) || ('请求失败 ' + res.status));
          err.status = res.status;
          throw err;
        }
        return data;
      });
    });
  }

  function money(cents) { return '¥' + (cents / 100).toFixed(2); }

  // -------------------------------------------------------------------------
  // 身份与入口守卫
  // -------------------------------------------------------------------------
  function requireRole(want) {
    var token = readToken();
    if (!token) {
      location.href = 'login.html?next=' + encodeURIComponent(location.pathname);
      return Promise.reject(new Error('未登录'));
    }

    return request('/auth/me').then(function (data) {
      state.me = data.user;
      state.role = data.user.role;

      var rank = { user: 0, merchant: 1, admin: 2 };
      if (rank[state.role] < rank[want]) {
        document.body.innerHTML =
          '<div class="guard">' +
          '<p class="guard-kicker">ACCESS DENIED</p>' +
          '<h1>这个页面需要' + (want === 'admin' ? '管理员' : '商家') + '权限</h1>' +
          '<p>你当前的身份是 <strong>' + (state.role || '未知') + '</strong>。</p>' +
          '<p><a href="index.html">返回商城</a></p>' +
          '</div>';
        return Promise.reject(new Error('权限不足'));
      }

      // 顶栏显示身份
      var who = $('whoAmI');
      if (who) {
        who.textContent = (state.me.display_name || state.me.username) +
          ' · ' + ({ user: '普通用户', merchant: '商家', admin: '管理员' }[state.role] || state.role);
      }
      return data;
    });
  }

  // -------------------------------------------------------------------------
  // 商家后台
  // -------------------------------------------------------------------------
  function renderStats(s) {
    var box = $('statGrid');
    if (!box) return;
    var cells = [
      ['在售商品', s.products, '件'],
      ['总库存', s.stock_total, '件'],
      ['累计月销', s.monthly_sales_total, '件'],
      ['订单总数', s.orders, '单'],
      ['成交金额', money(Math.round(s.revenue * 100)), ''],
      ['待发货', s.paid, '单']
    ];
    box.innerHTML = '';
    cells.forEach(function (c) {
      var card = el('div', 'stat-cell');
      card.appendChild(el('span', 'stat-label', c[0]));
      var v = el('span', 'stat-value');
      v.textContent = c[1];
      card.appendChild(v);
      if (c[2]) card.appendChild(el('span', 'stat-unit', c[2]));
      box.appendChild(card);
    });
  }

  function loadStats() {
    return request('/merchant/stats').then(renderStats).catch(function (e) {
      var box = $('statGrid');
      if (box) box.innerHTML = '<p class="hint">统计加载失败：' + e.message + '</p>';
    });
  }

  function loadProducts() {
    var body = $('productRows');
    if (!body) return;
    body.innerHTML = '<tr><td colspan="7" class="hint">加载中…</td></tr>';

    request('/merchant/products?limit=200').then(function (d) {
      body.innerHTML = '';
      if (!d.data.length) {
        body.innerHTML = '<tr><td colspan="7" class="hint">暂无商品</td></tr>';
        return;
      }
      d.data.forEach(function (p) {
        var tr = el('tr');
        if (!p.is_active) tr.className = 'is-off';

        var tdImg = el('td');
        var img = el('img');
        img.src = 'img/products/' + p.image;
        img.alt = '';
        img.width = 40; img.height = 40;
        img.loading = 'lazy';
        tdImg.appendChild(img);

        var tdName = el('td');
        tdName.appendChild(el('span', 'p-name', p.name));
        tdName.appendChild(el('span', 'p-slug', p.slug));

        var tdCat = el('td', 'mono', p.category);
        var tdPrice = el('td', 'mono', money(p.price_cents));

        var tdStock = el('td');
        var stockInput = el('input', 'inline-input');
        stockInput.type = 'number';
        stockInput.min = '0';
        stockInput.value = p.stock;
        stockInput.dataset.pid = p.id;
        stockInput.addEventListener('change', function () {
          patchProduct(p.id, { stock: parseInt(stockInput.value, 10) || 0 }, tr);
        });
        tdStock.appendChild(stockInput);

        var tdSales = el('td', 'mono', p.monthly_sales);

        var tdAct = el('td', 'act-cell');
        var toggle = el('button', 'mini-btn', p.is_active ? '下架' : '上架');
        toggle.type = 'button';
        toggle.addEventListener('click', function () {
          patchProduct(p.id, { is_active: !p.is_active }, tr);
        });
        tdAct.appendChild(toggle);

        tr.appendChild(tdImg);
        tr.appendChild(tdName);
        tr.appendChild(tdCat);
        tr.appendChild(tdPrice);
        tr.appendChild(tdStock);
        tr.appendChild(tdSales);
        tr.appendChild(tdAct);
        body.appendChild(tr);
      });
    }).catch(function (e) {
      body.innerHTML = '<tr><td colspan="7" class="hint">加载失败：' + e.message + '</td></tr>';
    });
  }

  function patchProduct(id, patch, rowEl) {
    if (rowEl) rowEl.classList.add('is-busy');
    request('/merchant/products/' + id, { method: 'PATCH', body: patch })
      .then(function () {
        if (rowEl) rowEl.classList.remove('is-busy');
        loadProducts();
        loadStats();
      })
      .catch(function (e) {
        if (rowEl) rowEl.classList.remove('is-busy');
        alert(e.message);
        loadProducts();
      });
  }

  var STATUS_LABEL = {
    pending: '待付款', paid: '待发货', shipped: '已发货',
    completed: '已完成', cancelled: '已取消'
  };

  function loadOrders() {
    var body = $('orderRows');
    if (!body) return;
    body.innerHTML = '<tr><td colspan="6" class="hint">加载中…</td></tr>';

    request('/merchant/orders?limit=100').then(function (d) {
      body.innerHTML = '';
      if (!d.data.length) {
        body.innerHTML = '<tr><td colspan="6" class="hint">暂无订单</td></tr>';
        return;
      }
      d.data.forEach(function (o) {
        var tr = el('tr');
        tr.appendChild(el('td', 'mono', o.order_no));

        var tdUser = el('td');
        tdUser.appendChild(el('span', 'p-name', o.username));
        tdUser.appendChild(el('span', 'p-slug', o.email));

        var tdItems = el('td');
        (o.items || []).forEach(function (it) {
          tdItems.appendChild(el('span', 'item-line', it.name_snapshot + ' ×' + it.qty));
        });

        tr.appendChild(tdUser);
        tr.appendChild(tdItems);
        tr.appendChild(el('td', 'mono', money(o.total_cents)));

        var tdSt = el('td');
        tdSt.appendChild(el('span', 'status-tag is-' + o.status, STATUS_LABEL[o.status] || o.status));
        tr.appendChild(tdSt);

        var tdAct = el('td', 'act-cell');
        if (o.status === 'paid') {
          var ship = el('button', 'mini-btn is-primary', '发货');
          ship.type = 'button';
          ship.addEventListener('click', function () {
            ship.disabled = true;
            ship.textContent = '发货中…';
            request('/orders/' + o.id + '/ship', { method: 'POST', body: { note: '' } })
              .then(function () { loadOrders(); loadStats(); loadProducts(); })
              .catch(function (e) {
                ship.disabled = false;
                ship.textContent = '发货';
                alert(e.message);
              });
          });
          tdAct.appendChild(ship);
        } else if (o.status === 'pending') {
          tdAct.appendChild(el('span', 'hint', '等待用户付款'));
        } else {
          tdAct.appendChild(el('span', 'hint', '—'));
        }
        tr.appendChild(tdAct);

        body.appendChild(tr);
      });
    }).catch(function (e) {
      body.innerHTML = '<tr><td colspan="6" class="hint">加载失败：' + e.message + '</td></tr>';
    });
  }

  // -------------------------------------------------------------------------
  // 管理员后台
  // -------------------------------------------------------------------------
  var ROLE_LABEL = { user: '普通用户', merchant: '商家', admin: '管理员' };

  function loadUsers(keyword) {
    var body = $('userRows');
    if (!body) return;
    body.innerHTML = '<tr><td colspan="6" class="hint">加载中…</td></tr>';

    var q = keyword ? '?q=' + encodeURIComponent(keyword) : '';
    request('/admin/users' + q).then(function (d) {
      body.innerHTML = '';
      if (!d.data.length) {
        body.innerHTML = '<tr><td colspan="6" class="hint">没有匹配的用户</td></tr>';
        return;
      }
      d.data.forEach(function (u) {
        var tr = el('tr');
        if (!u.is_active) tr.className = 'is-off';

        tr.appendChild(el('td', 'mono', String(u.id)));

        var tdWho = el('td');
        tdWho.appendChild(el('span', 'p-name', u.display_name || u.username));
        tdWho.appendChild(el('span', 'p-slug', u.email));
        tr.appendChild(tdWho);

        var tdRole = el('td');
        var sel = el('select', 'inline-select');
        ['user', 'merchant', 'admin'].forEach(function (r) {
          var opt = el('option', null, ROLE_LABEL[r]);
          opt.value = r;
          if (r === u.role) opt.selected = true;
          sel.appendChild(opt);
        });
        sel.addEventListener('change', function () {
          request('/admin/users/' + u.id + '/role', { method: 'PUT', body: { role: sel.value } })
            .then(function () { loadUsers(keyword); })
            .catch(function (e) { alert(e.message); loadUsers(keyword); });
        });
        tdRole.appendChild(sel);
        tr.appendChild(tdRole);

        tr.appendChild(el('td', 'mono', u.created_at ? String(u.created_at).slice(0, 10) : '—'));
        tr.appendChild(el('td', 'mono', u.last_login_at ? String(u.last_login_at).slice(0, 16) : '从未登录'));

        var tdAct = el('td', 'act-cell');
        var toggle = el('button', 'mini-btn', u.is_active ? '停用' : '启用');
        toggle.type = 'button';
        toggle.addEventListener('click', function () {
          request('/admin/users/' + u.id + '/active', { method: 'PUT' })
            .then(function () { loadUsers(keyword); })
            .catch(function (e) { alert(e.message); });
        });
        tdAct.appendChild(toggle);

        tr.appendChild(tdAct);
        body.appendChild(tr);
      });
    }).catch(function (e) {
      body.innerHTML = '<tr><td colspan="6" class="hint">加载失败：' + e.message + '</td></tr>';
    });
  }

  // -------------------------------------------------------------------------
  // 启动
  // -------------------------------------------------------------------------
  function init() {
    var page = document.body.dataset.adminPage;

    if (page === 'merchant') {
      requireRole('merchant').then(function () {
        loadStats(); loadProducts(); loadOrders();
      }).catch(function () { /* 已在 requireRole 内处理跳转/拦截 */ });
      return;
    }

    if (page === 'admin') {
      requireRole('admin').then(function () {
        loadUsers('');
        var search = $('userSearch');
        if (search) {
          var t = null;
          search.addEventListener('input', function () {
            clearTimeout(t);
            t = setTimeout(function () { loadUsers(search.value.trim()); }, 300);
          });
        }
      }).catch(function () { /* 同上 */ });
      return;
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
