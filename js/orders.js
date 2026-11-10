/**
 * 购买流程：商品卡 → 结算弹窗 → 下单 → 我的订单 → 付款 / 发货
 *
 * 依赖后端（backend/app.py）：
 *   GET  /api/v1/products             取商品（含 id，静态 HTML 里没有 id）
 *   POST /api/v1/orders               下单
 *   GET  /api/v1/orders               我的订单
 *   POST /api/v1/orders/{id}/pay      声明已付款
 *   POST /api/v1/orders/{id}/ship     发货（扣库存 + 加销量）
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
  var API_BASE = API_ORIGIN + '/api/v1';
  var TOKEN_KEY = 'cs_token';

  var state = {
    products: [],          // 全部商品
    byName: {},            // 商品名 → 商品对象
    current: null,         // 当前结算商品
    qty: 1,
    orders: []
  };

  function $(id) { return document.getElementById(id); }

  function readToken() {
    try {
      return localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY) || '';
    } catch (e) { return ''; }
  }

  function authHeaders() {
    var token = readToken();
    return token ? { Authorization: 'Bearer ' + token } : {};
  }

  function request(path, options) {
    options = options || {};
    var headers = Object.assign({ 'Content-Type': 'application/json' }, authHeaders(), options.headers || {});
    return fetch(API_BASE + path, {
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

  function money(cents) {
    return '¥' + (cents / 100).toFixed(2);
  }

  // -------------------------------------------------------------------------
  // 商品数据：静态 HTML 里没有 product_id，靠名字与后端对应
  // -------------------------------------------------------------------------
  function loadProducts() {
    return request('/products?limit=100').then(function (data) {
      state.products = data.data || [];
      state.products.forEach(function (p) {
        state.byName[p.name] = p;
      });
    }).catch(function () { /* 后端不可用时静默降级 */ });
  }

  // -------------------------------------------------------------------------
  // 结算弹窗
  // -------------------------------------------------------------------------
  function openCheckout(product) {
    // 没有商品上下文时不要打开空结算窗（否则显示「请选择商品 / ¥0」）
    if (!product || !product.id) {
      alert('请先在商品列表里点选要购买的商品');
      return;
    }
    if (!readToken()) {
      location.href = 'login.html?next=checkout';
      return;
    }
    state.current = product;
    state.qty = 1;

    $('ckItemImg').src = 'img/products/' + product.image;
    $('ckItemImg').alt = product.name;
    $('ckItemName').textContent = product.name;
    $('ckItemPrice').textContent = money(product.price_cents);
    $('ckQty').value = 1;
    $('ckError').textContent = '';
    updateTotal();

    var mask = $('modal-mask-checkout');
    if (mask && window.CSModal) {
      window.CSModal.show('modal-mask-checkout');
    } else if (mask) {
      mask.style.display = 'flex';
      mask.style.opacity = '1';
      mask.style.pointerEvents = 'auto';
    }
  }

  function updateTotal() {
    if (!state.current) return;
    var cents = state.current.price_cents * state.qty;
    $('ckTotal').textContent = money(cents);
  }

  function setQty(n) {
    var stock = state.current ? state.current.stock : 99;
    n = Math.max(1, Math.min(99, Math.min(stock || 99, n)));
    state.qty = n;
    $('ckQty').value = n;
    updateTotal();
  }

  function submitOrder() {
    var btn = $('ckSubmit');
    var errEl = $('ckError');
    var addr = $('ckAddr').value.trim();
    var phone = $('ckPhone').value.trim();

    if (!state.current) { errEl.textContent = '请选择商品'; return; }
    if (addr.length < 5) { errEl.textContent = '请填写完整收货地址'; $('ckAddr').focus(); return; }
    if (phone.length < 6) { errEl.textContent = '请填写有效联系电话'; $('ckPhone').focus(); return; }

    errEl.textContent = '';
    btn.disabled = true;
    btn.textContent = '提交中…';

    request('/orders', {
      method: 'POST',
      body: {
        items: [{ product_id: state.current.id, qty: state.qty }],
        addr: addr,
        phone: phone
      }
    }).then(function (order) {
      btn.disabled = false;
      btn.textContent = '提交订单';
      closeCheckout();
      // 直接去订单页，让用户在那里点「我已付款」
      location.href = 'orders.html?new=' + order.order_no;
    }).catch(function (err) {
      btn.disabled = false;
      btn.textContent = '提交订单';
      if (err.status === 401) {
        location.href = 'login.html?next=checkout';
        return;
      }
      errEl.textContent = err.message;
    });
  }

  function closeCheckout() {
    var mask = $('modal-mask-checkout');
    if (mask && window.CSModal) {
      window.CSModal.hide('modal-mask-checkout');
    } else if (mask) {
      mask.style.display = 'none';
    }
  }

  // -------------------------------------------------------------------------
  // 我的订单页（orders.html）
  // -------------------------------------------------------------------------
  var STATUS_LABEL = {
    pending: '待付款',
    paid: '已付款 · 待发货',
    shipped: '已发货',
    completed: '已完成',
    cancelled: '已取消'
  };

  function renderOrders() {
    var wrap = $('orderList');
    if (!wrap) return;

    if (!readToken()) {
      wrap.innerHTML = '<p class="ord-empty">请先 <a href="login.html">登录</a> 后查看订单。</p>';
      return;
    }

    wrap.innerHTML = '<p class="ord-empty">加载中…</p>';

    request('/orders?limit=50').then(function (data) {
      state.orders = data.data || [];
      if (!state.orders.length) {
        wrap.innerHTML = '<p class="ord-empty">还没有订单。<a href="index.html">去逛逛</a></p>';
        return;
      }

      wrap.innerHTML = '';
      state.orders.forEach(function (o) {
        wrap.appendChild(renderOrderCard(o));
      });
    }).catch(function (err) {
      wrap.innerHTML = '<p class="ord-empty">加载失败：' + err.message + '</p>';
    });
  }

  function renderOrderCard(o) {
    var card = document.createElement('article');
    card.className = 'ord-card';
    card.dataset.orderId = o.id;

    var head = document.createElement('div');
    head.className = 'ord-head';
    head.innerHTML =
      '<span class="ord-no">' + o.order_no + '</span>' +
      '<span class="ord-status is-' + o.status + '">' + (STATUS_LABEL[o.status] || o.status) + '</span>';

    var items = document.createElement('ul');
    items.className = 'ord-items';
    o.items.forEach(function (it) {
      var li = document.createElement('li');
      li.innerHTML =
        '<img src="img/products/' + (it.image_snapshot || '') + '" alt="" width="44" height="44" loading="lazy">' +
        '<span class="ord-item-name">' + it.name_snapshot + '</span>' +
        '<span class="ord-item-qty">×' + it.qty + '</span>' +
        '<span class="ord-item-price">' + money(it.price_cents) + '</span>';
      items.appendChild(li);
    });

    var foot = document.createElement('div');
    foot.className = 'ord-foot';
    foot.innerHTML =
      '<span class="ord-addr">' + (o.addr || '') + '　' + (o.phone || '') + '</span>' +
      '<span class="ord-total">合计 <strong>' + money(o.total_cents) + '</strong></span>';

    var actions = document.createElement('div');
    actions.className = 'ord-actions';

    if (o.status === 'pending') {
      var payBtn = document.createElement('button');
      payBtn.type = 'button';
      payBtn.className = 'ord-btn ord-btn-pay';
      payBtn.textContent = '我已付款';
      payBtn.addEventListener('click', function () { actOnOrder(o.id, 'pay', payBtn); });
      actions.appendChild(payBtn);
    } else if (o.status === 'paid') {
      var shipBtn = document.createElement('button');
      shipBtn.type = 'button';
      shipBtn.className = 'ord-btn ord-btn-ship';
      shipBtn.textContent = '发货';
      shipBtn.addEventListener('click', function () { actOnOrder(o.id, 'ship', shipBtn); });
      actions.appendChild(shipBtn);
    } else if (o.status === 'shipped') {
      var done = document.createElement('span');
      done.className = 'ord-done';
      done.textContent = '已于 ' + (o.shipped_at || '').replace('T', ' ').slice(0, 16) + ' 发货';
      actions.appendChild(done);
    }

    card.appendChild(head);
    card.appendChild(items);
    card.appendChild(foot);
    if (actions.children.length) card.appendChild(actions);
    return card;
  }

  function actOnOrder(orderId, action, btn) {
    var label = action === 'pay' ? '我已付款' : '发货';
    btn.disabled = true;
    btn.textContent = '处理中…';

    request('/orders/' + orderId + '/' + action, {
      method: 'POST',
      body: action === 'ship' ? { note: '' } : undefined
    }).then(function () {
      renderOrders();
    }).catch(function (err) {
      btn.disabled = false;
      btn.textContent = label;
      alert(err.message);
    });
  }

  // -------------------------------------------------------------------------
  // 启动
  // -------------------------------------------------------------------------
  function init() {
    // 商品卡点击 → 打开结算（只处理「立即购买」）
    document.addEventListener('click', function (e) {
      var buy = e.target.closest('[data-buy-product]');
      if (buy) {
        e.preventDefault();
        var name = buy.getAttribute('data-buy-product');
        var p = state.byName[name];
        if (p) openCheckout(p);
        else alert('商品数据还没加载好，请稍候再试');
        return;
      }
      // 也支持直接点商品卡本身
      var card = e.target.closest('.product-item');
      if (card && !e.target.closest('a, button')) {
        var nameEl = card.querySelector('.product-name');
        if (nameEl) {
          var p2 = state.byName[nameEl.textContent.trim()];
          if (p2) { e.preventDefault(); openCheckout(p2); }
        }
      }
    });

    // 数量加减
    var minus = $('qtyMinus');
    var plus = $('qtyPlus');
    var qtyInput = $('ckQty');
    if (minus) minus.addEventListener('click', function () { setQty(state.qty - 1); });
    if (plus) plus.addEventListener('click', function () { setQty(state.qty + 1); });
    if (qtyInput) qtyInput.addEventListener('input', function () {
      var n = parseInt(qtyInput.value, 10);
      if (!isNaN(n)) setQty(n);
    });

    // 提交订单
    var submit = $('ckSubmit');
    if (submit) submit.addEventListener('click', submitOrder);

    // 订单页
    if ($('orderList')) renderOrders();

    loadProducts();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
