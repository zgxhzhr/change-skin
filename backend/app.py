"""
change-skin 商城后端 · FastAPI 应用

路由全部挂在 /api/v1 下，统一版本前缀。
错误响应遵循 RFC 7807（application/problem+json）。

启动：
    python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
"""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import db
import mailer
from security import (
    burn_time,
    hash_password,
    hash_token,
    is_valid_email,
    is_valid_username,
    new_session_token,
    password_strength_error,
    session_expiry,
    verify_password,
)
from db import MAX_FAILED_ATTEMPTS, LOCK_MINUTES

app = FastAPI(
    title="change-skin API",
    version="1.0.0",
    description="异世界商城后端：认证、商品、用户偏好",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=db.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# ---------------------------------------------------------------------------
# RFC 7807 错误
# ---------------------------------------------------------------------------
def problem(status: int, title: str, detail: str, type_slug: str = "about:blank",
            extra: dict[str, Any] | None = None) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://change-skin.local/errors/{type_slug}" if type_slug != "about:blank" else "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
    }
    if extra:
        body.update(extra)
    return JSONResponse(status_code=status, content=body,
                        media_type="application/problem+json")


# ---------------------------------------------------------------------------
# 开发期缓存策略
# python http.server / StaticFiles 都不发 Cache-Control，浏览器按启发式缓存，
# 结果改了 CSS 但 HTML 里的 ?v= 版本号没更新 -> 一直加载旧样式。
# 这里给 HTML 加 no-cache；静态资源仍靠 ?v= 控制。
# ---------------------------------------------------------------------------
@app.middleware("http")
async def dev_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith(".html"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    slug = {
        400: "validation-error",
        401: "unauthorized",
        403: "forbidden",
        404: "not-found",
        409: "conflict",
        422: "validation-error",
        429: "too-many-requests",
    }.get(exc.status_code, "error")
    return problem(exc.status_code, exc.detail, exc.detail, slug)


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------
class RegisterIn(BaseModel):
    email: str = Field(..., max_length=190)
    username: str = Field(..., max_length=50)
    password: str = Field(..., max_length=128)
    code: str = Field(..., max_length=6, description="邮箱验证码")


class SendCodeIn(BaseModel):
    email: str = Field(..., max_length=190)
    purpose: str = Field("register", max_length=20)


class LoginIn(BaseModel):
    account: str = Field(..., description="邮箱或用户名", max_length=190)
    password: str = Field(..., max_length=128)


class PreferencesIn(BaseModel):
    theme: str | None = Field(None, max_length=20)
    visual_style: str | None = Field(None, max_length=20)


# ---------------------------------------------------------------------------
# 鉴权依赖
# ---------------------------------------------------------------------------
def current_user(authorization: str | None = Header(None)) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "缺少访问令牌")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(401, "缺少访问令牌")

    row = db.fetch_one(
        """
        SELECT s.user_id, s.expires_at, s.revoked_at,
               u.id, u.email, u.username, u.display_name, u.shop_name,
               u.role, u.is_active
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = %s
        """,
        (hash_token(token),),
    )
    if not row:
        raise HTTPException(401, "令牌无效")
    if row["revoked_at"] is not None:
        raise HTTPException(401, "令牌已失效")
    if row["expires_at"] < datetime.utcnow():
        raise HTTPException(401, "令牌已过期")
    if not row["is_active"]:
        raise HTTPException(403, "账号已停用")
    return row


# ---------------------------------------------------------------------------
# 邮箱验证码
# ---------------------------------------------------------------------------
CODE_TTL_MINUTES = 5          # 有效期
CODE_RESEND_SECONDS = 60      # 同邮箱重发冷却
CODE_MAX_ATTEMPTS = 5         # 单个验证码最多试错次数


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _issue_code(email: str, purpose: str, ip: str | None) -> str:
    """生成并投递验证码；返回明文（只在发信时用，不入库）。"""
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = datetime.utcnow()
    # created_at 显式写 UTC：表定义里是 DEFAULT CURRENT_TIMESTAMP（本地时间），
    # 直接依赖默认值会和 expires_at(UTC) 相差一个时区，导致冷却判断算出负数。
    db.execute(
        "INSERT INTO email_codes (email, code_hash, purpose, expires_at, created_at, ip) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (email, _hash_code(code), purpose,
         now + timedelta(minutes=CODE_TTL_MINUTES), now, ip),
    )
    return code


