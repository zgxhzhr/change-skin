/* ==========================================================
   BannerCarousel — 导航上方的主题轮播图
   水平滑动 · 首尾克隆无缝循环 · 自动播放 · 圆点/箭头/拖拽/键盘
   ========================================================== */

class BannerCarousel {
    constructor() {
        this.root = document.getElementById('bannerCarousel');
        this.track = document.getElementById('bannerTrack');
        this.dotsBox = document.getElementById('bannerDots');
        this.total = this.track ? this.track.children.length : 0;

        this.index = 1;          // 实际从 1 开始（0 是克隆的末尾图）
        this.timer = null;
        this.delay = 4000;
        this.dots = [];
        this.dragStartX = 0;
        this.dragging = false;
    }

    bindEvents() {
        if (!this.root || !this.track || this.total < 2) return;

        /* 首尾各克隆一张：滑到最后一张的下一张是克隆首图，
           滑到第一张的上一张是克隆尾图，视觉上形成无缝循环 */
        const originals = [...this.track.children];
        this.track.appendChild(originals[0].cloneNode(true));
        this.track.insertBefore(originals[this.total - 1].cloneNode(true), originals[0]);

        this.buildDots();
        this.goTo(1, false);

        this.root.querySelector('.banner-prev')?.addEventListener('click', () => this.prev());
        this.root.querySelector('.banner-next')?.addEventListener('click', () => this.next());

        /* 悬停 / 聚焦暂停 */
        this.root.addEventListener('mouseenter', () => this.pause());
        this.root.addEventListener('mouseleave', () => this.play());
        this.root.addEventListener('focusin', () => this.pause());
        this.root.addEventListener('focusout', () => this.play());

        /* 键盘 */
        this.root.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft') {
                e.preventDefault();
                this.prev();
            } else if (e.key === 'ArrowRight') {
                e.preventDefault();
                this.next();
            }
        });

        /* 拖拽 / 滑动 */
        this.root.addEventListener('pointerdown', (e) => {
            if (e.target.closest('a, button')) return;
            this.dragging = true;
            this.dragStartX = e.clientX;
        });

        this.root.addEventListener('pointerup', (e) => {
            if (!this.dragging) return;
            this.dragging = false;
            const dx = e.clientX - this.dragStartX;
            if (Math.abs(dx) > 40) {
                dx < 0 ? this.next() : this.prev();
            }
        });

        this.root.addEventListener('pointercancel', () => {
            this.dragging = false;
        });

        /* 滑到克隆页后无动画跳回真实页 */
        this.track.addEventListener('transitionend', () => this.onTransitionEnd());

        /* 切到后台标签页暂停 */
        document.addEventListener('visibilitychange', () => {
            document.hidden ? this.pause() : this.play();
        });

        this.play();
    }

    buildDots() {
        for (let i = 0; i < this.total; i++) {
            const dot = document.createElement('button');
            dot.type = 'button';
            dot.className = 'banner-dot';
            dot.setAttribute('role', 'tab');
            dot.setAttribute('aria-label', `第 ${i + 1} 张`);
            dot.addEventListener('click', () => {
                this.goTo(i + 1);
                this.restart();
            });
            this.dotsBox.appendChild(dot);
            this.dots.push(dot);
        }
    }

    /* 根据当前 index 更新圆点和主题色 */
    update() {
        const real = (this.index - 1 + this.total) % this.total;

        this.dots.forEach((dot, i) => {
            dot.classList.toggle('active', i === real);
            dot.setAttribute('aria-selected', String(i === real));
        });

        const slide = this.track.children[this.index];
        const color = slide?.dataset.color;
        if (color) this.root.style.setProperty('--banner-accent', color);

        /* 只让当前这张可交互、可被读屏识别 */
        [...this.track.children].forEach((item, i) => {
            const active = i === this.index;
            item.setAttribute('aria-hidden', String(!active));
            if (active) {
                item.removeAttribute('inert');
            } else {
                item.setAttribute('inert', '');
            }
        });
    }

    goTo(index, animate = true) {
        if (!this.track) return;

        // 索引钳制。track 结构：[克隆尾图, 1..total, 克隆首图]
        // 合法索引只有 0..total+1。越界时 translateX 会把所有 slide
        // 推出视口 —— 表现就是「连点几次下一张，图全白了」。
        if (!Number.isFinite(index)) index = 1;
        if (index < 0) index = 0;
        if (index > this.total + 1) index = this.total + 1;

        this.index = index;
        this.track.style.transition = animate ? '' : 'none';
        this.track.style.transform = `translateX(-${this.index * 100}%)`;

        if (!animate) {
            void this.track.offsetWidth; // 强制重排，让跳转不产生动画
            this.track.style.transition = '';
        }

        this.update();
    }

    onTransitionEnd() {
        if (this.index === 0) {
            this.goTo(this.total, false);
        } else if (this.index === this.total + 1) {
            this.goTo(1, false);
        }
    }

    next() {
        // 已经在克隆首图：先无动画跳回真实首图，再前进。
        // 连点时 transitionend 可能被新的 transition 打断而不触发，
        // 只依赖 onTransitionEnd 复位会漏掉，这里主动兜住。
        if (this.index >= this.total + 1) {
            this.goTo(1, false);
            void this.track.offsetWidth;
        }
        this.goTo(this.index + 1);
        this.restart();
    }

    prev() {
        if (this.index <= 0) {
            this.goTo(this.total, false);
            void this.track.offsetWidth;
        }
        this.goTo(this.index - 1);
        this.restart();
    }

    play() {
        this.pause();
        if (document.hidden) return;
        this.timer = setInterval(() => {
            // 自动播放同样要兜边界：切到后台标签页时 transitionend 不触发，
            // index 会一直累加，回来后就是一片空白。
            if (this.index >= this.total + 1) {
                this.goTo(1, false);
            }
            this.goTo(this.index + 1);
        }, this.delay);
    }

    pause() {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }
    }

    restart() {
        this.pause();
        this.play();
    }
}
