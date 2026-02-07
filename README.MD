# 抖音直播数据记录站 (DouyinLiveHub)

> 一个功能完整的抖音直播数据记录站，支持多房间24小时记录、数据持久化存储、实时 Socket.IO 推送。

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/badge/uv-0.5%2B-purple)](https://github.com/astral-sh/uv)
[![Flask](https://img.shields.io/badge/Flask-3.0%2B-green)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)

## ⚠️ 免责声明

**本代码库所有代码均只用于学习研究交流，严禁用于包括但不限于商业谋利、破坏系统、盗取个人信息等不良不法行为，违反此声明使用所产生的一切后果均由违反声明使用者承担。**

如果涉及到侵权或其他相关利益问题，请联系项目维护者删除本库代码。

## ✨ 功能特性

- 🎯 **多房间监控** - 同时监控多个直播间，独立管理
- 📊 **实时数据展示** - Socket.IO 实时推送弹幕、礼物、观看人数等数据
- 🔄 **24小时监控** - 自动检测开播，断线重连，无需人工干预
- 💾 **数据持久化** - MySQL 存储所有消息、统计数据、贡献榜
- 📱 **响应式设计** - 完美适配手机、平板、电脑端
- 🎨 **美观界面** - Vue.js + TailwindCSS 构建的现代化 UI
- 🌐 **代理支持** - 支持 HTTP/SOCKS5 代理，避免 IP 限制
- 📈 **统计分析** - 按时间段统计直播数据，支持图表展示

## 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| **后端** | Python 3.8+ / Flask 3.0+ |
| **包管理** | uv |
| **数据库** | MySQL 8.0+ |
| **ORM** | SQLAlchemy 2.0+ |
| **实时通信** | Socket.IO / WebSocket |
| **前端** | Vue.js 2.6 / TailwindCSS 2.2 |
| **任务调度** | APScheduler |
| **日志** | Loguru |

## 📦 安装部署

### 1. 安装 uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 或使用 pip
pip install uv
```

### 2. 克隆项目

```bash
git clone https://github.com/yourusername/DouyinLiveHub.git
cd DouyinLiveHub
```

### 3. 安装依赖

```bash
./scripts/install.sh
```

### 4. 配置数据库

创建 MySQL 数据库：

```sql
CREATE DATABASE douyin_live CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 5. 配置环境变量

复制 `.env.example` 为 `.env` 并修改配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填写数据库连接信息等配置。

### 6. 初始化数据库

```bash
./scripts/init-db.sh
```

### 7. 下载用户等级图标（可选）

```bash
./scripts/download-levels.sh
```

### 8. 启动应用

```bash
./scripts/run.sh
```

访问 `http://localhost:5000` 查看管理界面。

## 📖 使用说明

### 添加监控房间

1. 点击"添加直播间"按钮
2. 输入直播间 ID（从 URL 中获取，如 `https://live.douyin.com/261378947940` 中的 `261378947940`）
3. 选择监控类型：
   - **手动监控**：主播未开播时直接停止
   - **24小时监控**：等待开播后自动开始，支持轮询检测
4. 是否启用自动重连

### 启动/停止监控

- 点击"启动监控"开始监控直播间
- 点击"停止监控"停止当前监控
- 支持实时修改监控配置（点击"编辑"按钮）

### 查看实时数据

- 进入房间详情页查看实时弹幕、礼物
- 查看贡献榜 TOP100
- 查看当场直播统计数据

## 📁 项目结构

```
DouyinLiveHub/
├── crawler/                # 爬虫模块
│   ├── __init__.py
│   ├── fetcher.py         # 核心抓取类
│   ├── signature.py       # 签名生成
│   └── js/                # JavaScript签名脚本
│       ├── sign.js
│       ├── a_bogus.js
│       └── webmssdk.js
├── api/                    # API 路由
│   └── rooms.py           # 房间管理 API
├── models/                 # 数据模型
│   └── database.py        # SQLAlchemy ORM 模型
├── services/              # 业务逻辑层
│   ├── data_service.py    # 数据服务
│   ├── room_manager.py    # 多房间管理器
│   └── scheduler_service.py # 任务调度
├── ws_handlers/           # WebSocket 处理
│   └── handlers.py       # 消息处理器
├── templates/             # 前端模板
│   ├── index.html        # 首页
│   ├── room.html         # 房间详情页
│   └── stats.html        # 统计页面
├── static/                # 静态资源
│   └── js/              # JavaScript 文件
├── protobuf/             # Protobuf 协议
├── utils/                # 工具函数
├── scripts/              # 运行脚本
│   ├── install.sh       # 安装依赖
│   ├── run.sh           # 启动 Web 版
│   ├── monitor.sh       # 启动命令行版
│   ├── init-db.sh       # 初始化数据库
│   └── download-levels.sh # 下载等级图标
├── config.py            # 配置文件
├── app.py               # Flask 应用入口
├── main.py              # 命令行入口
├── pyproject.toml       # 项目配置与依赖
├── .env.example         # 环境变量模板
└── README.md            # 本文件
```

## 🔧 配置说明

### 监控类型

| 类型 | 说明 | 适用场景 |
|------|------|----------|
| **手动监控** | 主播未开播时停止 | 临时监控正在直播的房间 |
| **24小时监控** | 等待开播，自动重连 | 长期监控某位主播 |

### 自动重连

- **启用**：连接断开后自动重连，达到最大次数后进入轮询模式
- **禁用**：连接断开后停止监控

### 代理设置

1. 点击"代理设置"按钮
2. 勾选"启用代理"
3. 配置代理类型、地址和端口
4. 点击"保存"

**注意**：修改代理后需要重启监控房间才能生效。

## 🐛 故障排查

### WebSocket 连接失败 (502 Bad Gateway)
- 临时性服务器问题，自动重连会处理
- 如持续失败，考虑启用代理

### IP 被风控
- 启用代理避免 IP 限制
- 使用高质量代理服务

### 直播间显示"已结束"
- 检查主播是否真的在直播
- 确认直播间 ID 是否正确

### 状态不一致
- 应用重启后会自动清理不一致的状态
- 手动点击"停止"再"启动"即可

## 📄 原项目

本项目基于 [saermart/DouyinLiveWebFetcher](https://github.com/saermart/DouyinLiveWebFetcher) 进行二次开发。

## 📄 许可证

本项目采用 GNU Affero General Public License v3.0 许可证开源。

本项目是网络服务软件，如果您修改或发布本程序，您需要：

1. 开放所有源代码
2. 在网络服务器上提供源代码的可访问副本
3. 在相同或相似的许可证下发布修改版本

详情请参阅 [LICENSE](LICENSE) 文件。

## 🌟 Star History

如果这个项目对你有帮助，请给个 Star ⭐️
