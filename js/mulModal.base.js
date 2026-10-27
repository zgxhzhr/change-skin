class MulModal {
    constructor(options) {
        this.root = document.querySelector(options.root);
        if (!this.root) return;

        this.title = this.root.querySelector('.modal-title');
        this.content = this.root.querySelector('.modal-content');
        this.closeBtn = this.root.querySelector('.close-btn');
        this.cancelBtn = this.root.querySelector('.btn-cancel');
        this.confirmBtn = this.root.querySelector('.btn-confirm');

        if (options.title) this.title.textContent = options.title;
        if (options.content) this.content.innerHTML = options.content;
        if (options.confirmText) this.confirmBtn.textContent = options.confirmText;
        if (options.cancelText) this.cancelBtn.textContent = options.cancelText;

        this.options = options;
        this.bindEvents();
        this.hide();
    }

    bindEvents() {
        this.closeBtn.addEventListener('click', () => this.hide());

        this.cancelBtn.addEventListener('click', () => {
            if (this.options.onCancel) this.options.onCancel();
            this.hide();
        });

        this.confirmBtn.addEventListener('click', () => {
            if (this.options.onConfirm) this.options.onConfirm();
            this.hide();
        });

        this.root.addEventListener('click', (e) => {
            if (e.target === this.root) this.hide();
        });

        this.closeBtn.addEventListener('DOMSubtreeModified', () => {
            if (this.closeBtn.textContent !== '×') this.closeBtn.textContent = '×';
        });
    }

    show() {
        this.root.style.opacity = '1';
        this.root.style.pointerEvents = 'auto';
    }

    hide() {
        this.root.style.opacity = '0';
        this.root.style.pointerEvents = 'none';
    }
}