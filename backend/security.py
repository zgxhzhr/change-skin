"""
change-skin 商城后端 · 安全原语

设计取舍（都是刻意的，不是图省事）：
- 密码用 PBKDF2-HMAC-SHA256（标准库 hashlib），不引入 bcrypt/argon2 的编译依赖。
  迭代次数按 OWASP 2023+ 建议取 600k；这在 Windows + 纯 Python 下约 60-100ms/次，
  对登录接口可接受，对暴力破解足够昂贵。
- 密码比对用 hmac.compare_digest，防时序侧信道。
- 会话 token 用 secrets.token_urlsafe(32)（256 bit 熵），数据库里只存 SHA-256。
  库泄露也无法直接拿 token 冒用；token 明文只在响应里出现一次。
- 登录失败计数与锁定放在数据库，不用内存字典（重启即失效）。
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta

PBKDF2_ITERATIONS = 600_000
PBKDF2_ALGO = "pbkdf2_sha256"
SALT_BYTES = 16


# ---------------------------------------------------------------------------
# 密码
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """返回 'pbkdf2_sha256$迭代$盐hex$摘要hex'。"""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{PBKDF2_ALGO}${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters_s, salt_hex, digest_hex = stored.split("$")
        if algo != PBKDF2_ALGO:
            return False
        iterations = int(iters_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, AttributeError):
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    # 定长比较必须用 compare_digest，不能用 ==
    return hmac.compare_digest(actual, expected)


# ---------------------------------------------------------------------------
# 会话 token
# ---------------------------------------------------------------------------
def new_session_token() -> tuple[str, str]:
    """生成 (明文 token, 库里存的 hash)。明文只返回给客户端一次。"""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry(hours: int) -> datetime:
    return datetime.utcnow() + timedelta(hours=hours)


# ---------------------------------------------------------------------------
# 输入校验（服务端必须自己校验，不能只靠前端）
# ---------------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
USERNAME_RE = re.compile(r"^[\w\u4e00-\u9fa5\-]{2,20}$")


def is_valid_email(email: str) -> bool:
    return bool(email) and len(email) <= 190 and bool(EMAIL_RE.match(email))


def is_valid_username(name: str) -> bool:
    return bool(name) and bool(USERNAME_RE.match(name))


def password_strength_error(password: str) -> str | None:
    """返回错误信息；None 表示通过。"""
    if not isinstance(password, str) or len(password) < 8:
        return "密码至少 8 位"
    if len(password) > 128:
        return "密码不能超过 128 位"
    if not re.search(r"[A-Za-z]", password):
        return "密码必须包含字母"
    if not re.search(r"\d", password):
        return "密码必须包含数字"
    return None


# ---------------------------------------------------------------------------
# 常量时间假验证：用户不存在时也跑一次 PBKDF2，
# 避免通过响应时间区分「用户不存在」和「密码错误」。
# ---------------------------------------------------------------------------
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def burn_time(password: str) -> None:
    verify_password(password, _DUMMY_HASH)
