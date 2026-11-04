/**
 * 主题切换（子页面共用）
 *
 * 主站 index.html 用 main.js 里的 ThemeSwitcher（带确认弹窗）；
 * 登录 / 订单 / 商家后台 / 管理后台这些子页面没有弹窗那套，
 * 用这个轻量版：点一下立即换色，写 localStorage 与主站共享。
 */
(function () {
  'use strict';

  var THEMES = {
    red: {
      '--theme-color': '#ff0000', '--theme-color-dark': '#cc0000',
      '--theme-color-light': '#ff4d4d', '--theme-color-glow': 'rgba(255,0,0,.45)'
    },
    green: {
      '--theme-color': '#00c800', '--theme-color-dark': '#008a00',
      '--theme-color-light': '#33d633', '--theme-color-glow': 'rgba(0,200,0,.45)'
    },
    blue: {
      '--theme-color': '#0040ff', '--theme-color-dark': '#002db3',
      '--theme-color-light': '#4079ff', '--theme-color-glow': 'rgba(0,64,255,.45)'
    },
    orange: {
      '--theme-color': '#ff6f00', '--theme-color-dark': '#cc5800',
      '--theme-color-light': '#ff8c33', '--theme-color-glow': 'rgba(255,111,0,.45)'
    },
    purple: {
      '--theme-color': '#7A0080', '--theme-color-dark': '#5a0060',
      '--theme-color-light': '#a039a6', '--theme-color-glow': 'rgba(122,0,128,.45)'
    }
  };

  var STORAGE_KEY = 'shopmod-theme';

  function apply(name) {
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

    try { localStorage.setItem(STORAGE_KEY, name); } catch (e) { /* 忽略 */ }
  }

  function init() {
    var saved = null;
    var fromUrl = null;
    try { saved = localStorage.getItem(STORAGE_KEY); } catch (e) { /* 忽略 */ }
    try { fromUrl = new URLSearchParams(location.search).get('theme'); } catch (e) { /* 忽略 */ }

    var initial = (fromUrl && THEMES[fromUrl]) ? fromUrl
      : (saved && THEMES[saved]) ? saved
        : 'purple';
    apply(initial);

    document.querySelectorAll('.theme-tab').forEach(function (tab) {
      tab.addEventListener('click', function () {
        apply(tab.dataset.theme);
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
