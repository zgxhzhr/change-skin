"""
change-skin 后端启动入口

用法：
    python run.py                 # 默认 127.0.0.1:8000
    python run.py --port 8080     # 换端口
    python run.py --host 0.0.0.0  # 对外监听（局域网可访问）
    python run.py --reload        # 改代码自动重启（开发用）

启动前会先自检：依赖、数据库连接、表结构、端口占用。
任何一项不通过都会直接说明原因并退出，不用等 uvicorn 抛一堆栈。
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
from pathlib import Path

# Windows 控制台默认 GBK，输出 ✓ / ✗ 这类符号会抛 UnicodeEncodeError 直接崩掉。
# 这里强制切成 UTF-8；失败的终端（如重定向到文件）也能兜住。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))


def fail(msg: str) -> None:
    print(f"\n[X] {msg}\n", file=sys.stderr)
    sys.exit(1)


def check_deps() -> None:
    missing = []
    for mod, pkg in (("fastapi", "fastapi"), ("uvicorn", "uvicorn"), ("pymysql", "pymysql")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        fail(
            "缺少依赖：" + ", ".join(missing) + "\n"
            "    安装：python -m pip install " + " ".join(missing)
        )
    print("[OK] 依赖齐全")


def check_db() -> None:
    try:
        import db
        row = db.fetch_one("SELECT VERSION() AS v")
    except Exception as exc:  # noqa: BLE001
        fail(
            f"数据库连接失败：{exc}\n"
            f"    目标：{os.getenv('CS_DB_HOST', '127.0.0.1')}:{os.getenv('CS_DB_PORT', '3306')}"
            f"/{os.getenv('CS_DB_NAME', 'change_skin')}\n"
            "    检查 MySQL 是否在跑：Get-NetTCPConnection -LocalPort 3306 -State Listen"
        )
    print(f"[OK] 数据库连接正常（MySQL {row['v'] if row else '?'}）")

    try:
        import db as _db
        n = _db.fetch_one("SELECT COUNT(*) AS n FROM products")
        tables = _db.fetch_all("SHOW TABLES")
    except Exception as exc:  # noqa: BLE001
        fail(
            f"表结构不完整：{exc}\n"
            "    初始化：mysql -u root -p change_skin < schema.sql"
        )
    print(f"[OK] 表结构就绪（{len(tables)} 张表，{n['n']} 个商品）")


def check_port(host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.6)
        if s.connect_ex((host if host != "0.0.0.0" else "127.0.0.1", port)) == 0:
            fail(
                f"端口 {port} 已被占用。\n"
                f"    换个端口：python run.py --port {port + 1}\n"
                f"    或先停掉占用进程：Get-NetTCPConnection -LocalPort {port} | "
                "Select-Object OwningProcess"
            )
    print(f"[OK] 端口 {port} 可用")


def banner(host: str, port: int, mail_mode: str) -> None:
    shown = "127.0.0.1" if host == "0.0.0.0" else host
    print(
        "\n" + "=" * 62 + "\n"
        f"  异世界商城后端已启动\n"
        "\n"
        f"  商城首页    http://{shown}:{port}/index.html\n"
        f"  登录        http://{shown}:{port}/login.html\n"
        f"  我的订单    http://{shown}:{port}/orders.html\n"
        f"  商家后台    http://{shown}:{port}/merchant.html\n"
        f"  管理后台    http://{shown}:{port}/admin.html\n"
        f"  API 文档    http://{shown}:{port}/docs\n"
        f"  健康检查    http://{shown}:{port}/api/v1/health\n"
        "\n"
        f"  验证码投递  {'SMTP 真实发信' if mail_mode == 'smtp' else '控制台输出（未配置 SMTP）'}\n"
        "  停止服务    Ctrl+C\n"
        + "=" * 62 + "\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="change-skin 后端启动器")
    ap.add_argument("--host", default=os.getenv("CS_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("CS_PORT", "8000")))
    ap.add_argument("--reload", action="store_true", help="改代码自动重启（开发用）")
    args = ap.parse_args()

    os.chdir(BASE)

    print("正在自检…")
    check_deps()
    check_db()
    check_port(args.host, args.port)

    import mailer
    mail_mode = "smtp" if mailer.is_enabled() else "console"
    if mail_mode == "console":
        print("[!] 未配置 SMTP，邮箱验证码会打印到本控制台（backend/.env 可配置）")

    banner(args.host, args.port, mail_mode)

    import uvicorn
    uvicorn.run(
        "app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已停止。")
