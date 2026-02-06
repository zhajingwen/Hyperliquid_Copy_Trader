import os
from pathlib import Path
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
    report_interval_hours: int = 1

class SizingConfig(BaseModel):
    mode: str = "proportional"  # "fixed"（固定）或 "proportional"（按比例）
    fixed_size: float = 100.0
    portfolio_ratio: float = 0.01  # 1:100 比例
    max_position_size: float = 1000.0
    max_total_exposure: float = 5000.0

class LeverageConfig(BaseModel):
    adjustment_ratio: float = 0.5
    max_leverage: float = 10.0
    min_leverage: float = 1.0

class CopyRulesConfig(BaseModel):
    copy_existing_positions: bool = True
    copy_existing_orders: bool = True
    copy_open_positions: bool = True
    auto_adjust_size: bool = True
    use_limit_orders: bool = False  # 将市价单转为以当前成交价挂限价单
    max_open_trades: Optional[int] = None  # None = 无限制
    max_open_orders: Optional[int] = None  # None = 无限制
    max_account_equity: Optional[float] = None  # None = 无限制
    min_entry_quality_pct: float = 5.0
    max_slippage_pct: float = 1.0
    min_position_size_usd: float = 10.0
    blocked_assets: list[str] = []  # 不跟单的资产（如 ["BTC", "ETH"]）

class RiskManagementConfig(BaseModel):
    max_concurrent_positions: int = 10
    max_daily_loss_usd: float = 500.0
    enable_custom_stops: bool = False
    stop_loss_pct: float = 5.0

class Settings(BaseModel):
    # 跟单目标地址（钱包或金库地址，机器人统一处理）
    target_wallet: str = "0x0ba5de43fa2419a25c2e680f84aff3a8f57fce22"

    # 交易模式
    simulated_trading: bool = True
    simulated_account_balance: float = 1000.0

    # 各配置模块
    hyperliquid: HyperliquidConfig = Field(default_factory=HyperliquidConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    sizing: SizingConfig = Field(default_factory=SizingConfig)
    leverage: LeverageConfig = Field(default_factory=LeverageConfig)
    copy_rules: CopyRulesConfig = Field(default_factory=CopyRulesConfig)
    risk_management: RiskManagementConfig = Field(default_factory=RiskManagementConfig)

    # 路径配置
    log_level: str = "INFO"
    log_file: str = "./logs/trading.log"
    database_url: str = "sqlite:///./data/trading.db"

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'

    @classmethod
    def load(cls) -> 'Settings':
        """从环境变量加载配置"""
        settings = cls()

        # 从环境变量加载
        settings.hyperliquid.api_url = os.getenv('HYPERLIQUID_API_URL', settings.hyperliquid.api_url)
        settings.hyperliquid.wallet_address = os.getenv('HYPERLIQUID_WALLET_ADDRESS')
        settings.hyperliquid.private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')

        settings.target_wallet = os.getenv('TARGET_WALLET_ADDRESS', settings.target_wallet)

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
        settings.database_url = os.getenv('DATABASE_URL', settings.database_url)

        return settings

# 全局配置实例
settings = Settings.load()
