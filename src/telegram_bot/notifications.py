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

        logger.info(f"通知服务已初始化，聊天ID: {chat_id}")

    async def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """发送消息到配置的聊天"""
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
        is_simulated: bool = True,
        target_wallet: str = None
    ):
        """发送跟单交易通知"""

        mode_emoji = "🧪" if is_simulated else "✅"
        mode_text = "[模拟]" if is_simulated else ""

        target_text = ""
        if target_wallet:
            short = f"{target_wallet[:6]}...{target_wallet[-4:]}"
            target_text = f"\n<b>来源目标：</b> <code>{short}</code>"

        message = f"""
{mode_emoji} <b>跟单成功！</b> {mode_text}

<b>交易对：</b> {symbol}
<b>方向：</b> {side.upper()}
<b>你的数量：</b> {size:.4f}
<b>开仓价：</b> ${entry_price:,.2f}
<b>杠杆：</b> {leverage}x
<b>名义价值：</b> ${size * entry_price:,.2f}{target_text}

━━━━━━━━━━━━━━━━━━
<b>目标数量：</b> {target_size:.4f}
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
        target_wallets: list[str] = None
    ):
        """发送每小时交易报告"""

        pnl_emoji = "📈" if account_pnl_usd > 0 else "📉"

        wallets = target_wallets or []
        if len(wallets) == 1:
            targets_text = f"<code>{wallets[0][:10]}...{wallets[0][-6:]}</code>"
        else:
            targets_text = f"{len(wallets)} 个目标"
            for w in wallets:
                targets_text += f"\n  <code>{w[:6]}...{w[-4:]}</code>"

        message = f"""
📊 <b>每小时跟单报告</b>

<b>目标：</b> {targets_text}

━━━━━━━━━━━━━━━━━━━━━━━━━
📈 <b>跟单笔数：</b> {trades_copied}
💰 <b>账户盈亏：</b> {pnl_emoji} ${account_pnl_usd:,.2f} ({account_pnl_pct:+.2f}%)
📍 <b>持仓数量：</b> {open_positions}
📝 <b>挂单数量：</b> {open_orders}
━━━━━━━━━━━━━━━━━━━━━━━━━

🕐 <b>报告时间：</b> {datetime.now().strftime('%H:%M UTC')}
"""
        await self.send_message(message.strip())

    async def send_startup_notification(
        self,
        target_wallets: list[str] = None,
        ratios: dict[str, str] = None,
        leverage_adjustment: float = 1.0
    ):
        """发送机器人启动通知"""
        wallets = target_wallets or []
        ratio_map = ratios or {}

        if len(wallets) == 1:
            targets_text = f"<code>{wallets[0]}</code>"
            ratio_text = ratio_map.get(wallets[0], "N/A")
            ratio_line = f"• 比率: {ratio_text}"
        else:
            targets_text = f"{len(wallets)} 个目标钱包："
            for w in wallets:
                r = ratio_map.get(w, "N/A")
                short = f"{w[:6]}...{w[-4:]}"
                targets_text += f"\n  <code>{short}</code> ({r})"
            ratio_line = "• 比率: 见上方各目标"

        message = f"""
🚀 <b>跟单交易机器人已启动</b>

<b>目标钱包：</b>
{targets_text}

<b>配置信息：</b>
{ratio_line}
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

