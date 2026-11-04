"""
change-skin 商城后端 · 配置与数据库连接

MySQL 5.5 与 8.0 都兼容：不用 JSON 类型、不用窗口函数、不用 CTE。
连接层用 PyMySQL（纯 Python，Windows 上无需编译）。
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

import pymysql
from pymysql.cursors import DictCursor

# ---------------------------------------------------------------------------
# 配置（全部可用环境变量覆盖）
# ---------------------------------------------------------------------------
DB_HOST = os.getenv("CS_DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("CS_DB_PORT", "3306"))
DB_USER = os.getenv("CS_DB_USER", "root")
DB_PASSWORD = os.getenv("CS_DB_PASSWORD", "root")
DB_NAME = os.getenv("CS_DB_NAME", "change_skin")

# 会话有效期（小时）
SESSION_TTL_HOURS = int(os.getenv("CS_SESSION_TTL_HOURS", "72"))

# 登录失败锁定策略：连续失败 N 次锁 M 分钟
MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15

# CORS 白名单：生产环境务必收紧
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CS_ALLOWED_ORIGINS",
        "http://127.0.0.1:8777,http://localhost:8777,http://127.0.0.1:8000",
    ).split(",")
    if o.strip()
]


def _connect() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
        connect_timeout=5,
    )


@contextmanager
def get_conn() -> Iterator[pymysql.connections.Connection]:
    """事务上下文：正常提交，异常回滚。"""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_cursor() -> Iterator[DictCursor]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            yield cur


def fetch_one(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with get_cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def fetch_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def execute(sql: str, params: tuple[Any, ...] = ()) -> int:
    """执行写入语句，返回 lastrowid（INSERT）或受影响行数。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.lastrowid or cur.rowcount
