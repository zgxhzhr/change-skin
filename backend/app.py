"""
change-skin 商城后端 · FastAPI 应用

路由全部挂在 /api/v1 下，统一版本前缀。
错误响应遵循 RFC 7807（application/problem+json）。

启动：
    python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import db
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
               u.id, u.email, u.username, u.is_active
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

    exists = db.fetch_one(
        "SELECT id FROM users WHERE email = %s OR username = %s LIMIT 1",
        (email, username),
    )
    if exists:
        raise HTTPException(409, "该邮箱或用户名已被注册")

    user_id = db.execute(
        "INSERT INTO users (email, username, password_hash) VALUES (%s, %s, %s)",
        (email, username, hash_password(payload.password)),
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
        "user": {"id": user_id, "email": email, "username": username},
    }


@app.post("/api/v1/auth/login")
def login(payload: LoginIn):
    account = payload.account.strip().lower()

    row = db.fetch_one(
        "SELECT id, email, username, password_hash, is_active, failed_attempts, locked_until "
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
        "user": {"id": row["id"], "email": row["email"], "username": row["username"]},
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
        "user": {"id": user["id"], "email": user["email"], "username": user["username"]},
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
        return {"status": "ok", "db": "up"}
    except Exception as exc:  # noqa: BLE001
        return problem(503, "数据库不可用", str(exc), "dependency-unavailable")
