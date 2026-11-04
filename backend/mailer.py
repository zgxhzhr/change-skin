"""
change-skin 后端 · 邮件发送

两种模式，由环境变量决定：

- SMTP 模式（真实发送）：配置齐全时使用
    CS_SMTP_HOST     如 smtp.qq.com
    CS_SMTP_PORT     465（SSL）或 587（STARTTLS）
    CS_SMTP_USER     登录名 / 发件地址
    CS_SMTP_PASSWORD 授权码（不是邮箱登录密码）
    CS_SMTP_FROM     发件人显示地址，默认同 USER
    CS_SMTP_SSL      true/false，默认 true

- 开发模式（未配置 SMTP）：不倒腾网络，把验证码打到 stdout 与日志，
  接口照常返回成功，行为逻辑完全一致，只是投递渠道换成控制台。
  这样在没有邮箱账号时也能完整跑通注册流程。

无论哪种模式，验证码都是服务端生成、哈希入库、限时限次的真逻辑。
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

log = logging.getLogger("change_skin.mailer")

# 读同目录下的 .env（不用 python-dotenv，避免多一个依赖）
_ENV_FILE = Path(__file__).resolve().parent / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
        # 已存在的环境变量优先，.env 只做兜底
        os.environ.setdefault(_k, _v)

SMTP_HOST = os.getenv("CS_SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("CS_SMTP_PORT", "465"))
SMTP_USER = os.getenv("CS_SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("CS_SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("CS_SMTP_FROM", SMTP_USER).strip()
SMTP_SSL = os.getenv("CS_SMTP_SSL", "true").lower() in ("1", "true", "yes")

SMTP_ENABLED = bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def is_enabled() -> bool:
    return SMTP_ENABLED


def _build_message(to_addr: str, code: str, purpose: str) -> MIMEText:
    action = {
        "register": "注册账号",
        "reset": "重置密码",
        "login": "登录验证",
    }.get(purpose, "身份验证")

    text = f"""异世界商城 · 验证码

你正在进行「{action}」操作，验证码是：

    {code}

验证码 5 分钟内有效，仅可使用一次。

如果这不是你本人的操作，请忽略这封邮件，你的账号不会有任何变化。
请勿把验证码告诉任何人，包括声称是客服的人。

—— 异世界商城
"""
    msg = MIMEText(text, "plain", "utf-8")
    msg["Subject"] = Header(f"【异世界商城】{action}验证码：{code}", "utf-8")
    msg["From"] = formataddr(("异世界商城", SMTP_FROM))
    msg["To"] = to_addr
    return msg


def send_code(to_addr: str, code: str, purpose: str = "register") -> bool:
    """发送验证码。返回 True 表示已投递（或开发模式下已输出）。"""
    if not SMTP_ENABLED:
        # 开发模式：明确打出来，方便本地测试，同时在日志里留痕
        banner = "=" * 56
        log.warning("\n%s\n[开发模式] 未配置 SMTP，验证码只输出到控制台\n"
                    "收件人: %s\n用途: %s\n验证码: %s\n%s",
                    banner, to_addr, purpose, code, banner)
        print(f"\n{banner}\n[开发模式邮件] 收件人={to_addr}  用途={purpose}  验证码={code}\n{banner}\n", flush=True)
        return True

    try:
        msg = _build_message(to_addr, code, purpose)
        if SMTP_SSL:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
            server.starttls()
        try:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [to_addr], msg.as_string())
        finally:
            try:
                server.quit()
            except Exception:  # noqa: BLE001
                pass
        log.info("验证码已发送至 %s（用途 %s）", to_addr, purpose)
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("发送验证码失败 %s: %s", to_addr, exc)
        return False
