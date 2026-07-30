<!-- Language switcher -->
<div align="right">

**[English](#english)** | **[中文](#chinese)**

</div>

---

<a name="english"></a>
# cc-monitor

[**→ Open Dashboard**](https://bolunhan.github.io/cc-monitor/)
[![Deploy GH Pages](https://github.com/BolunHan/cc-monitor/actions/workflows/deploy-gh-pages.yml/badge.svg)](https://github.com/BolunHan/cc-monitor/actions/workflows/deploy-gh-pages.yml)
[![Build Docker](https://github.com/BolunHan/cc-monitor/actions/workflows/build-docker.yml/badge.svg)](https://github.com/BolunHan/cc-monitor/actions/workflows/build-docker.yml)

Real-time Claude Code session monitor — track idle, working, pending approval, and completed sessions through a web dashboard, Android app, and REST API.

## Features

- **📊 Real-time Dashboard** — SSE-powered web UI with session cards, state badges, and browser notifications
- **📱 Android App** — Mobile monitoring with QR pairing, multi-server support, and SSE event log
- **🔌 Hook System** — Automatic state detection via Claude Code hooks (7 events)
- **🔐 Secure Pairing** — Token-based auth with QR code and 6-digit approval flow
- **🐳 Docker** — Single-container deployment with host networking
- **🏠 Multi-Server** — Monitor multiple Claude Code instances from one dashboard
- **🌍 LAN Discovery** — mDNS advertisement for automatic server detection on local network

## Quick Start

### 1. Start the Server

**Docker (recommended):**
```bash
docker compose up -d
```

**Native:**
```bash
pip install -e ".[dev]"
cc-monitor --port 9876 --host 0.0.0.0
```

### 2. Install Hooks

On the machine where Claude Code runs:
```bash
curl -skSL https://<server-ip>:9876/static/install-hooks.sh | SERVER_URL=https://<server-ip>:9876 bash
```

### 3. Open Dashboard

- **Local:** [http://localhost:9876](http://localhost:9876)
- **Remote (GitHub Pages):** [https://bolunhan.github.io/cc-monitor/](https://bolunhan.github.io/cc-monitor/) — open Settings, set **Server URL** to your server IP, set **Port** to `9876`, then **Save & Reconnect**

> **🔐 Self-signed certificate:** The server uses a self-signed TLS certificate. When connecting from a remote dashboard (GitHub Pages), you must trust the certificate first — otherwise the browser blocks the connection.
>
> **One-time step:** Open `https://<your-server-ip>:9876` directly in a new tab. Click **Advanced** → **Proceed to site** (or **Accept the Risk and Continue**). Once the certificate is trusted, return to the dashboard and reconnect.

## Session States

| State | Icon | Meaning |
|-------|------|---------|
| `working` | 🔵 | Claude is actively processing — executing tools or generating output |
| `pending_review` | 🟢 | Claude finished responding — output ready for review (auto→idle after 24h) |
| `idle` | ⚪ | No activity — session is dormant, waiting for input |
| `pending_approval` | 🟡 | Claude needs permission to proceed (tool approval or permission prompt) |
| `all_done` | ✅ | Session has ended |

### State Transitions

```
UserPromptSubmit / PreToolUse / PostToolUse  →  WORKING
Notification(idle_prompt)                     →  IDLE
Notification(permission_prompt)               →  PENDING_APPROVAL
PermissionRequest                             →  PENDING_APPROVAL
Stop                                          →  PENDING_REVIEW
SessionEnd                                    →  ALL_DONE
PENDING_REVIEW + 24h inactivity               →  IDLE (auto)
```

## Hook Events

| Event | Hook Script | Description |
|-------|-------------|-------------|
| `PreToolUse` | `pre_tool_use.py` | Tool execution started |
| `PostToolUse` | `post_tool_use.py` | Tool execution completed |
| `UserPromptSubmit` | `user_prompt_submit.py` | User submitted a prompt |
| `Stop` | `stop.py` | Claude finished responding |
| `Notification` | `notification.py` | Idle/permission notifications |
| `PermissionRequest` | `permission_request.py` | Tool needs user approval |
| `SessionEnd` | `session_end.py` | User exited Claude Code |

### Multi-Server Support

Each cc-monitor server gets its own hook entries with a `--url` argument:
```json
{
  "command": "~/.cc-monitor/hooks/pre_tool_use.py --url https://192.168.3.28:9876"
}
```

Installing hooks for a second server on port 9877 creates separate entries — uninstalling one server doesn't affect the other.

## Authentication & Pairing

When bound to a non-localhost address, the server enables:
- **TLS** — self-signed certificate with SHA-256 fingerprint
- **mDNS** — LAN advertisement for automatic discovery
- **Token Auth** — Bearer token required for all API access (localhost bypassed)

### Pairing Flow

**Web Dashboard:**
1. Click "Pair Device" → generates a 6-digit code
2. Run `cc-monitor --approve <code>` on the server machine
3. Dashboard receives token automatically

**Android App:**
1. Scan QR code from the web settings panel
2. App confirms pairing and stores token securely

**CLI:**
```bash
# Approve a pending request
cc-monitor --approve 123456

# Revoke all tokens
cc-monitor --revoke-all
```

## API Reference

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/event` | Yes | Submit a raw hook event |
| `GET` | `/api/status` | Yes | All sessions' current states |
| `GET` | `/api/status/<id>` | Yes | Single session state |
| `GET` | `/api/stream` | Token¹ | SSE stream (state_update + heartbeat every 3s) |
| `GET` | `/api/version` | No | Server version |
| `GET` | `/api/hooks-status` | Yes | Check if hooks are installed |
| `POST` | `/api/install-hooks` | Yes² | Install hooks into global settings |
| `POST` | `/api/uninstall-hooks` | Yes² | Surgically remove cc-monitor hooks |
| `POST` | `/api/session/<id>/archive` | Yes | Archive a session |
| `POST` | `/api/session/<id>/unarchive` | Yes | Unarchive a session |
| `POST` | `/api/session/<id>/complete` | Yes | Mark session as all_done |
| `GET` | `/api/auth/pair/qr` | No | QR pairing payload |
| `POST` | `/api/auth/pair/request` | No | Submit pairing request |
| `GET` | `/api/auth/pair/request/<id>/status` | No | Poll pairing request status |
| `POST` | `/api/auth/pair/request/<id>/approve` | No | Approve pairing (localhost only) |
| `DELETE` | `/api/auth/devices/<id>` | Yes | Revoke a paired device |
| `GET` | `/api/auth/devices` | Yes | List paired devices |

¹ Token accepted via `?token=` query parameter (EventSource limitation)  
² POST endpoints require localhost access

## Docker

The Docker container is **self-contained** — all state lives in a named Docker volume. No host directories are mounted.

```bash
# Build
docker build \
  --build-arg HTTP_PROXY=$HTTP_PROXY \
  --build-arg HTTPS_PROXY=$HTTPS_PROXY \
  -t cc-monitor:latest .

# Run
docker compose up -d
```

**Hook installation** always uses the one-liner (the container cannot write to your host files):
```bash
curl -skSL https://<server>:9876/static/install-hooks.sh | SERVER_URL=https://<server>:9876 bash
```

**Persistence:** State, tokens, and certificates are stored in the `cc-monitor-data` Docker volume. To reset:
```bash
docker compose down -v
```

## Android App

The Flutter app provides mobile monitoring:

- **Server Discovery** — mDNS scanning + QR code pairing
- **Multi-Server** — Switch between servers from the sidebar drawer
- **Session Dashboard** — Active / Complete / Archived tabs with swipe actions
- **SSE Event Log** — Filterable log with log level selector (Debug/Info/Warning/Error)
- **Connection Status** — Disconnected banner + heartbeat watchdog

### Build

```bash
# Using Flutter Docker (proxy-aware)
make build-apk

# Install
make adb-install
# or: adb install android_app/build/app/outputs/flutter-apk/app-debug.apk
```

## Architecture

```
┌─────────────────┐     POST /api/event     ┌──────────────┐
│  Claude Code    │ ───────────────────────→ │  cc-monitor  │
│  (hooks)        │                          │  (FastAPI)   │
│                 │  write state files       │              │
│  ~/.cc-monitor/ │ ←─────────────────────→ │  SSE stream  │
└─────────────────┘                          └──────┬───────┘
                                                    │
                    ┌───────────────────────────────┼───────────
                    │                               │
              ┌─────┴─────┐                  ┌──────┴──────┐
              │ Web UI    │                  │ Android App │
              │ (static)  │                  │ (Flutter)   │
              └───────────┘                  └─────────────┘
```

- **Hook scripts** (stdlib-only Python) detect state changes, write files, and POST to server
- **StateManager** holds in-memory state, persists to disk, broadcasts via SSE
- **Dashboard** (vanilla HTML/CSS/JS) connects via EventSource, renders session cards
- **Android app** uses Dio for REST + custom SSE parser with auto-reconnect

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests (145 tests)
pytest tests/ -q

# Start dev server
cc-monitor --port 9876

# Restart server (kill + reinstall + start)
make restart-server
```

## Project Layout

```
cc-monitor/
├── src/cc_monitor/       # Python package (FastAPI server)
├── hooks/                # Hook scripts (stdlib-only, no deps)
├── static/               # Web dashboard (vanilla HTML/CSS/JS)
├── scripts/              # install-hooks.sh, uninstall-hooks.sh, restart-server.sh
├── android_app/          # Flutter Android app
├── tests/                # pytest test suite (145 tests)
├── Dockerfile            # Python server image
├── Dockerfile.flutter    # Flutter build image
└── docker-compose.yaml   # Docker deployment
```

---

<a name="chinese"></a>
# cc-monitor

[**→ 打开仪表盘**](https://bolunhan.github.io/cc-monitor/)
[![Deploy GH Pages](https://github.com/BolunHan/cc-monitor/actions/workflows/deploy-gh-pages.yml/badge.svg)](https://github.com/BolunHan/cc-monitor/actions/workflows/deploy-gh-pages.yml)

Claude Code 实时会话监控系统 — 通过网络仪表盘、Android 应用和 REST API 跟踪空闲、工作中、等待审批和已完成的会话。

## 功能特性

- **📊 实时仪表盘** — SSE 驱动的 Web UI，包含会话卡片、状态标签和浏览器通知
- **📱 Android 应用** — 移动端监控，支持二维码配对、多服务器切换、SSE 事件日志
- **🔌 Hook 系统** — 通过 Claude Code 的 7 个 hook 事件自动检测状态
- **🔐 安全配对** — 基于 Token 的认证，支持二维码和 6 位数字审批
- **🐳 Docker** — 单容器部署，host 网络模式
- **🏠 多服务器** — 从单个仪表盘监控多个 Claude Code 实例
- **🌍 局域网发现** — mDNS 广播，自动发现局域网内的服务器

## 快速开始

### 1. 启动服务器

**Docker（推荐）：**
```bash
docker compose up -d
```

**原生运行：**
```bash
pip install -e ".[dev]"
cc-monitor --port 9876 --host 0.0.0.0
```

### 2. 安装 Hook

在运行 Claude Code 的机器上执行：
```bash
curl -skSL https://<服务器IP>:9876/static/install-hooks.sh | SERVER_URL=https://<服务器IP>:9876 bash
```

### 3. 打开仪表盘

- **本地访问：** [http://localhost:9876](http://localhost:9876)
- **远程访问：** [https://bolunhan.github.io/cc-monitor/](https://bolunhan.github.io/cc-monitor/)（在设置中填入你的服务器地址）

## 会话状态

| 状态 | 图标 | 含义 |
|-------|------|------|
| `working` | 🔵 | Claude 正在工作 — 执行工具或生成输出 |
| `pending_review` | 🟢 | Claude 完成响应 — 输出待审查（24h 无活动自动→空闲） |
| `idle` | ⚪ | 无活动 — 会话休眠中，等待输入 |
| `pending_approval` | 🟡 | Claude 需要权限才能继续（工具审批或权限提示） |
| `all_done` | ✅ | 会话已结束 |

## 认证与配对

当服务器绑定到非 localhost 地址时自动启用：
- **TLS 加密** — 自签名证书，含 SHA-256 指纹
- **mDNS 广播** — 局域网自动发现
- **Token 认证** — 所有 API 访问需要 Bearer token（localhost 免认证）

### 配对流程

**Web 仪表盘：**
1. 点击"Pair Device"→ 生成 6 位配对码
2. 在服务器机器上运行 `cc-monitor --approve <配对码>`
3. 仪表盘自动获取 token

**Android 应用：**
1. 扫描 Web 设置面板中的二维码
2. 应用确认配对并安全存储 token

## API 接口

| 方法 | 路径 | 说明 |
|--------|------|------|
| `POST` | `/api/event` | 提交 hook 事件 |
| `GET` | `/api/status` | 所有会话状态 |
| `GET` | `/api/status/<id>` | 单个会话状态 |
| `GET` | `/api/stream` | SSE 实时推送（state_update + 每 3s heartbeat） |
| `GET` | `/api/version` | 服务器版本 |
| `GET` | `/api/hooks-status` | 检查 hook 安装状态 |
| `POST` | `/api/install-hooks` | 安装 hook 到全局配置 |
| `POST` | `/api/uninstall-hooks` | 精确移除 cc-monitor hook |

## Docker

Docker 容器**完全自包含**——所有状态存储在命名的 Docker 卷中，不挂载任何主机目录。

```bash
# 构建
docker build -t cc-monitor:latest .

# 运行
docker compose up -d
```

**Hook 安装**始终使用一键命令（容器无法写入主机文件）：
```bash
curl -skSL https://<服务器>:9876/static/install-hooks.sh | SERVER_URL=https://<服务器>:9876 bash
```

**持久化：** 状态、token 和证书存储在 `cc-monitor-data` Docker 卷中。重置：
```bash
docker compose down -v
```

## Android 应用

Flutter 应用提供移动端监控：

- **服务器发现** — mDNS 扫描 + 二维码配对
- **多服务器支持** — 侧边栏切换服务器
- **会话仪表盘** — Active / Complete / Archived 标签页，支持滑动操作
- **SSE 事件日志** — 可筛选日志，支持日志级别选择（Debug/Info/Warning/Error）

### 构建

```bash
make build-apk    # 使用 Flutter Docker 构建
make adb-install  # 安装到设备
```

## 架构

```
┌─────────────────┐     POST /api/event     ┌──────────────┐
│  Claude Code    │ ───────────────────────→ │  cc-monitor  │
│  (hooks)        │                          │  (FastAPI)   │
│                 │  写入状态文件            │              │
│  ~/.cc-monitor/ │ ←─────────────────────→ │  SSE 流      │
└─────────────────┘                          └──────┬───────┘
                                                    │
                    ┌───────────────────────────────┼───────────
                    │                               │
              ┌─────┴─────┐                  ┌──────┴──────┐
              │ Web UI    │                  │ Android App │
              │ (static)  │                  │ (Flutter)   │
              └───────────┘                  └─────────────┘
```

- **Hook 脚本**（纯 stdlib Python）检测状态变化、写入文件、POST 到服务器
- **StateManager** 维护内存状态、持久化到磁盘、通过 SSE 广播
- **仪表盘**（原生 HTML/CSS/JS）通过 EventSource 连接，渲染会话卡片
- **Android 应用** 使用 Dio 进行 REST 请求 + 自定义 SSE 解析器（自动重连）