def _verify_code(email: str, code: str, purpose: str = "register") -> None:
    """校验并消费验证码。失败抛 HTTPException。"""
    if not code or not code.isdigit() or len(code) != 6:
        raise HTTPException(422, "验证码应为 6 位数字")

    row = db.fetch_one(
        "SELECT id, code_hash, attempts, expires_at, consumed_at "
        "FROM email_codes WHERE email = %s AND purpose = %s "
        "ORDER BY id DESC LIMIT 1",
        (email, purpose),
    )
    if not row:
        raise HTTPException(422, "请先获取邮箱验证码")
    if row["consumed_at"] is not None:
        raise HTTPException(422, "验证码已使用，请重新获取")
    if row["expires_at"] < datetime.utcnow():
        raise HTTPException(422, "验证码已过期，请重新获取")
    if row["attempts"] >= CODE_MAX_ATTEMPTS:
        raise HTTPException(429, "验证码错误次数过多，请重新获取")

    if _hash_code(code) != row["code_hash"]:
        db.execute(
            "UPDATE email_codes SET attempts = attempts + 1 WHERE id = %s",
            (row["id"],),
        )
        raise HTTPException(422, "验证码不正确")

    # 正确：标记已消费（一次性）
    db.execute(
        "UPDATE email_codes SET consumed_at = %s WHERE id = %s",
        (datetime.utcnow(), row["id"]),
    )


@app.post("/api/v1/auth/send-code")
def send_code(payload: SendCodeIn, request: Request):
    email = payload.email.strip().lower()
    purpose = payload.purpose.strip() or "register"

    if purpose not in ("register", "reset"):
        raise HTTPException(422, "未知的验证码用途")
    if not is_valid_email(email):
        raise HTTPException(422, "邮箱格式不正确")

    if purpose == "register":
        taken = db.fetch_one("SELECT id FROM users WHERE email = %s LIMIT 1", (email,))
        if taken:
            raise HTTPException(409, "该邮箱已被注册")

    # 冷却：同邮箱 60 秒内只能发一次
    recent = db.fetch_one(
        "SELECT created_at FROM email_codes WHERE email = %s AND purpose = %s "
        "ORDER BY id DESC LIMIT 1",
        (email, purpose),
    )
    if recent:
        elapsed = (datetime.utcnow() - recent["created_at"]).total_seconds()
        if elapsed < CODE_RESEND_SECONDS:
            wait = int(CODE_RESEND_SECONDS - elapsed)
            raise HTTPException(429, f"发送太频繁，请 {wait} 秒后再试")

    code = _issue_code(email, purpose, request.client.host if request.client else None)

    if not mailer.send_code(email, code, purpose):
        raise HTTPException(503, "验证码发送失败，请稍后重试或联系管理员")

    return {
        "sent": True,
        "delivery": "smtp" if mailer.is_enabled() else "console",
        "expires_in": CODE_TTL_MINUTES * 60,
        "resend_after": CODE_RESEND_SECONDS,
    }




# ---------------------------------------------------------------------------
# 角色与权限
#
#   user      普通用户：浏览、下单、付款、看自己的订单
#   merchant  商家：上架/编辑商品、查看并处理订单（发货）、看自己店铺统计
#   admin     管理员：以上全部 + 用户管理与角色分配
# ---------------------------------------------------------------------------
ROLE_USER = "user"
ROLE_MERCHANT = "merchant"
ROLE_ADMIN = "admin"
ALL_ROLES = (ROLE_USER, ROLE_MERCHANT, ROLE_ADMIN)


def require_role(*allowed: str):
    """依赖工厂：只放行指定角色，其余 403。"""
    def _dep(user: dict = Depends(current_user)) -> dict:
        if user.get("role") not in allowed:
            raise HTTPException(403, "当前账号没有这个操作的权限")
        return user
    return _dep


require_merchant = require_role(ROLE_MERCHANT, ROLE_ADMIN)
require_admin = require_role(ROLE_ADMIN)


