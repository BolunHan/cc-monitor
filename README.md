<!-- Language switcher -->
<div align="right">

**[English](#english)** | **[中文](#chinese)**

</div>

---

<a name="english"></a>

# 🚦 cc-monitor — Cyber Traffic Light for Claude Code<br><small>Claude Code 赛博红绿灯</small>

[**→ Open Dashboard**](https://bolunhan.github.io/cc-monitor/)

[![Deploy GH Pages](https://github.com/BolunHan/cc-monitor/actions/workflows/deploy-gh-pages.yml/badge.svg)](https://github.com/BolunHan/cc-monitor/actions/workflows/deploy-gh-pages.yml)
[![Build Docker](https://github.com/BolunHan/cc-monitor/actions/workflows/build-docker.yml/badge.svg)](https://github.com/BolunHan/cc-monitor/actions/workflows/build-docker.yml)
[![Build APK](https://github.com/BolunHan/cc-monitor/actions/workflows/build-apk.yml/badge.svg)](https://github.com/BolunHan/cc-monitor/actions/workflows/build-apk.yml)

**Know when Claude needs you — before you waste time staring at the screen.**

Physical "Claude Code traffic light" gadgets sell for serious money. cc-monitor is the **free, open-source version** — it runs on any machine, pushes notifications to your phone and browser, and costs nothing. All you need is an Android phone or a browser tab.

> 🛡️ **Guard your vibe-coding flow.** When Claude is working, you're free. The moment it needs approval, hits an error, or finishes a review — you get pinged. No more babysitting the terminal.

---

## ⚠️ Security Warning

**Only install this tool from a trusted source.** The hook installer modifies `~/.claude/settings.json` — Claude Code's global configuration file. **A malicious hook script can steal your Claude API token** and gain full access to your Anthropic account. Never install hooks from a server you don't control.

- **Always inspect** the install script before running it: `curl -skSL <url>/static/install-hooks.sh | less`
- **Verify the source** — this repo is the only official distribution
- **Do NOT use sudo** — the hook scripts do not require root privileges and only modify your user-level Claude Code settings
- **Use localhost** when the server runs on the same machine (no auth required)

---

## Quick Start

### Option A: Docker from GHCR (no clone needed)

Pulls the pre-built image from GitHub Container Registry:

```bash
mkdir cc-monitor && cd cc-monitor
curl -O https://raw.githubusercontent.com/BolunHan/cc-monitor/main/docker-compose.yaml
docker compose up -d
```

### Option B: Docker local build (clone repo)

Build the image yourself from source:

```bash
git clone https://github.com/BolunHan/cc-monitor.git
cd cc-monitor
docker build -t ghcr.io/bolunhan/cc-monitor:latest .
docker compose up -d
```

### Option C: Native Python

```bash
git clone https://github.com/BolunHan/cc-monitor.git
cd cc-monitor
pip install .
cc-monitor --port 9876 --host 0.0.0.0
```

### Then: Install Hooks

On the machine where Claude Code runs:
```bash
curl -skSL https://<server-ip>:9876/static/install-hooks.sh | SERVER_URL=https://<server-ip>:9876 bash
```

> **🔐 One-time cert step:** Open `https://<server-ip>:9876` in your browser, click **Advanced** → **Proceed to site** to trust the self-signed certificate. Required when using the remote dashboard.

---

## Web Dashboard

Powerful zero-install monitoring — works from any browser.

**Local:** Open `https://localhost:9876` — connects automatically.

**Remote (GitHub Pages):** Go to [bolunhan.github.io/cc-monitor](https://bolunhan.github.io/cc-monitor/), open **Settings** (⚙), enter your server IP and port, then **Save & Reconnect**.

> 💡 **Browser notifications** work as a free alternative to the Android app — enable them when prompted and get pinged on state changes even without your phone nearby.

### What you can do

| Action           | How                                                                  |
| ---------------- | -------------------------------------------------------------------- |
| See all sessions | Active / Complete / Archived tabs with live state breakdown          |
| Get notified     | Browser push notifications on idle, pending review, pending approval |
| Pair devices     | QR code + 6-digit approval flow for the Android app                  |
| Manage hooks     | One-click install / uninstall / check from the Settings panel        |
| Switch language  | EN / 中文 toggle in the top bar                                      |

---

## Android App

Turn your phone into a dedicated Claude Code status monitor.

### Getting the app

Download the latest APK from [Releases](https://github.com/BolunHan/cc-monitor/releases) and install via ADB:
```bash
adb install cc-monitor-app-release.apk
```

### Connecting to a server

**LAN Scan (auto-discovery):**
1. Make sure the server is running with `--host 0.0.0.0` (mDNS is on by default)
2. Open the app — it auto-scans your local network
3. Tap a discovered server to pair

**QR Code Scan:**
1. In the web dashboard, click **⧉** (Pair Device) to show a QR code
2. In the app, tap **Scan QR Code** and point your camera
3. Pairing completes automatically

**Manual Entry:**
1. Tap **Manual Entry** in the app
2. Enter the server IP, port, and token (from the web dashboard's pairing panel)

### Managing servers

Open **Settings** (⚙) from the dashboard. You'll see:
- **Server cards** with connection status dots (green = connected, orange = disconnected, grey = inactive)
- **Forget** button on every server — removes it from your list
- **Pair New Server** to add another Claude Code instance
- **Language** switcher (System default / English / 中文)

---

## Session States — Your Traffic Light

| Light | State              | What it means                                              | Your move            |
| ----- | ------------------ | ---------------------------------------------------------- | -------------------- |
| 🔵     | `working`          | Claude is coding, running tools, generating output         | Go grab coffee ☕     |
| 🟢     | `pending_review`   | Claude finished — output ready for you                     | Review the results   |
| 🟡     | `pending_approval` | Claude needs permission (tool approval, permission prompt) | Approve or deny      |
| ⚪     | `idle`             | Nothing happening — session dormant                        | Send the next prompt |
| ✅     | `all_done`         | Session ended                                              | Archive and move on  |

**You get notified instantly** via browser push and/or Android notification on every state change that needs your attention.

---

## How It Works

```
Claude Code                    cc-monitor                  Web Dashboard
  (hooks)                        Server                    Android App
     |                             |  |
     |  POST /api/event            |  |  SSE stream
     +-----------------------------+  +---------------------->
                                   |
                                   +-- State files (~/.cc-monitor/)
                                   +-- mDNS (LAN discovery)
                                   +-- TLS + Token Auth
```

The server listens for 7 Claude Code hook events, tracks session state in memory, persists to disk, and pushes real-time updates to all connected clients via Server-Sent Events. The web dashboard and Android app render live session cards with color-coded states.

For the full technical reference, see [API Reference](#api-reference) and [Architecture](#architecture).

---

## API Reference

| Method   | Path                                  | Auth   | Description                                    |
| -------- | ------------------------------------- | ------ | ---------------------------------------------- |
| `POST`   | `/api/event`                          | Yes    | Submit a hook event                            |
| `GET`    | `/api/status`                         | Yes    | All sessions                                   |
| `GET`    | `/api/status/<id>`                    | Yes    | Single session                                 |
| `GET`    | `/api/stream`                         | Token¹ | SSE stream (state_update + heartbeat every 3s) |
| `GET`    | `/api/version`                        | No     | Server version                                 |
| `GET`    | `/api/hooks-status`                   | Yes    | Hook installation status                       |
| `POST`   | `/api/install-hooks`                  | Yes²   | Install hooks globally                         |
| `POST`   | `/api/uninstall-hooks`                | Yes²   | Remove cc-monitor hooks                        |
| `POST`   | `/api/session/<id>/archive`           | Yes    | Archive session                                |
| `POST`   | `/api/session/<id>/unarchive`         | Yes    | Unarchive session                              |
| `POST`   | `/api/session/<id>/complete`          | Yes    | Mark session done                              |
| `GET`    | `/api/auth/pair/qr`                   | No     | QR pairing payload                             |
| `POST`   | `/api/auth/pair/request`              | No     | Submit pairing request                         |
| `GET`    | `/api/auth/pair/request/<id>/status`  | No     | Poll request status                            |
| `POST`   | `/api/auth/pair/request/<id>/approve` | No     | Approve (localhost only)                       |
| `DELETE` | `/api/auth/devices/<id>`              | Yes    | Revoke device                                  |
| `GET`    | `/api/auth/devices`                   | Yes    | List paired devices                            |

¹ Token via `?token=` query parameter (EventSource limitation)  
² Requires localhost access

---

## Architecture

```
cc-monitor/
|--  src/cc_monitor/       # Python package (FastAPI server)
|--  hooks/                # Hook scripts (stdlib-only, no deps)
|--  static/               # Web dashboard (vanilla HTML/CSS/JS)
|--  scripts/              # install-hooks.sh, uninstall-hooks.sh
|--  android_app/          # Flutter Android app
|--  tests/                # pytest suite (145 tests)
|--  Dockerfile            # Python server image
|--  Dockerfile.flutter    # Flutter build image
+--  docker-compose.yaml   # Docker deployment
```

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -q          # 145 tests
cc-monitor --port 9876    # Start dev server
```

---

<a name="chinese"></a>

# 🚦 cc-monitor — Claude Code 赛博红绿灯

[**→ 打开仪表盘**](https://bolunhan.github.io/cc-monitor/)

[![Deploy GH Pages](https://github.com/BolunHan/cc-monitor/actions/workflows/deploy-gh-pages.yml/badge.svg)](https://github.com/BolunHan/cc-monitor/actions/workflows/deploy-gh-pages.yml)
[![Build Docker](https://github.com/BolunHan/cc-monitor/actions/workflows/build-docker.yml/badge.svg)](https://github.com/BolunHan/cc-monitor/actions/workflows/build-docker.yml)
[![Build APK](https://github.com/BolunHan/cc-monitor/actions/workflows/build-apk.yml/badge.svg)](https://github.com/BolunHan/cc-monitor/actions/workflows/build-apk.yml)

**Claude 需要你的时候，第一时间知道 — 不再白白盯着屏幕浪费时间。**

市面上那些"Claude Code 物理红绿灯"小玩意卖得可不便宜。cc-monitor 是**免费的、开源的替代方案** — 跑在任何机器上，推送到你的手机和浏览器，一毛钱不花。你只需要一台 Android 手机或一个浏览器标签页。

> 🛡️ **守护摸鱼时光安全，及时提醒手动接管 Claude Code。** Claude 干活时你自由，需要审批、出错、或完成审查的那一刻 — 你立刻收到通知。再也不用守着终端。

---

## ⚠️ 安全警告

**仅从可信来源安装此工具。** Hook 安装脚本会修改 `~/.claude/settings.json` — Claude Code 的全局配置文件。**恶意 hook 脚本可以窃取你的 Claude API token**，获得对你 Anthropic 账户的完全访问权限。切勿从不受你控制的服务器安装 hook。

- **务必先检查**安装脚本：`curl -skSL <url>/static/install-hooks.sh | less`
- **验证来源** — 此仓库是唯一的官方分发渠道
- **切勿使用 sudo** — hook 脚本无需 root 权限，仅修改用户级别的 Claude Code 配置
- **优先使用 localhost** — 当服务器运行在同一台机器上时无需认证

---

## 快速开始

### 方案 A：Docker（无需克隆仓库）

从 GitHub Container Registry 拉取预构建镜像：

```bash
mkdir cc-monitor && cd cc-monitor
curl -O https://raw.githubusercontent.com/BolunHan/cc-monitor/main/docker-compose.yaml
docker compose up -d
```

### 方案 B：Docker 本地构建（克隆仓库）

从源码自行构建镜像：

```bash
git clone https://github.com/BolunHan/cc-monitor.git
cd cc-monitor
docker build -t ghcr.io/bolunhan/cc-monitor:latest .
docker compose up -d
```

### 方案 C：原生 Python

```bash
git clone https://github.com/BolunHan/cc-monitor.git
cd cc-monitor
pip install .
cc-monitor --port 9876 --host 0.0.0.0
```

### 然后：安装 Hook

在运行 Claude Code 的机器上执行：
```bash
curl -skSL https://<服务器IP>:9876/static/install-hooks.sh | SERVER_URL=https://<服务器IP>:9876 bash
```

> **🔐 一次性证书步骤：** 在浏览器中打开 `https://<服务器IP>:9876`，点击 **高级** → **继续访问** 以信任自签名证书。使用远程仪表盘时必须执行此步骤。

---

## Web 仪表盘

功能强大的零安装监控 — 任何浏览器都能用。

**本地访问：** 打开 `https://localhost:9876` — 自动连接。

**远程访问（GitHub Pages）：** 前往 [bolunhan.github.io/cc-monitor](https://bolunhan.github.io/cc-monitor/)，打开 **设置**（⚙），输入服务器 IP 和端口，然后 **保存并重连**。

> 💡 **浏览器通知** 可作为 Android 应用的免费替代 — 被提示时启用，即可在状态变化时收到提醒，即使手机不在身边。

### 功能一览

| 功能         | 操作方式                                                 |
| ------------ | -------------------------------------------------------- |
| 查看所有会话 | Active / Complete / Archived 标签页，含实时状态统计      |
| 接收通知     | 浏览器推送通知（idle、pending review、pending approval） |
| 配对设备     | 二维码 + 6 位数字审批流程（供 Android 应用使用）         |
| 管理 Hook    | 设置面板中一键安装 / 卸载 / 检查                         |
| 切换语言     | 顶部 EN / 中文 切换按钮                                  |

---

## Android 应用

将手机变成专属的 Claude Code 状态监视器。

### 获取应用

从 [Releases](https://github.com/BolunHan/cc-monitor/releases) 下载最新 APK，通过 ADB 安装：
```bash
adb install cc-monitor-app-release.apk
```

### 连接服务器

**局域网扫描（自动发现）：**
1. 确保服务器以 `--host 0.0.0.0` 运行（mDNS 默认开启）
2. 打开应用 — 自动扫描本地网络
3. 点击发现的服务器进行配对

**二维码扫描：**
1. 在 Web 仪表盘中，点击 **⧉**（配对设备）显示二维码
2. 在应用中，点击 **扫描二维码**，将摄像头对准二维码
3. 配对自动完成

**手动输入：**
1. 在应用中点击 **手动输入**
2. 输入服务器 IP、端口和 token（从 Web 仪表盘配对面板获取）

### 管理服务器

从仪表盘打开 **设置**（⚙），你将看到：
- **服务器卡片** — 带连接状态圆点（绿色 = 已连接，橙色 = 已断开，灰色 = 未激活）
- **移除**按钮在每个服务器上 — 从列表中删除
- **配对新服务器** — 添加另一个 Claude Code 实例
- **语言**切换（跟随系统 / English / 中文）

---

## 会话状态 — 你的红绿灯

| 灯光 | 状态               | 含义                                  | 你该做什么           |
| ---- | ------------------ | ------------------------------------- | -------------------- |
| 🔵    | `working`          | Claude 正在写代码、执行工具、生成输出 | 去喝杯咖啡 ☕         |
| 🟢    | `pending_review`   | Claude 完成 — 输出等待审查            | 检查结果             |
| 🟡    | `pending_approval` | Claude 需要权限（工具审批、权限提示） | 批准或拒绝           |
| ⚪    | `idle`             | 无活动 — 会话休眠                     | 发送下一条提示       |
| ✅    | `all_done`         | 会话已结束                            | 归档，继续下一个任务 |

**每次需要你关注的状态变化，你都会立即通过浏览器推送和/或 Android 通知收到提醒。**

---

## 工作原理

```
Claude Code                    cc-monitor                  Web 仪表盘
  (hooks)                        Server                    Android 应用
     |                             |  |
     |  POST /api/event            |  |  SSE stream
     +-----------------------------+  +---------------------->
                                   |
                                   +-- 状态文件 (~/.cc-monitor/)
                                   +-- mDNS (局域网发现)
                                   +-- TLS + Token 认证
```

服务器监听 7 个 Claude Code hook 事件，在内存中追踪会话状态，持久化到磁盘，并通过 Server-Sent Events 向所有连接的客户端推送实时更新。Web 仪表盘和 Android 应用渲染带有颜色编码状态的实时会话卡片。

完整技术参考见 [API 接口](#api-接口) 和 [架构](#架构-1)。

---

## API 接口

| 方法     | 路径                                  | 说明                                           |
| -------- | ------------------------------------- | ---------------------------------------------- |
| `POST`   | `/api/event`                          | 提交 hook 事件                                 |
| `GET`    | `/api/status`                         | 所有会话状态                                   |
| `GET`    | `/api/status/<id>`                    | 单个会话状态                                   |
| `GET`    | `/api/stream`                         | SSE 实时推送（state_update + 每 3s heartbeat） |
| `GET`    | `/api/version`                        | 服务器版本                                     |
| `GET`    | `/api/hooks-status`                   | 检查 hook 安装状态                             |
| `POST`   | `/api/install-hooks`                  | 安装 hook 到全局配置                           |
| `POST`   | `/api/uninstall-hooks`                | 移除 cc-monitor hook                           |
| `POST`   | `/api/session/<id>/archive`           | 归档会话                                       |
| `POST`   | `/api/session/<id>/unarchive`         | 取消归档                                       |
| `POST`   | `/api/session/<id>/complete`          | 标记会话完成                                   |
| `GET`    | `/api/auth/pair/qr`                   | 二维码配对数据                                 |
| `POST`   | `/api/auth/pair/request`              | 提交配对请求                                   |
| `GET`    | `/api/auth/pair/request/<id>/status`  | 查询请求状态                                   |
| `POST`   | `/api/auth/pair/request/<id>/approve` | 批准配对（仅限 localhost）                     |
| `DELETE` | `/api/auth/devices/<id>`              | 撤销设备                                       |
| `GET`    | `/api/auth/devices`                   | 列出已配对设备                                 |

---

## 架构

```
cc-monitor/
|--  src/cc_monitor/       # Python 包（FastAPI 服务器）
|--  hooks/                # Hook 脚本（纯 stdlib，无依赖）
|--  static/               # Web 仪表盘（原生 HTML/CSS/JS）
|--  scripts/              # install-hooks.sh, uninstall-hooks.sh
|--  android_app/          # Flutter Android 应用
|--  tests/                # pytest 测试套件（145 个测试）
|--  Dockerfile            # Python 服务器镜像
|--  Dockerfile.flutter    # Flutter 构建镜像
+--  docker-compose.yaml   # Docker 部署
```

## 开发

```bash
pip install -e ".[dev]"
pytest tests/ -q          # 145 个测试
cc-monitor --port 9876    # 启动开发服务器
```
