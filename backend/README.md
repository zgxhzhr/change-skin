# 后端服务 · 启动说明

## 环境

| 组件 | 版本 | 位置 |
|---|---|---|
| MySQL | 8.4.3 | `E:\mysql84`（端口 3306） |
| Python | 3.10.6 | 系统 PATH |
| FastAPI | 0.94.0 | pip |
| PyMySQL | 2.2.8 | pip |

旧的 MySQL 5.5 已停止并改为手动启动，原数据备份在 `I:\AI\backup\mysql_5.5_20261104`。

## 启动

### 1. 确认 MySQL 在跑

```powershell
Get-NetTCPConnection -LocalPort 3306 -State Listen
```

如果没有，启动 8.4：

```powershell
Start-Process -FilePath "E:\mysql84\mysql-8.4.3-winx64\bin\mysqld.exe" `
  -ArgumentList "--defaults-file=E:\mysql84\my.ini" -WindowStyle Hidden
```

### 2. 启动 API

```powershell
cd E:\xueqi3_25570705lixiyu\JS\change-skin\backend
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

### 3. 启动前端

```powershell
cd E:\xueqi3_25570705lixiyu\JS\change-skin
python -m http.server 8777 --bind 127.0.0.1
```

访问 <http://127.0.0.1:8777/login.html>

## 配置

全部可用环境变量覆盖，改 `backend/db.py` 顶部的默认值也可以：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `CS_DB_HOST` | 127.0.0.1 | |
| `CS_DB_PORT` | 3306 | |
| `CS_DB_USER` | root | |
| `CS_DB_PASSWORD` | root | **上线前务必改** |
| `CS_DB_NAME` | change_skin | |
| `CS_SESSION_TTL_HOURS` | 72 | 会话有效期 |
| `CS_ALLOWED_ORIGINS` | 127.0.0.1:8777 等 | CORS 白名单 |

## API

前缀 `/api/v1`，交互式文档 <http://127.0.0.1:8000/docs>

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/auth/register` | 注册，返回 token |
| POST | `/auth/login` | 登录，返回 token |
| POST | `/auth/logout` | 注销当前 token（204） |
| GET | `/auth/me` | 当前用户 + 偏好 |
| GET | `/users/me/preferences` | 读偏好 |
| PUT | `/users/me/preferences` | 写偏好（theme / visual_style） |
| GET | `/products` | 商品列表（category / badge / sort / 分页） |
| GET | `/products/{id}` | 商品详情 |
| GET | `/health` | 健康检查 |

错误响应统一 RFC 7807（`application/problem+json`）。

## 安全实现

- 密码：PBKDF2-HMAC-SHA256，600k 次迭代，16 字节随机盐，`hmac.compare_digest` 比对
- 会话：`secrets.token_urlsafe(32)`，库里只存 SHA-256，明文只在响应里出现一次
- 登录失败 5 次锁 15 分钟（计数在库，重启不失效）
- 用户不存在时也跑一次哈希（`burn_time`），避免时序侧信道区分账号是否存在
- 所有查询参数化，无字符串拼接 SQL
- 偏好写入做白名单校验（只接受已知主题/风格值）

## 未做的事

- 密码找回（`/forgotLink` 目前只提示联系管理员）
- 限流（rate limiting）—— 上公网前必须加
- HTTPS —— 本地明文，公网必须走 TLS
- 订单接口只建了表，未开放 API

## 重新灌商品数据

```powershell
cd E:\xueqi3_25570705lixiyu\JS\change-skin\backend
python seed_products.py
```

从 `index.html` 抽取商品卡写入 `products` 表（可重复执行，按 `slug` 幂等更新）。