# ---------------------------------------------------------------------------
# 认证
# ---------------------------------------------------------------------------
@app.post("/api/v1/auth/register", status_code=201)
def register(payload: RegisterIn):
    email = payload.email.strip().lower()
    username = payload.username.strip()

    if not is_valid_email(email):
        raise HTTPException(422, "邮箱格式不正确")
    if not is_valid_username(username):
        raise HTTPException(422, "用户名需 2-20 位，支持字母数字下划线中文")
    err = password_strength_error(payload.password)
    if err:
        raise HTTPException(422, err)

    # 验证码必须先过
    _verify_code(email, payload.code.strip(), "register")

    exists = db.fetch_one(
        "SELECT id FROM users WHERE email = %s OR username = %s LIMIT 1",
        (email, username),
    )
    if exists:
        raise HTTPException(409, "该邮箱或用户名已被注册")

    user_id = db.execute(
        "INSERT INTO users (email, username, password_hash, role) VALUES (%s, %s, %s, %s)",
        (email, username, hash_password(payload.password), ROLE_USER),
    )
    db.execute(
        "INSERT INTO user_preferences (user_id, theme, visual_style) VALUES (%s, %s, %s) "
        "ON DUPLICATE KEY UPDATE user_id = user_id",
        (user_id, "purple", "manga"),
    )

    token, _ = new_session_token()
    db.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
        (hash_token(token), user_id, session_expiry(db.SESSION_TTL_HOURS)),
    )
    return {
        "token": token,
        "user": {"id": user_id, "email": email, "username": username, "role": ROLE_USER},
    }


@app.post("/api/v1/auth/login")
def login(payload: LoginIn):
    account = payload.account.strip().lower()

    row = db.fetch_one(
        "SELECT id, email, username, password_hash, role, is_active, failed_attempts, locked_until "
        "FROM users WHERE email = %s OR username = %s LIMIT 1",
        (account, payload.account.strip()),
    )

    # 用户不存在也跑一次哈希，避免时序侧信道
    if not row:
        burn_time(payload.password)
        raise HTTPException(401, "账号或密码错误")

    # 锁定检查
    if row["locked_until"] and row["locked_until"] > datetime.utcnow():
        raise HTTPException(429, f"失败次数过多，请 {LOCK_MINUTES} 分钟后再试")

    if not verify_password(payload.password, row["password_hash"]):
        attempts = row["failed_attempts"] + 1
        if attempts >= MAX_FAILED_ATTEMPTS:
            db.execute(
                "UPDATE users SET failed_attempts = %s, locked_until = %s WHERE id = %s",
                (0, datetime.utcnow().replace(microsecond=0), row["id"]),
            )
            raise HTTPException(429, f"失败次数过多，账号已锁定 {LOCK_MINUTES} 分钟")
        db.execute(
            "UPDATE users SET failed_attempts = %s WHERE id = %s",
            (attempts, row["id"]),
        )
        raise HTTPException(401, "账号或密码错误")

    if not row["is_active"]:
        raise HTTPException(403, "账号已停用")

    # 成功：清计数、记登录时间、发新 token
    db.execute(
        "UPDATE users SET failed_attempts = 0, locked_until = NULL, last_login_at = %s WHERE id = %s",
        (datetime.utcnow(), row["id"]),
    )
    token, _ = new_session_token()
    db.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
        (hash_token(token), row["id"], session_expiry(db.SESSION_TTL_HOURS)),
    )
    return {
        "token": token,
        "user": {
            "id": row["id"], "email": row["email"], "username": row["username"],
            "role": row.get("role", ROLE_USER),
        },
    }


@app.post("/api/v1/auth/logout", status_code=204)
def logout(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "缺少访问令牌")
    token = authorization[7:].strip()
    db.execute(
        "UPDATE sessions SET revoked_at = %s WHERE token_hash = %s",
        (datetime.utcnow(), hash_token(token)),
    )
    return None


@app.get("/api/v1/auth/me")
def me(user: dict = Depends(current_user)):
    pref = db.fetch_one(
        "SELECT theme, visual_style FROM user_preferences WHERE user_id = %s",
        (user["id"],),
    )
    return {
        "user": {
            "id": user["id"], "email": user["email"], "username": user["username"],
            "display_name": user.get("display_name"), "shop_name": user.get("shop_name"),
            "role": user.get("role"),
        },
        "preferences": pref or {"theme": "purple", "visual_style": "manga"},
    }


