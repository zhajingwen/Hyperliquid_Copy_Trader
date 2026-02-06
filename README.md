# Hyperliquid 跟单交易机器人

<p align="center">
  <a href="https://hyperfoundation.org/" target="_blank">
    <img src="https://www.cryptoninjas.net/wp-content/uploads/hyperliquid-logo-330x330.webp" alt="Hyperliquid Logo" width="200"/>
  </a>
</p>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://www.docker.com/)

Hyperliquid DEX 自动跟单交易机器人。实时复制任意钱包的交易，并自动调整仓位大小。

## 功能特性

- 通过 WebSocket 实时跟单
- 根据账户余额比例自动计算仓位大小
- 整数杠杆，支持资产特定上限
- 支持市价单和限价单
- 启动时自动复制已有持仓
- 模拟交易模式，可用于测试
- Telegram 通知（可选）

## 快速开始

### Docker（推荐）

```bash
docker-compose up -d
```

### 手动安装

1. 安装 Python 3.12+
2. 安装依赖：

```bash
pip install -r requirements.txt
```

3. 配置 .env 文件
4. 启动机器人：

```bash
python src/main.py
```

## 配置说明

编辑 `.env` 文件：

```properties
# Hyperliquid API
HYPERLIQUID_API_URL=https://api.hyperliquid.xyz

# 你的 Hyperliquid 凭证（留空则为模拟模式）
HYPERLIQUID_WALLET_ADDRESS=
HYPERLIQUID_PRIVATE_KEY=

# 跟单目标（钱包地址或金库地址）
TARGET_WALLET_ADDRESS=0x...

# 交易模式
SIMULATED_TRADING=true
SIMULATED_ACCOUNT_BALANCE=10000.0

# 跟单设置
COPY_OPEN_POSITIONS=true
COPY_EXISTING_ORDERS=true
AUTO_ADJUST_SIZE=true
USE_LIMIT_ORDERS=false
LEVERAGE_ADJUSTMENT=1.0
MAX_OPEN_TRADES=x
MAX_OPEN_ORDERS=x
MAX_ACCOUNT_EQUITY=x

# 资产过滤
BLOCKED_ASSETS=BTC,ETH  # 以逗号分隔（例如：BTC,ETH,SOL）

# Telegram（可选）
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# 数据库
DATABASE_URL=sqlite:///./data/trading.db

# 日志
LOG_LEVEL=INFO
LOG_FILE=./logs/trading.log
```

注意事项：
- `TARGET_WALLET_ADDRESS` 可以填写钱包地址或金库地址。
- `x` 表示不限制；设置整数可限制 `MAX_OPEN_TRADES`（最大开仓数）、`MAX_OPEN_ORDERS`（最大挂单数）或 `MAX_ACCOUNT_EQUITY`（最大账户权益）。
- Hyperliquid 强制要求每笔订单最低名义价值为 $10。如果你的账户远小于目标账户，当按比例计算的仓位低于 $10 时，小额成交将被跳过。增加账户余额或缩小比例差距可以跟单更多交易。

## 杠杆调整

`LEVERAGE_ADJUSTMENT` 设置用于控制风险：

- 0.5 = 使用目标杠杆的 50%（更安全）
- 1.0 = 完全匹配目标杠杆
- 2.0 = 使用目标杠杆的 200%（更激进）

杠杆会自动取整为整数，并限制在资产特定的最大值范围内。

## 屏蔽资产

`BLOCKED_ASSETS` 设置可以排除特定资产的跟单：

```properties
BLOCKED_ASSETS=BTC,ETH,SOL
```

当目标钱包交易这些资产时，机器人将：

- 记录警告日志
- 跳过该笔交易的跟单
- 继续正常监控其他资产

适用场景：

- 避免高波动性资产
- 排除你正在手动交易的资产
- 通过限制特定市场的敞口来管理风险

注意：资产代码不区分大小写（BTC、btc、Btc 均可）。

## 仓位计算

仓位大小根据你的账户余额与目标钱包余额的比例自动计算。

示例：

- 目标钱包：$100,000
- 你的账户：$10,000
- 比例：1:10
- 目标开仓 1 BTC = 你开仓 0.1 BTC

## Docker 命令

### Windows

使用 `windows/` 文件夹中的批处理文件：

```cmd
cd windows
start.bat    # 启动机器人
logs.bat     # 查看日志
stop.bat     # 停止机器人
```

### Linux/Mac

使用 `linux/` 文件夹中的 Shell 脚本：

```bash
cd linux
chmod +x *.sh       # 添加执行权限（仅首次需要）
./start.sh          # 启动机器人
./logs.sh           # 查看日志
./stop.sh           # 停止机器人
```

### 手动 Docker 命令

启动机器人：

```bash
docker-compose up -d
```

查看日志：

```bash
docker-compose logs -f
```

停止机器人：

```bash
docker-compose down
```

修改代码后重新构建：

```bash
docker-compose up -d --build
```

## Telegram 机器人

启用 Telegram 通知的步骤：

1. 在 Telegram 上通过 @BotFather 创建机器人
2. 获取机器人 Token
3. 向你的机器人发送一条消息
4. 通过以下链接获取 Chat ID：https://api.telegram.org/bot `<TOKEN>`/getUpdates
5. 将 Token 和 Chat ID 填入 .env 文件

可用命令：

- /status - 机器人状态和余额
- /positions - 当前持仓
- /pnl - 盈亏报告
- /pause - 暂停跟单
- /resume - 恢复跟单

## 免责声明

加密货币交易涉及重大损失风险。本软件按原样提供，不附带任何保证。使用风险自负。作者不对任何经济损失承担责任。

## 支持

Discord：maskiplays

## 捐赠

如果你觉得这个机器人有用，欢迎捐赠：

Arbitrum USDC：0x2987F53372c02D1a4C67241aA1840C1E83c480fF

## 写在最后
10/10 暴跌真他妈太惨了
Hyperliquid。
