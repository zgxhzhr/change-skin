class ThemeSwitcher {
    constructor() {
        this.logo = document.querySelector('.logo');
        this.themeTabs = document.querySelector('.theme-tabs');
        this.root = document.documentElement;
        this.pendingTheme = null;
        this.pendingLogo = null;
        this.pendingTab = null;
        this.themeMap = {
            red:    { '--theme-color': '#ff0000', '--theme-color-dark': '#cc0000' },
            green:  { '--theme-color': '#00c800', '--theme-color-dark': '#008a00' },
            blue:   { '--theme-color': '#0040ff', '--theme-color-dark': '#002db3' },
            orange: { '--theme-color': '#ff6f00', '--theme-color-dark': '#cc5800' },
            purple: { '--theme-color': '#7A0080', '--theme-color-dark': '#5a0060' }
        };
        this.themeLabelMap = {
            red: '炽热红', green: '森绿', blue: '深空蓝', orange: '活力橙', purple: '紫晶'
        };
        this.modal = new MulModal({
            root: '#modal-mask-theme',
            onConfirm: () => {
                if (this.pendingTheme) {
                    this.switchTheme(this.pendingTheme, this.pendingLogo);
                    this.setActive(this.pendingTab);
                    this.updateAria(this.pendingTab);
                }
            }
        });
    }

    bindEvents() {
        this.themeTabs?.addEventListener('click', (e) => {
            const tab = e.target.closest('.theme-tab');
            if (!tab) return;
            if (tab.classList.contains('active')) return;
            this.pendingTheme = tab.dataset.theme;
            this.pendingLogo = tab.dataset.logo;
            this.pendingTab = tab;
            const label = this.themeLabelMap[tab.dataset.theme] || tab.dataset.theme;
            document.getElementById('themeNameLabel').textContent = label;
            this.modal.show();
        });
    }

    switchTheme(color, logoFile) {
        const vars = this.themeMap[color];
        if (vars) {
            Object.entries(vars).forEach(([key, val]) => {
                this.root.style.setProperty(key, val);
            });
        }
        if (logoFile) this.logo.src = `./img/${logoFile}`;
    }

    setActive(target) {
        this.themeTabs?.querySelectorAll('.theme-tab').forEach(tab => {
            tab.classList.toggle('active', tab === target);
        });
    }

    updateAria(target) {
        this.themeTabs?.querySelectorAll('.theme-tab').forEach(tab => {
            tab.setAttribute('aria-selected', tab === target ? 'true' : 'false');
        });
    }
}

class Navigation {
    constructor() {
        this.navMenu = document.querySelector('.nav-menu');
    }

    bindEvents() {
        this.navMenu?.addEventListener('click', (e) => {
            const link = e.target.closest('a');
            if (!link) return;

            const li = link.parentElement;
            const hasSub = li?.querySelector(':scope > .submenu');

            if (hasSub) {
                // 父级菜单项：点击切换子菜单展开/收起
                e.preventDefault();
                this.setActive(link);
                li.classList.toggle('expanded');
                return;
            }

            // 叶子链接：仅记录选中状态，不跳转
            e.preventDefault();
            this.setActive(link);
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.navMenu?.querySelectorAll('a.active').forEach(a => a.classList.remove('active'));
                this.navMenu?.querySelectorAll('.expanded').forEach(el => el.classList.remove('expanded'));
            }
        });
    }

    setActive(target) {
        this.navMenu?.querySelectorAll('a').forEach(a => a.classList.remove('active'));
        target?.classList?.add('active');
    }
}

class Hamburger {
    constructor() {
        this.nav = document.querySelector('.nav');
        this.btn = this.nav?.querySelector('.hamburger');
        this.navMenu = this.nav?.querySelector('.nav-menu');
    }

    bindEvents() {
        this.btn?.addEventListener('click', () => this.toggle());

        this.navMenu?.addEventListener('click', (e) => {
            const link = e.target.closest('a');
            const li = link?.parentElement;
            const hasSub = li?.querySelector(':scope > .submenu');
            // 点击含子菜单的父级项时不关闭整个菜单（由 Navigation 负责展开/收起子菜单）
            if (link && !hasSub && this.nav?.classList.contains('open')) {
                this.close();
            }
        });
    }

    toggle() {
        const isOpen = this.nav?.classList.toggle('open');
        this.btn?.classList.toggle('active', isOpen);
        this.btn?.setAttribute('aria-expanded', String(!!isOpen));
    }

    open() {
        this.nav?.classList.add('open');
        this.btn?.classList.add('active');
        this.btn?.setAttribute('aria-expanded', 'true');
    }

    close() {
        this.nav?.classList.remove('open');
        this.btn?.classList.remove('active');
        this.btn?.setAttribute('aria-expanded', 'false');
    }
}

class DebugToggle {
    constructor() {
        this.btn = document.getElementById('debugToggle');
    }

    bindEvents() {
        this.btn?.addEventListener('click', () => {
            const isMobile = document.body.classList.toggle('mobile-view');
            this.btn.textContent = isMobile ? '🖥️' : '📱';
            this.btn.title = isMobile ? '切换回横屏' : '切换竖屏调试';
        });
    }
}

/**
 * 视觉风格切换：漫画分镜 / 和风浮世绘 / 手帐文具
 * 只切换 body 上的 visual-* 类，不重建 DOM，不影响任何交互逻辑
 */
