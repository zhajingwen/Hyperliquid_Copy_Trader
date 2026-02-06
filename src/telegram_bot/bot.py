import asyncio
from typing import Optional, Callable
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)
from loguru import logger


class TelegramBot:
    """
    用于控制和监控跟单交易机器人的 Telegram Bot
    """

    def __init__(
        self,
        bot_token: str,
        allowed_chat_id: str
    ):
        """初始化 Telegram 机器人

        Args:
            bot_token: 从 BotFather 获取的 Telegram 机器人令牌
            allowed_chat_id: 仅允许此聊天ID控制机器人
        """
        self.bot_token = bot_token
        self.allowed_chat_id = str(allowed_chat_id)
        self.app: Optional[Application] = None

        # 主应用可设置的回调函数
        self.on_stop_requested: Optional[Callable] = None
        self.on_pause_requested: Optional[Callable] = None
        self.on_resume_requested: Optional[Callable] = None
        self.get_status_callback: Optional[Callable] = None
        self.get_positions_callback: Optional[Callable] = None
        self.get_orders_callback: Optional[Callable] = None
        self.get_pnl_callback: Optional[Callable] = None

        logger.info(f"Telegram 机器人已初始化，聊天ID: {allowed_chat_id}")

    def _check_authorized(self, update: Update) -> bool:
        """检查用户是否已授权"""
        user_chat_id = str(update.effective_chat.id)
        if user_chat_id != self.allowed_chat_id:
            logger.warning(f"未授权的访问尝试，来自聊天ID: {user_chat_id}")
            return False
        return True

    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /start 命令"""
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ 未授权")
            return

        message = """
🤖 <b>Hyperliquid 跟单交易机器人</b>

<b>可用命令：</b>

/status - 当前机器人状态
/positions - 查看持仓
/orders - 查看挂单
/pnl - 账户盈亏摘要
/pause - 暂停跟单（保留持仓）
/resume - 恢复跟单
/stop - 停止机器人并平仓