# ---------------------------------------------------------------------------
# 偏好
# ---------------------------------------------------------------------------
@app.get("/api/v1/users/me/preferences")
def get_preferences(user: dict = Depends(current_user)):
    pref = db.fetch_one(
        "SELECT theme, visual_style FROM user_preferences WHERE user_id = %s",
        (user["id"],),
    )
    return pref or {"theme": "purple", "visual_style": "manga"}


@app.put("/api/v1/users/me/preferences")
def put_preferences(payload: PreferencesIn, user: dict = Depends(current_user)):
    # 白名单校验：只允许已知的主题与风格值
    ALLOWED_THEMES = {"red", "green", "blue", "orange", "purple"}
    ALLOWED_VISUALS = {"manga", "editorial", "gacha", "spine"}

    if payload.theme and payload.theme not in ALLOWED_THEMES:
        raise HTTPException(422, "未知的主题")
    if payload.visual_style and payload.visual_style not in ALLOWED_VISUALS:
        raise HTTPException(422, "未知的视觉风格")

    db.execute(
        """
        INSERT INTO user_preferences (user_id, theme, visual_style)
        VALUES (%s, COALESCE(%s,'purple'), COALESCE(%s,'manga'))
        ON DUPLICATE KEY UPDATE
            theme = COALESCE(VALUES(theme), theme),
            visual_style = COALESCE(VALUES(visual_style), visual_style)
        """,
        (user["id"], payload.theme, payload.visual_style),
    )
    return db.fetch_one(
        "SELECT theme, visual_style FROM user_preferences WHERE user_id = %s",
        (user["id"],),
    )


# ---------------------------------------------------------------------------
# 商品
# ---------------------------------------------------------------------------
@app.get("/api/v1/products")
def list_products(
    category: str | None = Query(None, max_length=40),
    badge: str | None = Query(None, max_length=20),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort: str = Query("sort_order", pattern="^(sort_order|price_asc|price_desc|sales|rating)$"),
):
    where = ["is_active = 1"]
    params: list[Any] = []
    if category:
        where.append("category = %s")
        params.append(category)
    if badge:
        where.append("badge = %s")
        params.append(badge)

    order = {
        "sort_order": "sort_order ASC, id ASC",
        "price_asc": "price_cents ASC",
        "price_desc": "price_cents DESC",
        "sales": "monthly_sales DESC",
        "rating": "rating DESC",
    }[sort]

    clause = " AND ".join(where)
    total = db.fetch_one(f"SELECT COUNT(*) AS n FROM products WHERE {clause}", tuple(params))
    rows = db.fetch_all(
        f"""SELECT id, slug, name, description, price_cents, category, image,
                   badge, monthly_sales, rating, stock
            FROM products WHERE {clause}
            ORDER BY {order} LIMIT %s OFFSET %s""",
        tuple(params) + (limit, offset),
    )
    for r in rows:
        r["price"] = round(r["price_cents"] / 100, 2)
        r["rating"] = float(r["rating"])
    return {
        "data": rows,
        "pagination": {
            "total": total["n"] if total else 0,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + len(rows)) < (total["n"] if total else 0),
        },
    }


@app.get("/api/v1/products/{product_id}")
def get_product(product_id: int):
    row = db.fetch_one(
        """SELECT id, slug, name, description, price_cents, category, image,
                  badge, monthly_sales, rating, stock
           FROM products WHERE id = %s AND is_active = 1""",
        (product_id,),
    )
    if not row:
        raise HTTPException(404, "商品不存在")
    row["price"] = round(row["price_cents"] / 100, 2)
    row["rating"] = float(row["rating"])
    return row


@app.get("/api/v1/health")
def health():
    try:
        db.fetch_one("SELECT 1 AS ok")
        return {"status": "ok", "db": "up", "mail": "smtp" if mailer.is_enabled() else "console"}
    except Exception as exc:  # noqa: BLE001
        return problem(503, "数据库不可用", str(exc), "dependency-unavailable")


