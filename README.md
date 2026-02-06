# Hyperliquid 跟单交易机器人

<p align="center">
  <a href="https://hyperfoundation.org/" target="_blank">
    <img src="https://www.cryptoninjas.net/wp-content/uploads/hyperliquid-logo-330x330.webp" alt="Hyperliquid Logo" width="200"/>
  </a>
</p>

<p align="center">
  <strong>实时复制任意钱包交易 · 智能仓位管理 · 全自动化运行</strong>
</p>

<p align="center">
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"/></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python 3.12+"/></a>
  <a href="https://www.docker.com/"><img src="https://img.shields.io/badge/docker-ready-brightgreen.svg" alt="Docker"/></a>
  <img src="https://img.shields.io/badge/platform-linux%20%7C%20macOS%20%7C%20windows-lightgrey.svg" alt="Platform"/>
</p>

---

Hyperliquid DEX 自动跟单交易机器人。通过 WebSocket 实时监控多个目标钱包（最多 10 个），自动复制其永续合约交易，按比例智能调整仓位大小，支持模拟交易和 Telegram 远程控制。

## 目录

- [功能特性](#功能特性)
- [系统架构](#系统架构)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [配置详解](#配置详解)
- [工作原理](#工作原理)
- [Telegram 机器人](#telegram-机器人)
- [部署方式](#部署方式)
- [风险管理](#风险管理)
- [常见问题](#常见问题)
- [故障排除](#故障排除)
- [免责声明](#免责声明)
- [支持与捐赠](#支持与捐赠)

## 功能特性

### 实时跟单引擎
- **多钱包跟单** — 支持同时跟单最多 10 个目标地址（Hyperliquid WebSocket 上限），逗号分隔配置
- **WebSocket 实时监控** — 通过 `userEvents` 频道订阅目标钱包，毫秒级响应交易信号
- **全事件覆盖** — 支持新开仓、平仓、加仓、减仓、翻转仓位等所有操作类型
- **成交追踪** — 跟踪部分成交和完全成交事件，精确复制每一笔交易
- **启动同步** — 启动时自动复制所有目标钱包的已有持仓和挂单
- **独立比率** — 每个目标钱包自动计算独立的仓位比率

### 智能仓位管理
- **比例模式（默认）** — 根据你与目标的账户余额比例自动缩放仓位
  - 例：目标 $100,000，你 $10,000 → 比例 1:10 → 目标开 1 BTC，你开 0.1 BTC
- **固定模式** — 每笔交易使用固定金额，不受目标仓位大小影响
- **最小订单检查** — 自动过滤低于 Hyperliquid $10 最小名义价值的订单

### 杠杆控制
- **杠杆倍率调整** — 通过乘数灵活控制风险（0.5x 更保守，2.0x 更激进）
- **资产特定上限** — 不同资产自动限制最大杠杆
  | 资产类别 | 最大杠杆 |
  |---------|---------|
  | BTC / ETH | 50x |
  | SOL / MATIC / ARB / OP / AVAX / DOGE | 20x |
  | 其他资产 | 10x |
- **整数取整** — 自动适配 Hyperliquid 仅支持整数杠杆的要求

### 订单类型
- **市价单** — 即时执行（默认）
- **限价单** — 可将市价单转换为以入场价挂限价单
- **入场质量检查** — 当前价格偏离入场价超过 5% 时自动跳过

### 模拟交易
- **零风险测试** — 默认模拟模式，无需真实资金即可验证策略
- **虚拟账本** — 模拟余额追踪，计算虚拟盈亏
- **无缝切换** — 通过 `.env` 一键切换模拟 / 实盘模式

### Telegram 远程控制
- 查看状态、持仓、盈亏
- 暂停 / 恢复跟单
- 紧急一键平仓
- 定时汇总报告（每小时）
- 单一 Chat ID 鉴权保护

### 资产过滤
- 屏蔽指定资产（如 BTC、ETH、SOL），机器人将跳过这些资产的跟单
- 大小写不敏感，灵活配置

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                      主控制器 (main.py)                   │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  配置管理     │  │  回调处理     │  │  生命周期管理   │  │
│  │  settings.py │  │  事件分发     │  │  启停 / 信号    │  │
│  └──────┬──────┘  └──────┬───────┘  └───────┬────────┘  │
│         │                │                   │           │
├─────────┼────────────────┼───────────────────┼───────────┤
│         ▼                ▼                   ▼           │
│  ┌────────────────────────────────────────────────────┐  │
│  │               跟单引擎 (copy_engine/)               │  │
│  │  ┌────────────┐ ┌─────────────┐ ┌───────────────┐ │  │
│  │  │  钱包监控   │ │  交易执行    │ │  仓位计算      │ │  │
│  │  │ monitor.py │ │ executor.py │ │ position_sizer│ │  │
│  │  │            │ │             │ │   .py         │ │  │
│  │  │ · 多目标状态│ │ · 市价/限价  │ │ · 比例模式    │ │  │
│  │  │ · 事件检测  │ │ · EIP-712签名│ │ · 固定模式    │ │  │
│  │  │ · 变更比对  │ │ · 模拟执行   │ │ · 杠杆计算    │ │  │
│  │  └─────┬──────┘ └──────┬──────┘ └───────────────┘ │  │
│  └────────┼───────────────┼──────────────────────────┘  │
│           │               │                              │
├───────────┼───────────────┼──────────────────────────────┤
│           ▼               ▼                              │
│  ┌──────────────────────────────────────┐                │
│  │      Hyperliquid API (hyperliquid/) │                │
│  │  ┌───────────┐  ┌────────────────┐  │                │
│  │  │ REST 客户端│  │ WebSocket 客户端│  │                │
│  │  │ client.py │  │ websocket.py   │  │                │
│  │  │           │  │                │  │                │
│  │  │ · 账户状态 │  │ · 实时事件     │  │                │
│  │  │ · 市场价格 │  │ · 自动重连     │  │                │
│  │  │ · 资产列表 │  │ · 多用户订阅   │  │                │
│  │  └───────────┘  └────────────────┘  │                │
│  └──────────────────────────────────────┘                │
│                                                          │
│  ┌──────────────────────────────────────┐                │
│  │      Telegram 机器人 (telegram_bot/) │                │
│  │  ┌───────────┐  ┌────────────────┐  │                │
│  │  │ 命令处理   │  │  通知服务      │  │                │
│  │  │  bot.py   │  │notifications.py│  │                │
│  │  └───────────┘  └────────────────┘  │                │
│  └──────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────┘
```

### 项目结构

```
Hyperliquid_Copy_Trader/
├── src/                          # 源代码（~3,300 行）
│   ├── main.py                   # 主入口 & 回调逻辑
│   ├── config/
│   │   └── settings.py           # Pydantic v2 配置管理
│   ├── hyperliquid/
│   │   ├── models.py             # 数据模型（Position, Order, Trade, UserState）
│   │   ├── client.py             # REST API 客户端
│   │   └── websocket.py          # WebSocket 实时连接
│   ├── copy_engine/
│   │   ├── monitor.py            # 钱包事件监控 & 变更检测
│   │   ├── executor.py           # 订单执行 & EIP-712 签名
│   │   └── position_sizer.py     # 仓位计算 & 杠杆管理
│   ├── telegram_bot/
│   │   ├── bot.py                # Telegram 命令处理
│   │   └── notifications.py      # 通知推送服务
│   └── utils/
│       └── logger.py             # Loguru 日志配置
├── linux/                        # Linux/macOS 启动脚本
│   ├── start.sh
│   ├── logs.sh
│   └── stop.sh
├── windows/                      # Windows 批处理脚本
│   ├── start.bat
│   ├── logs.bat
│   └── stop.bat
├── .env.example                  # 配置模板
├── requirements.txt              # Python 依赖
├── Dockerfile                    # 容器镜像
├── docker-compose.yml            # 容器编排
└── LICENSE                       # MIT 许可证
```

## 环境要求

- **Python** 3.12 或更高版本
- **Docker**（可选，推荐部署方式）
- **Hyperliquid 账户** — 需要钱包地址和私钥（模拟模式不需要）
- **Telegram 机器人**（可选）— 用于远程控制和通知

### 核心依赖

| 库 | 版本 | 用途 |
|---|------|------|
| `aiohttp` | 3.9.1 | 异步 HTTP 客户端（REST API） |
| `websockets` | 12.0 | WebSocket 实时连接 |
| `eth-account` | 0.11.0 | EIP-712 交易签名 |
| `web3` | 6.11.3 | 以太坊工具库 |
| `pydantic` | 2.5.0 | 配置验证 |
| `python-telegram-bot` | 20.7 | Telegram Bot API |
| `loguru` | 0.7.2 | 高级日志（带颜色输出） |
| `sqlalchemy` | 2.0.23 | 数据库 ORM |
| `python-dotenv` | 1.0.0 | 环境变量加载 |

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/MaxIsOntoSomething/Hyperliquid_Copy_Trader.git
cd Hyperliquid_Copy_Trader
```

### 2. 创建配置文件

```bash
cp .env.example .env
```

编辑 `.env`，至少填写 `TARGET_WALLET_ADDRESS`（跟单目标地址）。支持逗号分隔配置多个目标：

```properties
# 单个目标
TARGET_WALLET_ADDRESS=0xAAA...

# 多个目标（最多10个）
TARGET_WALLET_ADDRESS=0xAAA...,0xBBB...,0xCCC...
```

首次使用建议保持模拟模式。

### 3. 启动机器人

**方式一：Docker（推荐）**

```bash
docker-compose up -d
```

**方式二：本地运行**

```bash
pip install -r requirements.txt
python src/main.py
```

### 4. 验证运行

```bash
# Docker 用户
docker-compose logs -f

# 本地运行用户
# 查看 ./logs/trading.log 或终端输出
```

如果配置了 Telegram，发送 `/status` 查看机器人状态。

## 配置详解

所有配置通过 `.env` 文件管理，支持以下参数：

### Hyperliquid 连接

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `HYPERLIQUID_API_URL` | string | `https://api.hyperliquid.xyz` | REST API 地址 |
| `HYPERLIQUID_WALLET_ADDRESS` | string | 空 | 你的钱包地址（留空 = 模拟模式） |
| `HYPERLIQUID_PRIVATE_KEY` | string | 空 | 钱包私钥（留空 = 模拟模式） |
| `TARGET_WALLET_ADDRESS` | string | **必填** | 跟单目标地址，支持逗号分隔多个（最多 10 个） |

### 交易模式

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `SIMULATED_TRADING` | bool | `true` | 模拟交易模式开关 |
| `SIMULATED_ACCOUNT_BALANCE` | float | `10000.0` | 模拟初始余额（美元） |

### 跟单行为

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `COPY_OPEN_POSITIONS` | bool | `true` | 启动时复制已有持仓 |
| `COPY_EXISTING_ORDERS` | bool | `true` | 启动时复制已有挂单 |
| `AUTO_ADJUST_SIZE` | bool | `true` | 按余额比例自动调整仓位（`false` = 固定模式） |
| `USE_LIMIT_ORDERS` | bool | `false` | 将市价单转为限价单执行 |
| `LEVERAGE_ADJUSTMENT` | float | `1.0` | 杠杆倍率调整（0.5 = 保守，2.0 = 激进） |

### 风控限制

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `MAX_OPEN_TRADES` | int / `x` | `x` | 最大同时持仓数（`x` = 不限制） |
| `MAX_OPEN_ORDERS` | int / `x` | `x` | 最大挂单数（`x` = 不限制） |
| `MAX_ACCOUNT_EQUITY` | float / `x` | `x` | 最大账户权益，超过后停止跟单（`x` = 不限制） |
| `BLOCKED_ASSETS` | string | 空 | 屏蔽资产列表，逗号分隔（如 `BTC,ETH,SOL`） |

### Telegram 通知

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `TELEGRAM_BOT_TOKEN` | string | 空 | Telegram Bot Token（留空 = 禁用） |
| `TELEGRAM_CHAT_ID` | string | 空 | 你的 Telegram Chat ID |

### 存储与日志

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `DATABASE_URL` | string | `sqlite:///./data/trading.db` | 数据库连接地址 |
| `LOG_LEVEL` | string | `INFO` | 日志级别（DEBUG / INFO / WARNING / ERROR） |
| `LOG_FILE` | string | `./logs/trading.log` | 日志文件路径 |

## 工作原理

### 启动流程

```
启动 main.py
    │
    ├── 1. 加载 .env 配置并验证（校验目标地址数量 ≤ 10）
    ├── 2. 初始化组件（API客户端、监控器、执行器、仓位计算器）
    ├── 3. 验证凭证（实盘模式下校验私钥与地址匹配）
    ├── 4. 遍历所有目标钱包，获取初始状态
    ├── 5. 为每个目标独立计算钱包余额比例（如 目标A 1:10, 目标B 1:50）
    ├── 6. [可选] 遍历所有目标，复制已有持仓（COPY_OPEN_POSITIONS）
    ├── 7. [可选] 遍历所有目标，复制已有挂单（COPY_EXISTING_ORDERS）
    ├── 8. [可选] 启动 Telegram 机器人和定时报告
    └── 9. 为每个目标创建 WebSocket 订阅，进入监听循环
```

### 实时跟单循环

```
WebSocket 接收事件
    │
    ├── 新开仓 ──→ 计算你的仓位大小 → 检查最小$10 → 执行市价单 → 通知
    ├── 平仓   ──→ 平掉你的对应仓位 → 计算盈亏 → 更新余额 → 通知
    ├── 加/减仓 ──→ 调整你的对应仓位 → 执行增减量订单 → 通知
    ├── 新挂单 ──→ 计算你的订单大小 → 执行对应限价单 → 通知
    ├── 订单成交 ──→ 判断方向（开仓/平仓/翻转）→ 执行匹配订单 → 通知
    └── 订单取消 ──→ 记录日志
```

### 仓位计算示例

**比例模式（AUTO_ADJUST_SIZE=true）：**

```
目标钱包余额:  $100,000
你的账户余额:  $1,000
钱包比例:      0.01 (1:100)

目标开仓: 2 BTC @ 50x 杠杆 (做多)
├── 你的仓位: 2 × 0.01 = 0.02 BTC
├── 杠杆计算: 50 × 1.0(倍率) = 50 → min(50, 50) = 50x
├── 名义价值: 0.02 × $60,000 = $1,200 ✓ (> $10 最小值)
└── 执行: 市价做多 0.02 BTC @ 50x
```

**多目标独立比率示例：**

```
你的账户余额:       $1,000

目标A 余额: $100,000 → 比率 1:100 → 目标A 开 1 BTC，你跟 0.01 BTC
目标B 余额: $50,000  → 比率 1:50  → 目标B 开 1 BTC，你跟 0.02 BTC
目标C 余额: $10,000  → 比率 1:10  → 目标C 开 1 BTC，你跟 0.10 BTC
```

**杠杆调整示例（LEVERAGE_ADJUSTMENT=0.5）：**

```
目标杠杆:  20x
调整后:    20 × 0.5 = 10 → 取整 = 10x
资产上限:  SOL 最大 20x
最终杠杆:  min(10, 20) = 10x ✓
```

## Telegram 机器人

### 设置步骤

1. 在 Telegram 中搜索 **@BotFather**，发送 `/newbot` 创建机器人
2. 记录返回的 **Bot Token**
3. 向你的新机器人发送任意消息
4. 访问 `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` 获取 **Chat ID**
5. 将 Token 和 Chat ID 填入 `.env` 文件

### 可用命令

| 命令 | 功能 | 示例输出 |
|------|------|---------|
| `/status` | 机器人运行状态、所有目标及比率、余额 | 运行中 · 3个目标 · 余额 $10,234.56 · 已跟单 15 笔 |
| `/positions` | 按目标分组显示所有持仓及盈亏 | [0xAAA...BBB] BTC 做多 0.02 · 盈亏 +$45.20 |
| `/orders` | 待执行挂单列表 | ETH 限价买入 0.5 @ $3,200 |
| `/pnl` | 盈亏汇总报告 | 总盈亏 +$234.56 · 胜率 68% |
| `/pause` | 暂停跟单（保留现有持仓） | 跟单已暂停 |
| `/resume` | 恢复跟单 | 跟单已恢复 |
| `/stop` | 平掉所有仓位并停止机器人 | 正在平仓... 机器人已停止 |

### 自动通知

- **交易执行** — 每笔跟单成功后即时推送
- **持仓关闭** — 平仓时推送盈亏详情
- **每小时汇总** — 定时发送账户状态和持仓概览
- **异常告警** — 错误和异常情况即时通知

## 部署方式

### Docker（推荐）

最简单的部署方式，自动处理依赖和环境。

```bash
# 启动（后台运行）
docker-compose up -d

# 查看实时日志
docker-compose logs -f

# 停止
docker-compose down

# 修改代码后重新构建
docker-compose up -d --build
```

Docker 数据卷映射：
- `./data:/app/data` — 数据库持久化
- `./logs:/app/logs` — 日志文件
- `./.env:/app/.env` — 配置文件

### Linux / macOS

使用 `linux/` 目录中的便捷脚本：

```bash
cd linux
chmod +x *.sh       # 首次使用需添加执行权限

./start.sh           # 启动机器人
./logs.sh            # 查看日志
./stop.sh            # 停止机器人
```

### Windows

使用 `windows/` 目录中的批处理文件：

```cmd
cd windows
start.bat            REM 启动机器人
logs.bat             REM 查看日志
stop.bat             REM 停止机器人
```

### 手动运行

```bash
# 安装依赖
pip install -r requirements.txt

# 启动
python src/main.py

# 后台运行（Linux/macOS）
nohup python src/main.py > /dev/null 2>&1 &
```

## 风险管理

本机器人内置多层安全机制：

| 安全特性 | 说明 |
|---------|------|
| **目标数量上限** | 最多 10 个目标地址（Hyperliquid WebSocket 限制），超出时启动报错 |
| **模拟模式默认开启** | 首次运行使用虚拟资金，不会产生真实交易 |
| **最小名义价值检查** | 低于 $10 的订单自动跳过（Hyperliquid 限制） |
| **入场质量检查** | 当前价格偏离入场价 >5% 时跳过，避免追高/追低 |
| **最大持仓数限制** | 可配置同时持仓上限 |
| **最大权益限制** | 账户权益超过阈值后自动停止跟单 |
| **资产级杠杆上限** | 按资产类别设置最大杠杆，防止过度杠杆化 |
| **资产黑名单** | 屏蔽特定高风险资产 |
| **Telegram 鉴权** | 仅响应指定 Chat ID 的命令 |
| **优雅退出** | Ctrl+C 信号处理，确保资源正确释放 |
| **状态刷新延迟** | 成交处理前等待 1.5s 确保状态同步 |

### 安全建议

> **私钥安全**：永远不要将 `.env` 文件提交到版本控制。`.gitignore` 已默认排除该文件。
>
> **从模拟开始**：首次使用务必以模拟模式运行，确认跟单逻辑符合预期后再切换实盘。
>
> **小额试水**：切换实盘时，建议先用少量资金测试，确认一切正常后再投入更多。
>
> **监控运行**：定期通过 Telegram 或日志检查机器人状态，确保正常运行。

## 常见问题

### Q: 什么情况下交易会被跳过？

以下情况机器人会跳过跟单：
- 按比例计算后的名义价值低于 $10（Hyperliquid 最小要求）
- 当前价格偏离目标入场价超过 5%
- 该资产在 `BLOCKED_ASSETS` 黑名单中
- 已达到 `MAX_OPEN_TRADES` 上限
- 账户权益已超过 `MAX_ACCOUNT_EQUITY` 阈值
- 机器人处于暂停状态（通过 `/pause` 命令）

### Q: 账户余额远小于目标怎么办？

如果比例过小（如 1:1000），大部分交易按比例缩放后会低于 $10 最小值而被跳过。建议：
- 增加账户余额以缩小比例差距
- 使用固定模式（`AUTO_ADJUST_SIZE=false`）
- 关注被跳过的日志，评估实际跟单率

### Q: 杠杆为什么和目标不一样？

杠杆可能因以下原因不同：
- `LEVERAGE_ADJUSTMENT` 设置了非 1.0 的倍率
- Hyperliquid 仅支持整数杠杆，非整数值会被取整
- 触及了资产类别的最大杠杆上限

### Q: 最多可以同时跟单多少个地址？

最多 **10 个**。这是 Hyperliquid WebSocket 单连接的用户订阅上限。超过 10 个地址时机器人会在启动阶段报错。

### Q: 多目标跟单的仓位比率如何计算？

每个目标独立计算比率。例如你的余额 $1,000：
- 目标A 余额 $100,000 → 比率 1:100
- 目标B 余额 $20,000 → 比率 1:20

两个目标的交易信号互不影响，各自按独立比率跟单。

### Q: 多个目标交易同一资产会冲突吗？

不会。模拟持仓以 `目标地址:交易对` 为 key 独立追踪。例如目标A 和目标B 同时开 BTC 多头会被记录为两笔独立持仓。但在实盘模式下，由于你只有一个交易账户，两笔同向订单会合并为一个持仓。

### Q: 目标可以是金库地址吗？

可以。`TARGET_WALLET_ADDRESS` 同时支持普通钱包地址和金库（Vault）地址。

### Q: 如何仅模拟不交易？

确保以下配置：
```properties
SIMULATED_TRADING=true
HYPERLIQUID_WALLET_ADDRESS=
HYPERLIQUID_PRIVATE_KEY=
```
留空钱包地址和私钥，机器人将以模拟模式运行。

### Q: WebSocket 断线怎么办？

机器人内置自动重连机制，断线后会在 5 秒后自动尝试重新连接。重连期间的交易信号可能会丢失，但重连后会通过状态同步尽量恢复。

## 故障排除

### 机器人无法启动

```
检查清单：
1. Python 版本是否 >= 3.12？ → python --version
2. 依赖是否安装？         → pip install -r requirements.txt
3. .env 文件是否存在？     → cp .env.example .env
4. TARGET_WALLET_ADDRESS 是否填写？
```

### 启动报错"目标钱包数量超过限制"

Hyperliquid WebSocket 最多支持订阅 10 个用户的订单流。请减少 `TARGET_WALLET_ADDRESS` 中的地址数量至 10 个以内。

### 没有复制任何交易

```
检查清单：
1. 目标钱包是否有活跃交易？
2. 日志中是否有 "skipped" 或 "blocked" 提示？
3. BLOCKED_ASSETS 是否屏蔽了目标交易的资产？
4. 仓位计算后是否低于 $10 最小值？
5. 是否达到了 MAX_OPEN_TRADES 上限？
6. 机器人是否处于暂停状态？
```

### Telegram 机器人无响应

```
检查清单：
1. TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID 是否正确？
2. 是否向机器人发送过消息（需要先激活对话）？
3. Chat ID 是否与 .env 中的一致？
4. 查看日志中是否有 Telegram 相关错误信息
```

### 实盘交易失败

```
检查清单：
1. HYPERLIQUID_WALLET_ADDRESS 格式是否正确（0x...）？
2. HYPERLIQUID_PRIVATE_KEY 是否与钱包地址匹配？
3. 钱包中是否有足够的 USDC 余额？
4. 日志中的错误信息是什么？
```

## 免责声明

> **加密货币交易涉及重大损失风险。** 本软件按原样提供，不附带任何保证。使用风险自负。作者不对因使用本软件导致的任何经济损失承担责任。
>
> 跟单交易无法保证盈利，过去的收益不代表未来的回报。请务必了解杠杆交易的风险，仅投入你能承受损失的资金。

## 支持与捐赠

**Discord**：maskiplays

如果你觉得这个机器人有用，欢迎捐赠支持开发：

**Arbitrum USDC**：`0x2987F53372c02D1a4C67241aA1840C1E83c480fF`

## 许可证

本项目基于 [MIT 许可证](LICENSE) 开源。Copyright (c) 2026 MaxIsOntoSomething。
