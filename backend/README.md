# 后端服务 · 启动说明

## 最快启动

双击 `start.bat`，或者在 PowerShell 里：

```powershell
cd E:\xueqi3_25570705lixiyu\JS\change-skin\backend
python run.py
```

启动前会自动自检依赖、数据库、表结构、端口占用，全过才拉起服务，并打印所有页面地址。

**只需要起这一个进程**，前端由后端托管（`StaticFiles` 挂载在 `/`），不用再单独开静态服务器。

---

## 环境

| 组件 | 版本 | 说明 |
|---|---|---|
| MySQL | 8.4.3 | `E:\mysql84`，端口 3306，已注册为服务 `MySQL84`（自动启动） |
| Python | **3.12.0** | PATH 里的 `python` 指向它 |
| FastAPI | 0.162.0 | pip |
| uvicorn | 0.54.0 | pip |
| PyMySQL | 2.2.8 | pip |
| cryptography | — | PyMySQL 连 MySQL 8 的 `caching_sha2_password` 需要 |

旧的 MySQL 5.5 已停止并改为手动启动，原始数据备份在 `I:\AI\backup\mysql_5.5_20261104`。

### 依赖安装

```powershell
python -m pip install fastapi uvicorn pymysql cryptography
```

**网络注意**：这台机器上代理（127.0.0.1:10808）不一定开着，而 pip 可能继承了代理配置，导致安装失败。直连 pypi 是通的，所以建议显式清掉代理：

```powershell
$env:HTTP_PROXY=""; $env:HTTPS_PROXY=""
python -m pip install --proxy "" --timeout 120 --index-url https://pypi.org/simple fastapi uvicorn pymysql cryptography
```

直连速度较慢（几十 KB/s），装完需要几分钟。

> 之前依赖装在 Python 3.10，但那个安装已损坏（`ModuleNotFoundError: No module named 'encodings'`）。现在统一用 PATH 里的 Python 3.12。

---

## 启动

### 1. 确认 MySQL 在跑

```powershell
Get-Service MySQL84
```

如果不是 `Running`：

```powershell
sc.exe start MySQL84
```

### 2. 起后端

双击 `backend\start.bat`，或：

```powershell
python run.py
```

可选参数：

```powershell
python run.py --port 8080        # 换端口
python run.py --host 0.0.0.0     # 局域网可访问
python run.py --reload           # 改代码自动重启
```

### 3. 打开页面

```
http://127.0.0.1:8000/index.html      商城
http://127.0.0.1:8000/login.html      登录 / 注册
http://127.0.0.1:8000/orders.html     我的订单
http://127.0.0.1:8000/merchant.html   商家后台
http://127.0.0.1:8000/admin.html      管理后台
http://127.0.0.1:8000/docs            API 文档
```

---

## 关于 start.bat 的编码

**这个文件必须是纯 ASCII，不要往里加中文。**

`cmd.exe` 解析 `.bat` 文件用的是**系统代码页（zh-CN 是 GBK）**，不是文件里 `chcp 65001` 设置的那个。所以 UTF-8 存的中文会被切成乱码「命令」，报错形如：

```
'世界商城后端' is not recognized as an internal or external command
```

所有中文提示都放在 `run.py` 里（它自己把 stdout/stderr 重配成 UTF-8）。

---

## 配置

全部可用环境变量覆盖，也可以写进 `backend/.env`（已被 `.gitignore` 排除）：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `CS_DB_HOST` | 127.0.0.1 | |
| `CS_DB_PORT` | 3306 | |
| `CS_DB_USER` | root | |
| `CS_DB_PASSWORD` | root | **上线前务必改** |
| `CS_DB_NAME` | change_skin | |
| `CS_SESSION_TTL_HOURS` | 72 | 会话有效期 |
| `CS_ALLOWED_ORIGINS` | 127.0.0.1:8777 等 | CORS 白名单 |
| `CS_SMTP_HOST` | — | 邮件 SMTP，留空则验证码打到控制台 |
| `CS_SMTP_PORT` | 465 | |
| `CS_SMTP_USER` | — | 发件邮箱 |
| `CS_SMTP_PASSWORD` | — | 授权码（不是邮箱登录密码） |

---

## API

前缀 `/api/v1`，交互式文档 <http://127.0.0.1:8000/docs>

### 认证
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/auth/send-code` | 发邮箱验证码（60 秒冷却） |
| POST | `/auth/register` | 注册（需邮箱验证码） |
| POST | `/auth/login` | 登录 |
| POST | `/auth/logout` | 注销当前 token |
| GET | `/auth/me` | 当前用户 + 偏好 |

### 商品与偏好
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/products` | 商品列表（分页、分类、排序） |
| GET | `/products/{id}` | 商品详情 |
| GET/PUT | `/users/me/preferences` | 主题与视觉风格偏好 |

### 订单
| 方法 | 路径 | 权限 |
|---|---|---|
| POST | `/orders` | 登录用户 |
| GET | `/orders` | 登录用户（只返回自己的） |
| POST | `/orders/{id}/pay` | 登录用户（声明已付款） |
| POST | `/orders/{id}/ship` | **merchant / admin** |

### 商家 / 管理
| 方法 | 路径 | 权限 |
|---|---|---|
| GET/POST | `/merchant/products` | merchant / admin |
| PATCH/DELETE | `/merchant/products/{id}` | merchant / admin |
| GET | `/merchant/orders` | merchant / admin |
| GET | `/merchant/stats` | merchant / admin |
| GET | `/admin/users` | admin |
| PUT | `/admin/users/{id}/role` | admin |
| PUT | `/admin/users/{id}/active` | admin |

错误响应统一 RFC 7807（`application/problem+json`）。

---

## 安全实现

- 密码：PBKDF2-HMAC-SHA256，600k 次迭代，16 字节随机盐，`hmac.compare_digest` 比对
- 会话：`secrets.token_urlsafe(32)`，库里只存 SHA-256，明文只在响应出现一次
- 登录失败 5 次锁 15 分钟（计数在库，重启不失效）
- 用户不存在时也跑一次哈希（`burn_time`），避免时序侧信道
- 所有查询参数化，无字符串拼接 SQL
- 邮箱验证码：6 位数字、SHA-256 入库、5 分钟过期、60 秒冷却、最多试错 5 次、一次性消费
- 发货扣库存用 `WHERE stock >= qty` 原子校验，防并发超卖，整单事务
- 角色权限在服务端判定，前端只控制入口显隐

---

## 缓存策略

`app.py` 里有 `dev_cache_headers` 中间件：所有 `.html` 响应加 `no-cache, no-store, must-revalidate`。

原因是 `StaticFiles` 和 `python http.server` 都不发 `Cache-Control`，浏览器会按启发式缓存 HTML——改了 CSS 又升了 `?v=` 版本号，但 HTML 本身被缓存导致版本号还是旧的，于是永远加载旧样式。

---

## 未做的事

- 密码找回（`/forgotLink` 目前只提示联系管理员）
- 限流（rate limiting）—— 上公网前必须加
- HTTPS —— 本地明文，公网必须 TLS
- 真实支付网关（`pay` 只是状态标记）

## 重新灌商品数据

```powershell
python seed_products.py
```

从 `index.html` 抽取商品卡写入 `products` 表（幂等，按 `slug` 更新）。