# ---------------------------------------------------------------------------
# 订单
#
# 状态机（只允许这些转移，其余一律拒绝）：
#   pending ──用户点「我已付款」──> paid ──发货──> shipped
#
# 「是否已付款」按需求定义为：用户点击声明已付款的按钮，不接真实支付网关。
# 发货是唯一改动商品数据的动作（库存 -qty、月销 +qty），必须在一个事务内完成。
# ---------------------------------------------------------------------------
ORDER_NO_PREFIX = datetime.utcnow().strftime("%Y%m%d")


class OrderItemIn(BaseModel):
    product_id: int = Field(..., gt=0)
    qty: int = Field(1, ge=1, le=99)


class OrderIn(BaseModel):
    items: list[OrderItemIn] = Field(...)
    addr: str = Field(..., max_length=200)
    phone: str = Field(..., max_length=30)
    note: str = Field("", max_length=200)


class ShipIn(BaseModel):
    note: str = Field("", max_length=200)


def _gen_order_no() -> str:
    return ORDER_NO_PREFIX + "".join(secrets.choice("0123456789") for _ in range(8))


def _load_order(order_id: int, user_id: int) -> dict[str, Any]:
    order = db.fetch_one(
        "SELECT id, order_no, user_id, total_cents, status, addr, phone, "
        "paid_at, shipped_at, note, created_at FROM orders WHERE id = %s AND user_id = %s",
        (order_id, user_id),
    )
    if not order:
        raise HTTPException(404, "订单不存在")
    order["items"] = db.fetch_all(
        "SELECT product_id, name_snapshot, image_snapshot, price_cents, qty "
        "FROM order_items WHERE order_id = %s ORDER BY id",
        (order_id,),
    )
    order["total"] = round(order["total_cents"] / 100, 2)
    for it in order["items"]:
        it["price"] = round(it["price_cents"] / 100, 2)
    return order


@app.post("/api/v1/orders", status_code=201)
def create_order(payload: OrderIn, user: dict = Depends(current_user)):
    addr = payload.addr.strip()
    phone = payload.phone.strip()
    if len(addr) < 5:
        raise HTTPException(422, "请填写完整收货地址")
    if len(phone) < 6:
        raise HTTPException(422, "请填写有效联系电话")

    # 合并重复商品，避免同一商品两行各扣一次库存
    wanted: dict[int, int] = {}
    for it in payload.items:
        wanted[it.product_id] = wanted.get(it.product_id, 0) + it.qty

    ids = list(wanted.keys())
    placeholders = ",".join(["%s"] * len(ids))
    rows = db.fetch_all(
        f"SELECT id, name, image, price_cents, stock, is_active "
        f"FROM products WHERE id IN ({placeholders})",
        tuple(ids),
    )
    by_id = {r["id"]: r for r in rows}

    total_cents = 0
    for pid, qty in wanted.items():
        p = by_id.get(pid)
        if not p or not p["is_active"]:
            raise HTTPException(422, f"商品 {pid} 不存在或已下架")
        if p["stock"] < qty:
            raise HTTPException(409, f"「{p['name']}」库存不足（剩 {p['stock']} 件）")
        total_cents += p["price_cents"] * qty

    order_no = _gen_order_no()
    while db.fetch_one("SELECT id FROM orders WHERE order_no = %s", (order_no,)):
        order_no = _gen_order_no()

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO orders (order_no, user_id, total_cents, status, addr, phone, note) "
                "VALUES (%s, %s, %s, 'pending', %s, %s, %s)",
                (order_no, user["id"], total_cents, addr, phone, payload.note.strip()),
            )
            order_id = cur.lastrowid
            for pid, qty in wanted.items():
                p = by_id[pid]
                cur.execute(
                    "INSERT INTO order_items "
                    "(order_id, product_id, name_snapshot, image_snapshot, price_cents, qty) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (order_id, pid, p["name"], p["image"], p["price_cents"], qty),
                )

    return _load_order(order_id, user["id"])


@app.get("/api/v1/orders")
def list_orders(user: dict = Depends(current_user), limit: int = Query(20, ge=1, le=100)):
    rows = db.fetch_all(
        "SELECT id FROM orders WHERE user_id = %s ORDER BY id DESC LIMIT %s",
        (user["id"], limit),
    )
    return {"data": [_load_order(r["id"], user["id"]) for r in rows]}