<b>状态：</b> 🟢 运行中
        """
        await update.message.reply_text(message.strip(), parse_mode="HTML")

    async def _status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /status 命令"""
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ 未授权")
            return

        if self.get_status_callback:
            try:
                status = await self.get_status_callback()
                await update.message.reply_text(status, parse_mode="HTML")
            except Exception as e:
                logger.error(f"获取状态出错: {e}")
                await update.message.reply_text(f"❌ 错误: {e}")
        else:
            await update.message.reply_text("状态回调未配置")

    async def _positions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /positions 命令"""
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ 未授权")
            return

        if self.get_positions_callback:
            try:
                positions = await self.get_positions_callback()
                await update.message.reply_text(positions, parse_mode="HTML")
            except Exception as e:
                logger.error(f"获取持仓出错: {e}")
                await update.message.reply_text(f"❌ 错误: {e}")
        else:
            await update.message.reply_text("📍 持仓回调未配置")

    async def _orders_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /orders 命令"""
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ 未授权")
            return

        if self.get_orders_callback:
            try:
                orders = await self.get_orders_callback()

                if not orders:
                    await update.message.reply_text("📋 暂无挂单")
                    return

                message = "<b>挂单列表</b>\n\n"
                for i, order in enumerate(orders, 1):
                    side = order.get('side', 'BUY').upper()
                    order_type = order.get('order_type', 'LIMIT').upper()

                    message += f"<b>{i}. {order['symbol']} {side}</b>\n"
                    message += f"   类型: {order_type}\n"
                    message += f"   数量: {abs(order['size']):.4f}\n"
                    message += f"   价格: ${order['price']:,.2f}\n"

                    if 'trigger_price' in order and order['trigger_price']:
                        message += f"   触发价: ${order['trigger_price']:,.2f}\n"

                    message += "\n"

                await update.message.reply_text(message.strip(), parse_mode="HTML")
            except Exception as e:
                logger.error(f"获取挂单出错: {e}")
                await update.message.reply_text(f"❌ 错误: {e}")
        else:
            await update.message.reply_text("📋 挂单回调未配置")

    async def _pause_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /pause 命令"""
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ 未授权")
            return

        if self.on_pause_requested:
            try:
                await self.on_pause_requested()
                await update.message.reply_text(
                    "⏸️ <b>机器人已暂停</b>\n\n不会跟单新的交易。\n现有持仓保持不变。",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"暂停出错: {e}")
                await update.message.reply_text(f"❌ 错误: {e}")
        else:
            await update.message.reply_text("暂停回调未配置")

    async def _resume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /resume 命令"""
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ 未授权")
            return

        if self.on_resume_requested:
            try:
                await self.on_resume_requested()
                await update.message.reply_text(
                    "▶️ <b>机器人已恢复</b>\n\n跟单交易已激活！",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"恢复出错: {e}")
                await update.message.reply_text(f"❌ 错误: {e}")
        else:
            await update.message.reply_text("恢复回调未配置")

    async def _stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /stop 命令 - 显示确认界面"""
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ 未授权")
            return

        keyboard = [
            [
                InlineKeyboardButton("平掉持仓", callback_data="stop_close"),
                InlineKeyboardButton("保留持仓", callback_data="stop_keep")
            ],
            [InlineKeyboardButton("❌ 取消", callback_data="stop_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "⚠️ <b>停止跟单交易</b>\n\n"
            "此操作将：\n"
            "✅ 停止跟单新交易\n"
            "✅ 撤销所有挂单\n\n"
            "是否同时平掉所有持仓？",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )

    async def _button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理按钮回调"""
        query = update.callback_query
        await query.answer()

        if not self._check_authorized(update):
            await query.edit_message_text("⛔ 未授权")
            return

        if query.data == "stop_close":
            await query.edit_message_text(
                "🛑 <b>正在停止机器人...</b>\n\n"
                "• 撤销所有挂单\n"
                "• 平掉所有持仓\n"
                "• 关闭机器人\n\n"
                "请稍候...",
                parse_mode="HTML"
            )
            if self.on_stop_requested:
                try:
                    await self.on_stop_requested(close_positions=True)
                    await query.edit_message_text(
                        "✅ <b>机器人已停止</b>\n\n"
                        "所有挂单已撤销。\n"
                        "所有持仓已平掉。\n"
                        "状态: 🔴 已停止",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    await query.edit_message_text(f"❌ 错误: {e}")

        elif query.data == "stop_keep":
            await query.edit_message_text(
                "🛑 <b>正在停止机器人...</b>\n\n"
                "• 撤销所有挂单\n"
                "• 保留现有持仓\n"
                "• 关闭机器人\n\n"
                "请稍候...",
                parse_mode="HTML"
            )
            if self.on_stop_requested:
                try:
                    await self.on_stop_requested(close_positions=False)
                    await query.edit_message_text(
                        "✅ <b>机器人已停止</b>\n\n"
                        "所有挂单已撤销。\n"
                        "持仓已保留。\n"
                        "状态: 🔴 已停止",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    await query.edit_message_text(f"❌ 错误: {e}")

        elif query.data == "stop_cancel":
            await query.edit_message_text(
                "✅ 已取消停止操作。机器人仍在运行。",
                parse_mode="HTML"
            )

    async def _pnl_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /pnl 命令"""
        if not self._check_authorized(update):
            await update.message.reply_text("⛔ 未授权")
            return

        # TODO: 从数据库获取实际盈亏数据
        message = """
💰 <b>账户盈亏摘要</b>

<b>本次会话：</b>
• 总交易数: 0
• 盈利笔数: 0
• 亏损笔数: 0
• 胜率: 0%

<b>盈亏：</b>
• 今日: $0.00 (0%)
• 本周: $0.00 (0%)
• 累计: $0.00 (0%)

🕐 <i>更新时间: {}</i>
        """.format(datetime.now().strftime('%H:%M:%S UTC'))

        await update.message.reply_text(message.strip(), parse_mode="HTML")

    async def start(self):
        """启动 Telegram 机器人"""
        logger.info("正在启动 Telegram 机器人...")

        # 创建应用
        self.app = Application.builder().token(self.bot_token).build()

        # 添加命令处理器
        self.app.add_handler(CommandHandler("start", self._start_command))
        self.app.add_handler(CommandHandler("status", self._status_command))
        self.app.add_handler(CommandHandler("positions", self._positions_command))
        self.app.add_handler(CommandHandler("orders", self._orders_command))
        self.app.add_handler(CommandHandler("pause", self._pause_command))
        self.app.add_handler(CommandHandler("resume", self._resume_command))
        self.app.add_handler(CommandHandler("stop", self._stop_command))
        self.app.add_handler(CommandHandler("pnl", self._pnl_command))

        # 添加按钮回调处理器
        self.app.add_handler(CallbackQueryHandler(self._button_callback))

        # 开始轮询
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()

        logger.info("✅ Telegram 机器人已启动并开始轮询")

    async def stop(self):
        """停止 Telegram 机器人"""
        if self.app:
            logger.info("正在停止 Telegram 机器人...")
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            logger.info("Telegram 机器人已停止")