class VisualSwitcher {
    constructor() {
        this.buttons = Array.from(document.querySelectorAll('.visual-btn'));
        this.body = document.body;
        this.themes = ['manga', 'wafu', 'stationery'];
        this.storageKey = 'shopmod-visual-style';
    }

    bindEvents() {
        this.buttons.forEach(btn => {
            btn.addEventListener('click', () => this.switch(btn.dataset.visual));
        });

        // 支持 ?visual=wafu 直接指定风格（便于分享/调试）
        let fromUrl = null;
        try { fromUrl = new URLSearchParams(location.search).get('visual'); } catch (e) { /* 忽略 */ }
        if (fromUrl && this.themes.includes(fromUrl)) {
            this.switch(fromUrl, true);
            return;
        }

        // 恢复上次选择（默认漫画风）
        let saved = null;
        try { saved = localStorage.getItem(this.storageKey); } catch (e) { /* 隐私模式忽略 */ }
        if (saved && this.themes.includes(saved)) this.switch(saved, true);
    }

    switch(name, silent) {
        if (!this.themes.includes(name)) return;

        this.themes.forEach(n => this.body.classList.remove('visual-' + n));
        this.body.classList.add('visual-' + name);

        this.buttons.forEach(b => {
            const on = b.dataset.visual === name;
            b.classList.toggle('active', on);
            b.setAttribute('aria-pressed', String(on));
        });

        if (!silent) {
            try { localStorage.setItem(this.storageKey, name); } catch (e) { /* 忽略 */ }
        }
    }
}

class ContentTabs {
    constructor() {
        this.tabs = document.querySelector('.content-tabs');
        this.panels = document.querySelector('.content-panels');
    }

    bindEvents() {
        this.tabs?.addEventListener('click', (e) => {
            const tab = e.target.closest('.content-tab');
            if (!tab) return;
            this.switch(tab.dataset.tab);
        });
    }

    switch(name) {
        this.tabs?.querySelectorAll('.content-tab').forEach(t => {
            const match = t.dataset.tab === name;
            t.classList.toggle('active', match);
            t.setAttribute('aria-selected', String(match));
        });
        this.panels?.querySelectorAll('.content-panel').forEach(p => {
            p.classList.toggle('active', p.dataset.tab === name);
        });
    }
}

class ImageCarousel {
    constructor() {
        this.list = document.getElementById('carouselList');
        if (!this.list) return;
        this.id = null;
        this.offset = 0;
        this.speed = 0.5;
        this.originalWidth = 0;
        this.clone = false;
    }

    bindEvents() {
        if (!this.list) return;
        this.list.appendChild(this.list.cloneNode(true));
        this.originalWidth = this.list.scrollWidth / 2;
        this.clone = true;

        this.animate = this.animate.bind(this);
        this.start = this.start.bind(this);
        this.stop = this.stop.bind(this);

        this.list.addEventListener('mouseenter', this.stop);
        this.list.addEventListener('mouseleave', this.start);

        this.start();
    }

    animate() {
        this.offset += this.speed;
        if (this.offset >= this.originalWidth) {
            this.offset -= this.originalWidth;
        }
        this.list.style.transform = `translateX(-${this.offset}px)`;
        this.id = requestAnimationFrame(this.animate);
    }

    start() {
        if (!this.id) this.id = requestAnimationFrame(this.animate);
    }

    stop() {
        if (this.id) {
            cancelAnimationFrame(this.id);
            this.id = null;
        }
    }
}

class ModalsInit {
    constructor() {
        this.previewModal = new MulModal({ root: '#modal-mask-preview' });
        this.contactModal = new MulModal({
            root: '#modal-mask-contact',
            onConfirm: () => {
                const name = document.getElementById('contactName')?.value.trim();
                const email = document.getElementById('contactEmail')?.value.trim();
                const msg = document.getElementById('contactMsg')?.value.trim();
                if (!name || !email || !msg) { alert('请填写完整信息'); return; }
                alert(`留言已提交！\n姓名：${name}\n邮箱：${email}`);
                document.getElementById('contactName').value = '';
                document.getElementById('contactEmail').value = '';
                document.getElementById('contactMsg').value = '';
            },
            onCancel: () => alert('操作已取消')
        });
        this.checkoutModal = new MulModal({
            root: '#modal-mask-checkout',
            onConfirm: () => {
                const addr = document.getElementById('ckAddr')?.value.trim();
                const phone = document.getElementById('ckPhone')?.value.trim();
                const qty = document.getElementById('ckQty')?.value || '1';
                if (!addr || !phone) { alert('请填写收货地址和联系电话'); return; }
                alert(`订单提交成功！\n地址：${addr}\n电话：${phone}\n数量：${qty}`);
            },
            onCancel: () => alert('操作已取消')
        });
    }

    bindEvents() {
        document.getElementById('aboutLink')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.contactModal.show();
        });
        document.getElementById('heroBuyBtn')?.addEventListener('click', () => {
            this.checkoutModal.show();
        });
        document.getElementById('carouselList')?.addEventListener('click', (e) => {
            const img = e.target.closest('img');
            if (!img) return;
            const previewImg = document.getElementById('previewImg');
            if (previewImg) { previewImg.src = img.src; previewImg.alt = img.alt; }
            this.previewModal.show();
        });
    }
}

const init = () => {
    [
        ThemeSwitcher,
        Navigation,
        Hamburger,
        DebugToggle,
        VisualSwitcher,
        ContentTabs,
        ImageCarousel,
        BannerCarousel
    ].forEach(Cls => new Cls().bindEvents());

    new ModalsInit().bindEvents();
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}