@app.get("/api/v1/orders/{order_id}")
def get_order(order_id: int, user: dict = Depends(current_user)):
    return _load_order(order_id, user["id"])


@app.post("/api/v1/orders/{order_id}/pay")
def pay_order(order_id: int, user: dict = Depends(current_user)):
    """用户声明已付款。只允许 pending → paid，重复点击幂等返回。"""
    order = db.fetch_one(
        "SELECT id, status FROM orders WHERE id = %s AND user_id = %s",
        (order_id, user["id"]),
    )
    if not order:
        raise HTTPException(404, "订单不存在")

    if order["status"] == "paid":
        return _load_order(order_id, user["id"])      # 幂等
    if order["status"] != "pending":
        raise HTTPException(409, f"当前状态（{order['status']}）不能付款")

    # 条件更新：并发下只有一个请求能把它从 pending 改成 paid
    affected = db.execute(
        "UPDATE orders SET status = 'paid', paid_at = %s "
        "WHERE id = %s AND user_id = %s AND status = 'pending'",
        (datetime.utcnow(), order_id, user["id"]),
    )
    if not affected:
        raise HTTPException(409, "订单状态已变化，请刷新后重试")

    return _load_order(order_id, user["id"])


@app.post("/api/v1/orders/{order_id}/ship")
def ship_order(order_id: int, payload: ShipIn, user: dict = Depends(require_merchant)):
    """
    发货：paid → shipped，并在同一事务里
      products.stock         -= qty
      products.monthly_sales += qty
    库存扣减带 `WHERE stock >= qty` 做原子校验，避免并发超卖。
    """
    order = db.fetch_one("SELECT id, status, user_id FROM orders WHERE id = %s", (order_id,))
    if not order:
        raise HTTPException(404, "订单不存在")
    owner_id = order["user_id"]
    if order["status"] == "shipped":
        return _load_order(order_id, owner_id)         # 幂等
    if order["status"] != "paid":
        raise HTTPException(409, "订单未付款，不能发货")

    items = db.fetch_all(
        "SELECT product_id, name_snapshot, qty FROM order_items WHERE order_id = %s",
        (order_id,),
    )
    if not items:
        raise HTTPException(409, "订单没有商品明细")

    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                # 1) 锁住订单状态：条件更新防止并发重复发货
                cur.execute(
                    "UPDATE orders SET status = 'shipped', shipped_at = %s, note = %s "
                    "WHERE id = %s AND status = 'paid'",
                    (datetime.utcnow(), payload.note.strip(), order_id),
                )
                if cur.rowcount == 0:
                    raise HTTPException(409, "订单状态已变化，请刷新后重试")

                # 2) 扣库存 + 加销量；任一件库存不足则整单回滚
                for it in items:
                    cur.execute(
                        "UPDATE products SET stock = stock - %s, "
                        "monthly_sales = monthly_sales + %s "
                        "WHERE id = %s AND stock >= %s",
                        (it["qty"], it["qty"], it["product_id"], it["qty"]),
                    )
                    if cur.rowcount == 0:
                        raise HTTPException(
                            409, f"「{it['name_snapshot']}」库存不足，发货失败"
                        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"发货失败：{exc}") from exc

    return _load_order(order_id, owner_id)


# ---------------------------------------------------------------------------
# 前端托管：必须放在所有 API 路由之后挂载，
# 否则 "/" 的 StaticFiles 会吃掉 /api/v1/*
# 这样只需启动后端一个进程，前端也一并可用。
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 商家 / 管理员接口
# ---------------------------------------------------------------------------
class ProductIn(BaseModel):
    name: str = Field(..., max_length=120)
    slug: str = Field(..., max_length=80)
    description: str = Field("", max_length=2000)
    price_cents: int = Field(..., ge=0, le=100_000_000)
    category: str = Field("other", max_length=40)
    image: str = Field("", max_length=160)
    badge: str = Field("", max_length=20)
    stock: int = Field(0, ge=0, le=999_999)
    is_active: bool = True


