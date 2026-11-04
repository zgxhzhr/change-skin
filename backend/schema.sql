-- ============================================================================
-- change-skin 商城后端 · 数据库结构
-- 目标库：change_skin
-- 兼容：MySQL 5.5+ / 8.0+（不使用 JSON 类型、窗口函数、CTE）
-- 字符集：utf8mb4（中文商品名、emoji）
-- ============================================================================

CREATE DATABASE IF NOT EXISTS change_skin
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE change_skin;

-- ---------------------------------------------------------------------------
-- 用户
-- password_hash 存 PBKDF2-HMAC-SHA256 的 "算法$迭代$盐$摘要" 串，
-- 绝不存明文，也绝不存可逆加密。
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id              INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    email           VARCHAR(190)    NOT NULL,
    username        VARCHAR(50)     NOT NULL,
    password_hash   VARCHAR(255)    NOT NULL,
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    failed_attempts SMALLINT        NOT NULL DEFAULT 0,
    locked_until    DATETIME        NULL,
    last_login_at   DATETIME        NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_users_email (email),
    UNIQUE KEY uk_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 会话（服务端会话表，不把用户信息塞进前端可读的 token 里）
-- token 只存哈希，库泄露也无法直接冒用。
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    token_hash  CHAR(64)        NOT NULL,          -- SHA-256 hex
    user_id     INT UNSIGNED    NOT NULL,
    ip          VARCHAR(45)     NULL,
    user_agent  VARCHAR(255)    NULL,
    expires_at  DATETIME        NOT NULL,
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at  DATETIME        NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_sessions_token (token_hash),
    KEY idx_sessions_user (user_id),
    KEY idx_sessions_expires (expires_at),
    CONSTRAINT fk_sessions_user FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 商品（从静态 HTML 搬进库，前端改调 API）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id           INT UNSIGNED   NOT NULL AUTO_INCREMENT,
    slug         VARCHAR(80)    NOT NULL,
    name         VARCHAR(120)   NOT NULL,
    description  TEXT           NULL,
    price_cents  INT UNSIGNED   NOT NULL,            -- 分，避免浮点误差
    category     VARCHAR(40)    NOT NULL DEFAULT 'other',
    image        VARCHAR(160)   NOT NULL,
    badge        VARCHAR(20)    NULL,                -- hot / new / sale
    monthly_sales INT UNSIGNED  NOT NULL DEFAULT 0,
    rating       DECIMAL(4,1)   NOT NULL DEFAULT 0.0,
    stock        INT UNSIGNED   NOT NULL DEFAULT 0,
    is_active    TINYINT(1)     NOT NULL DEFAULT 1,
    sort_order   INT            NOT NULL DEFAULT 0,
    created_at   DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_products_slug (slug),
    KEY idx_products_category (category, is_active),
    KEY idx_products_sort (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 用户偏好：把「5 色主题 + 6 套视觉风格」的选择存到账号上，
-- 换设备登录后自动恢复。
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id      INT UNSIGNED NOT NULL,
    theme        VARCHAR(20)  NOT NULL DEFAULT 'purple',
    visual_style VARCHAR(20)  NOT NULL DEFAULT 'manga',
    updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id),
    CONSTRAINT fk_pref_user FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 订单（结算弹窗接进来用）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_no    CHAR(20)        NOT NULL,
    user_id     INT UNSIGNED    NOT NULL,
    total_cents INT UNSIGNED    NOT NULL,
    status      VARCHAR(20)     NOT NULL DEFAULT 'pending',
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_orders_no (order_no),
    KEY idx_orders_user (user_id, created_at),
    CONSTRAINT fk_orders_user FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS order_items (
    id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id     BIGINT UNSIGNED NOT NULL,
    product_id   INT UNSIGNED    NOT NULL,
    name_snapshot VARCHAR(120)   NOT NULL,
    price_cents  INT UNSIGNED    NOT NULL,
    qty          SMALLINT UNSIGNED NOT NULL DEFAULT 1,
    PRIMARY KEY (id),
    KEY idx_order_items_order (order_id),
    CONSTRAINT fk_items_order FOREIGN KEY (order_id)
        REFERENCES orders (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
