import os
from typing import Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class HyperliquidConfig(BaseModel):
    api_url: str = Field(default="https://api.hyperliquid.xyz")
    ws_url: str = Field(default="wss://api.hyperliquid.xyz/ws")
    wallet_address: Optional[str] = None
    private_key: Optional[str] = None

class TelegramConfig(BaseModel):
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None

class SizingConfig(BaseModel):
    mode: str = "proportional"  # "fixed"（固定）或 "proportional"（按比例）
    portfolio_ratio: float = 0.01  # 1:100 比例
    max_position_size: float = 1000.0
    max_total_exposure: float = 5000.0

class LeverageConfig(BaseModel):
    adjustment_ratio: float = 0.5

class CopyRulesConfig(BaseModel):
    copy_existing_orders: bool = True
    copy_open_positions: bool = True
    auto_adjust_size: bool = True
    use_limit_orders: bool = False  # 将市价单转为以当前成交价挂限价单
    max_open_trades: Optional[int] = None  # None = 无限制
    max_open_orders: Optional[int] = None  # None = 无限制
    max_account_equity: Optional[float] = None  # None = 无限制
    blocked_assets: list[str] = []  # 不跟单的资产（如 ["BTC", "ETH"]）

class Settings(BaseModel):
    # Hyperliquid WebSocket 单连接最大用户订阅数
    MAX_TARGET_WALLETS = 10

    # 跟单目标地址列表（钱包或金库地址，支持逗号分隔配置多个，最多10个）
    target_wallets: list[str] = ["0x0ba5de43fa2419a25c2e680f84aff3a8f57fce22"]

    # 交易模式
    simulated_trading: bool = True
    simulated_account_balance: float = 1000.0

    # 各配置模块
    hyperliquid: HyperliquidConfig = Field(default_factory=HyperliquidConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    sizing: SizingConfig = Field(default_factory=SizingConfig)
    leverage: LeverageConfig = Field(default_factory=LeverageConfig)
    copy_rules: CopyRulesConfig = Field(default_factory=CopyRulesConfig)

    # 路径配置
    log_level: str = "INFO"
    log_file: str = "./logs/trading.log"

    @classmethod
    def load(cls) -> 'Settings':
        """从环境变量加载配置"""
        settings = cls()

        # 从环境变量加载
        settings.hyperliquid.api_url = os.getenv('HYPERLIQUID_API_URL', settings.hyperliquid.api_url)
        settings.hyperliquid.wallet_address = os.getenv('HYPERLIQUID_WALLET_ADDRESS')
        settings.hyperliquid.private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')

        # 解析逗号分隔的目标钱包地址
        raw_targets = os.getenv('TARGET_WALLET_ADDRESS', '')
        if raw_targets:
            settings.target_wallets = [
                addr.strip() for addr in raw_targets.split(',') if addr.strip()
            ]

        # Hyperliquid WebSocket 最多支持订阅 10 个用户的订单流
        if len(settings.target_wallets) > cls.MAX_TARGET_WALLETS:
            raise ValueError(
                f"目标钱包数量 ({len(settings.target_wallets)}) 超过 Hyperliquid WebSocket 限制 ({cls.MAX_TARGET_WALLETS})，"
                f"请减少 TARGET_WALLET_ADDRESS 中的地址数量"
            )

        # 交易模式
        sim_trading = os.getenv('SIMULATED_TRADING', 'true').lower()
        settings.simulated_trading = sim_trading in ('true', '1', 'yes')

        sim_balance = os.getenv('SIMULATED_ACCOUNT_BALANCE', '1000.0')
        settings.simulated_account_balance = float(sim_balance)

        # 跟单交易设置
        copy_open_pos = os.getenv('COPY_OPEN_POSITIONS', 'true').lower()
        settings.copy_rules.copy_open_positions = copy_open_pos in ('true', '1', 'yes')

        copy_orders = os.getenv('COPY_EXISTING_ORDERS', 'true').lower()
        settings.copy_rules.copy_existing_orders = copy_orders in ('true', '1', 'yes')

        auto_adjust = os.getenv('AUTO_ADJUST_SIZE', 'true').lower()
        settings.copy_rules.auto_adjust_size = auto_adjust in ('true', '1', 'yes')

        use_limit = os.getenv('USE_LIMIT_ORDERS', 'false').lower()
        settings.copy_rules.use_limit_orders = use_limit in ('true', '1', 'yes')

        # 杠杆调整
        leverage_adj = os.getenv('LEVERAGE_ADJUSTMENT', '0.5')
        settings.leverage.adjustment_ratio = float(leverage_adj)

        max_trades = os.getenv('MAX_OPEN_TRADES', 'x')
        settings.copy_rules.max_open_trades = None if max_trades.lower() == 'x' else int(max_trades)

        max_orders = os.getenv('MAX_OPEN_ORDERS', 'x')
        settings.copy_rules.max_open_orders = None if max_orders.lower() == 'x' else int(max_orders)

        max_equity = os.getenv('MAX_ACCOUNT_EQUITY', 'x')
        settings.copy_rules.max_account_equity = None if max_equity.lower() == 'x' else float(max_equity)

        # 屏蔽资产
        blocked = os.getenv('BLOCKED_ASSETS', '')
        settings.copy_rules.blocked_assets = [
            asset.strip().upper() for asset in blocked.split(',') if asset.strip()
        ]

        settings.telegram.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        settings.telegram.chat_id = os.getenv('TELEGRAM_CHAT_ID')

        settings.log_level = os.getenv('LOG_LEVEL', settings.log_level)
        settings.log_file = os.getenv('LOG_FILE', settings.log_file)

        return settings

# 全局配置实例
settings = Settings.load()