class ProductPatch(BaseModel):
    name: str | None = Field(None, max_length=120)
    description: str | None = Field(None, max_length=2000)
    price_cents: int | None = Field(None, ge=0, le=100_000_000)
    category: str | None = Field(None, max_length=40)
    image: str | None = Field(None, max_length=160)
    badge: str | None = Field(None, max_length=20)
    stock: int | None = Field(None, ge=0, le=999_999)
    is_active: bool | None = None


class RoleIn(BaseModel):
    role: str = Field(..., max_length=20)


# ---------- 商品管理（merchant / admin） ----------
@app.get("/api/v1/merchant/products")
def merchant_list_products(user: dict = Depends(require_merchant),
                           limit: int = Query(100, ge=1, le=200),
                           offset: int = Query(0, ge=0)):
    rows = db.fetch_all(
        "SELECT id, slug, name, description, price_cents, category, image, badge, "
        "monthly_sales, rating, stock, is_active, sort_order "
        "FROM products ORDER BY sort_order ASC, id ASC LIMIT %s OFFSET %s",
        (limit, offset),
    )
    total = db.fetch_one("SELECT COUNT(*) AS n FROM products")
    for r in rows:
        r["price"] = round(r["price_cents"] / 100, 2)
        r["rating"] = float(r["rating"])
    return {"data": rows, "total": total["n"]}


@app.post("/api/v1/merchant/products", status_code=201)
def merchant_create_product(payload: ProductIn, user: dict = Depends(require_merchant)):
    if db.fetch_one("SELECT id FROM products WHERE slug = %s", (payload.slug.strip(),)):
        raise HTTPException(409, "该 slug 已存在")
    pid = db.execute(
        "INSERT INTO products (slug, name, description, price_cents, category, image, "
        "badge, stock, is_active, sort_order) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (payload.slug.strip(), payload.name.strip(), payload.description.strip(),
         payload.price_cents, payload.category.strip() or "other", payload.image.strip(),
         payload.badge.strip() or None, payload.stock, 1 if payload.is_active else 0, 999),
    )
    return db.fetch_one("SELECT * FROM products WHERE id = %s", (pid,))


@app.patch("/api/v1/merchant/products/{product_id}")
def merchant_patch_product(product_id: int, payload: ProductPatch,
                           user: dict = Depends(require_merchant)):
    row = db.fetch_one("SELECT id FROM products WHERE id = %s", (product_id,))
    if not row:
        raise HTTPException(404, "商品不存在")

    sets, params = [], []
    data = payload.dict(exclude_unset=True)
    for field in ("name", "description", "price_cents", "category", "image", "stock"):
        if field in data and data[field] is not None:
            sets.append(f"{field} = %s")
            params.append(data[field])
    if "badge" in data:
        sets.append("badge = %s")
        params.append((data["badge"] or "").strip() or None)
    if "is_active" in data and data["is_active"] is not None:
        sets.append("is_active = %s")
        params.append(1 if data["is_active"] else 0)

    if not sets:
        raise HTTPException(422, "没有要修改的字段")

    params.append(product_id)
    db.execute(f"UPDATE products SET {', '.join(sets)} WHERE id = %s", tuple(params))
    return db.fetch_one("SELECT * FROM products WHERE id = %s", (product_id,))


@app.delete("/api/v1/merchant/products/{product_id}", status_code=204)
def merchant_delete_product(product_id: int, user: dict = Depends(require_merchant)):
    row = db.fetch_one("SELECT id FROM products WHERE id = %s", (product_id,))
    if not row:
        raise HTTPException(404, "商品不存在")
    # 不真删，下架（历史订单要能追溯到商品快照，删了会留下悬空引用）
    db.execute("UPDATE products SET is_active = 0 WHERE id = %s", (product_id,))
    return None


# ---------- 订单管理（merchant / admin） ----------
@app.get("/api/v1/merchant/orders")
def merchant_list_orders(user: dict = Depends(require_merchant),
                         status: str | None = Query(None, max_length=20),
                         limit: int = Query(50, ge=1, le=200)):
    where, params = [], []
    if status:
        where.append("o.status = %s")
        params.append(status)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = db.fetch_all(
        f"SELECT o.id, o.order_no, o.user_id, u.username, u.email, o.total_cents, "
        f"o.status, o.addr, o.phone, o.paid_at, o.shipped_at, o.created_at "
        f"FROM orders o JOIN users u ON u.id = o.user_id {clause} "
        f"ORDER BY o.id DESC LIMIT %s",
        tuple(params) + (limit,),
    )
    for r in rows:
        r["total"] = round(r["total_cents"] / 100, 2)
        r["items"] = db.fetch_all(
            "SELECT product_id, name_snapshot, qty, price_cents FROM order_items WHERE order_id = %s",
            (r["id"],),
        )
    return {"data": rows}


