import asyncio
from typing import Optional
from datetime import datetime
from telegram import Bot
from loguru import logger


class NotificationService:
    """
    Telegram 通知服务
    """

    def __init__(self, bot_token: str, chat_id: str):
        """初始化通知服务

        Args:
            bot_token: Telegram 机器人令牌
            chat_id: 发送通知的聊天ID
        """
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id
        self.enabled = True

        logger.info(f"通知服务已初始化，聊天ID: {chat_id}")

    async def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """发送消息到配置的聊天"""
        if not self.enabled:
            logger.debug("通知已禁用，跳过发送")
            return False

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=parse_mode
            )
            return True
        except Exception as e:
            logger.error(f"发送 Telegram 消息失败: {e}")
            return False

    async def send_trade_notification(
        self,
        symbol: str,
        side: str,
        size: float,
        entry_price: float,
        leverage: float,
        target_size: float,
        is_simulated: bool = True
    ):
        """发送跟单交易通知"""

        mode_emoji = "🧪" if is_simulated else "✅"
        mode_text = "[模拟]" if is_simulated else ""

        message = f"""
{mode_emoji} <b>跟单成功！</b> {mode_text}

<b>交易对：</b> {symbol}
<b>方向：</b> {side.upper()}
<b>你的数量：</b> {size:.4f}
<b>开仓价：</b> ${entry_price:,.2f}
<b>杠杆：</b> {leverage}x
<b>名义价值：</b> ${size * entry_price:,.2f}

━━━━━━━━━━━━━━━━━━
<b>目标数量：</b> {target_size:.4f}
<b>时间：</b> {datetime.now().strftime('%H:%M:%S UTC')}
"""
        await self.send_message(message.strip())

    async def send_position_close_notification(
        self,
        symbol: str,
        pnl: Optional[float] = None,
        is_simulated: bool = True
    ):
        """发送平仓通知"""

        mode_emoji = "🧪" if is_simulated else "🔴"
        mode_text = "[模拟]" if is_simulated else ""

        pnl_text = ""
        if pnl is not None:
            pnl_emoji = "📈" if pnl > 0 else "📉"
            pnl_text = f"\n<b>盈亏：</b> {pnl_emoji} ${pnl:,.2f}"

        message = f"""
{mode_emoji} <b>持仓已平</b> {mode_text}

<b>交易对：</b> {symbol}{pnl_text}
<b>时间：</b> {datetime.now().strftime('%H:%M:%S UTC')}
"""
        await self.send_message(message.strip())

    async def send_hourly_report(
        self,
        trades_copied: int,
        account_pnl_usd: float,
        account_pnl_pct: float,
        open_positions: int,
        open_orders: int,
        target_wallet: str
    ):
        """发送每小时交易报告"""

        pnl_emoji = "📈" if account_pnl_usd > 0 else "📉"

        message = f"""
📊 <b>每小时跟单报告</b>

<b>目标：</b> <code>{target_wallet[:10]}...{target_wallet[-6:]}</code>

━━━━━━━━━━━━━━━━━━━━━━━━━
📈 <b>跟单笔数：</b> {trades_copied}
💰 <b>账户盈亏：</b> {pnl_emoji} ${account_pnl_usd:,.2f} ({account_pnl_pct:+.2f}%)
📍 <b>持仓数量：</b> {open_positions}
📝 <b>挂单数量：</b> {open_orders}
━━━━━━━━━━━━━━━━━━━━━━━━━

🕐 <b>报告时间：</b> {datetime.now().strftime('%H:%M UTC')}
"""
        await self.send_message(message.strip())

    async def send_error_notification(self, error_message: str):
        """发送错误通知"""
        message = f"""
⚠️ <b>检测到错误</b>

<code>{error_message}</code>

<b>时间：</b> {datetime.now().strftime('%H:%M:%S UTC')}
"""
        await self.send_message(message.strip())

    async def send_startup_notification(
        self,
        target_wallet: str,
        sizing_mode: str,
        ratio: str,
        leverage_adjustment: float
    ):
        """发送机器人启动通知"""
        message = f"""
🚀 <b>跟单交易机器人已启动</b>

<b>目标钱包：</b>
<code>{target_wallet}</code>

<b>配置信息：</b>
• 仓位模式: {sizing_mode.title()}
• 比率: {ratio}
• 杠杆: {leverage_adjustment}x（相对目标）
• 状态: <b>运行中</b> 🟢

机器人正在监控交易！
"""
        await self.send_message(message.strip())

    async def send_shutdown_notification(self):
        """发送机器人关闭通知"""
        message = """
🛑 <b>跟单交易机器人已停止</b>

机器人已安全关闭。
状态: <b>已停止</b> 🔴
"""
        await self.send_message(message.strip())

    def enable(self):
        """启用通知"""
        self.enabled = True
        logger.info("通知已启用")

    def disable(self):
        """禁用通知"""
        self.enabled = False
        logger.info("通知已禁用")