# ---------- 统计（merchant / admin） ----------
@app.get("/api/v1/merchant/stats")
def merchant_stats(user: dict = Depends(require_merchant)):
    totals = db.fetch_one(
        "SELECT COUNT(*) AS products, "
        "COALESCE(SUM(stock), 0) AS stock_total, "
        "COALESCE(SUM(monthly_sales), 0) AS sales_total "
        "FROM products WHERE is_active = 1"
    )
    order_stat = db.fetch_one(
        "SELECT COUNT(*) AS orders, "
        "COALESCE(SUM(total_cents), 0) AS revenue_cents, "
        "SUM(status = 'pending') AS pending_n, "
        "SUM(status = 'paid') AS paid_n, "
        "SUM(status = 'shipped') AS shipped_n "
        "FROM orders"
    )
    return {
        "products": totals["products"],
        "stock_total": int(totals["stock_total"]),
        "monthly_sales_total": int(totals["sales_total"]),
        "orders": order_stat["orders"],
        "revenue": round(int(order_stat["revenue_cents"] or 0) / 100, 2),
        "pending": int(order_stat["pending_n"] or 0),
        "paid": int(order_stat["paid_n"] or 0),
        "shipped": int(order_stat["shipped_n"] or 0),
    }


# ---------- 用户管理（仅 admin） ----------
@app.get("/api/v1/admin/users")
def admin_list_users(user: dict = Depends(require_admin),
                     q: str | None = Query(None, max_length=100),
                     limit: int = Query(50, ge=1, le=200)):
    if q:
        rows = db.fetch_all(
            "SELECT id, email, username, display_name, shop_name, role, is_active, "
            "last_login_at, created_at FROM users "
            "WHERE email LIKE %s OR username LIKE %s ORDER BY id DESC LIMIT %s",
            (f"%{q}%", f"%{q}%", limit),
        )
    else:
        rows = db.fetch_all(
            "SELECT id, email, username, display_name, shop_name, role, is_active, "
            "last_login_at, created_at FROM users ORDER BY id DESC LIMIT %s",
            (limit,),
        )
    return {"data": rows}


@app.put("/api/v1/admin/users/{user_id}/role")
def admin_set_role(user_id: int, payload: RoleIn, user: dict = Depends(require_admin)):
    role = payload.role.strip()
    if role not in ALL_ROLES:
        raise HTTPException(422, "未知角色")
    target = db.fetch_one("SELECT id, role FROM users WHERE id = %s", (user_id,))
    if not target:
        raise HTTPException(404, "用户不存在")
    if target["id"] == user["id"] and role != ROLE_ADMIN:
        raise HTTPException(409, "不能给自己降权，请让另一个管理员操作")
    db.execute("UPDATE users SET role = %s WHERE id = %s", (role, user_id))
    return {"id": user_id, "role": role}


@app.put("/api/v1/admin/users/{user_id}/active")
def admin_set_active(user_id: int, user: dict = Depends(require_admin)):
    target = db.fetch_one("SELECT id, is_active FROM users WHERE id = %s", (user_id,))
    if not target:
        raise HTTPException(404, "用户不存在")
    if target["id"] == user["id"]:
        raise HTTPException(409, "不能停用自己的账号")
    new_state = 0 if target["is_active"] else 1
    db.execute("UPDATE users SET is_active = %s WHERE id = %s", (new_state, user_id))
    return {"id": user_id, "is_active": bool(new_state)}


# ---------------------------------------------------------------------------
# 前端托管：必须放在所有 API 路由之后挂载，
# 否则 "/" 的 StaticFiles 会吃掉 /api/v1/*
# ---------------------------------------------------------------------------

FRONTEND_DIR = Path(__file__).resolve().parent.parent

if (FRONTEND_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
