import asyncio
from datetime import datetime
from loguru import logger
from config.settings import settings
from utils.logger import setup_logger
from hyperliquid.client import HyperliquidClient
from hyperliquid.websocket import HyperliquidWebSocket
from hyperliquid.models import WebSocketUpdate, PositionSide, OrderSide
from copy_engine import WalletMonitor, TradeExecutor, PositionSizer
from telegram_bot import TelegramBot, NotificationService

# 配置日志
setup_logger(settings.log_file, settings.log_level)

# Hyperliquid 最小订单金额要求
MIN_POSITION_SIZE_USD = 10.0

# 初始化组件
monitor: WalletMonitor = None
executor: TradeExecutor = None
position_sizer: PositionSizer = None
client: HyperliquidClient = None
telegram_bot: TelegramBot = None
notifier: NotificationService = None

# 状态追踪
is_paused = False
trades_copied_count = 0
bot_start_time = None

# 模拟账户追踪
simulated_balance = 0.0
simulated_positions = {}  # symbol -> {'size': float, 'entry_price': float, 'side': str}
simulated_pnl = 0.0


def calculate_adjusted_leverage(target_leverage: float, adjustment_ratio: float, symbol: str) -> int:
    """
    计算调整后的杠杆倍数，带有正确的取整和最大杠杆限制。

    Hyperliquid 仅支持整数杠杆（1x, 2x, 3x 等）。
    每个资产有不同的最大杠杆限制。

    Args:
        target_leverage: 目标钱包的杠杆倍数
        adjustment_ratio: 调整比率（如 0.5 = 使用目标杠杆的50%）
        symbol: 交易对（用于查询最大杠杆）

    Returns:
        介于1和该资产最大杠杆之间的整数杠杆值
    """
    # Hyperliquid 各资产最大杠杆限制
    MAX_LEVERAGE_LIMITS = {
        'BTC': 50,
        'ETH': 50,
        'SOL': 20,
        'MATIC': 20,
        'ARB': 20,
        'OP': 20,
        'AVAX': 20,
        'DOGE': 20,
        'ATOM': 10,
        'LTC': 10,
        'BCH': 10,
        'LINK': 10,
        'UNI': 10,
        'APE': 10,
        'APT': 10,
        'SUI': 10,
        'TIA': 10,
        'SEI': 10,
        'WLD': 10,
        'NEAR': 10,
        'FET': 10,
        'INJ': 10,
        'STX': 10,
        'PEPE': 10,
        'BONK': 10,
        'WIF': 10,
        'HYPE': 10,
        'ZEC': 10,
        'TRUMP': 10,
        'MELANIA': 10,
        'PUMP': 10,
    }

    # 获取该资产的最大杠杆（未知资产默认10x）
    max_leverage = MAX_LEVERAGE_LIMITS.get(symbol.upper(), 10)

    # 计算期望杠杆
    desired_leverage = target_leverage * adjustment_ratio

    # 四舍五入到最近的整数
    rounded_leverage = round(desired_leverage)

    # 确保最低1x
    rounded_leverage = max(1, rounded_leverage)

    # 限制在该资产的最大杠杆
    final_leverage = min(rounded_leverage, max_leverage)

    return final_leverage


async def on_new_position(position_data: dict):
    """
    当目标钱包新开仓时调用
    这里是跟单交易的核心逻辑！
    """
    global trades_copied_count, is_paused, simulated_balance, simulated_positions, simulated_pnl

    # 检查是否暂停
    if is_paused:
        logger.warning("⏸️ 机器人已暂停 - 跳过交易")
        return

    # 检查最大持仓数限制
    if settings.copy_rules.max_open_trades is not None:
        current_trades = len(monitor.current_state.positions) if monitor.current_state else 0
        if current_trades >= settings.copy_rules.max_open_trades:
            logger.warning(f"⚠️ 已达最大持仓数限制 ({current_trades}/{settings.copy_rules.max_open_trades}) - 跳过交易")
            return

    # 检查账户权益限制
    if settings.copy_rules.max_account_equity is not None:
        current_equity = monitor.current_state.total_equity if monitor.current_state else 0
        if current_equity >= settings.copy_rules.max_account_equity:
            logger.warning(f"⚠️ 已达最大账户权益 (${current_equity:,.2f}/${settings.copy_rules.max_account_equity:,.2f}) - 停止跟单")
            is_paused = True
            if notifier:
                await notifier.send_error_notification(f"已达最大账户权益: ${current_equity:,.2f}。机器人自动暂停。")
            return

    try:
        logger.success("=" * 60)
        logger.success("🎯 检测到新持仓 - 正在跟单！")
        logger.success("=" * 60)

        # 解析持仓数据
        symbol = position_data.get("coin", "")
        size = float(position_data.get("szi", 0))
        side = PositionSide.LONG if size > 0 else PositionSide.SHORT

        position_info = position_data.get("position", {})
        entry_price = float(position_info.get("entryPx", 0))
        target_leverage = float(position_info.get("leverage", {}).get("value", 1))

        logger.info(f"📊 目标持仓:")
        logger.info(f"   交易对: {symbol}")
        logger.info(f"   方向: {side.value.upper()}")
        logger.info(f"   数量: {abs(size)}")
        logger.info(f"   开仓价: ${entry_price:,.2f}")
        logger.info(f"   杠杆: {target_leverage}x")

        # 获取当前市场价格
        async with client:
            current_price = await client.get_market_price(symbol)
            if not current_price:
                current_price = entry_price

        logger.info(f"   当前价格: ${current_price:,.2f}")

        # 检查是否应该跟单（入场质量检查）
        should_copy = position_sizer.should_copy_position(
            entry_price,
            current_price,
            settings.copy_rules.min_entry_quality_pct
        )

        if not should_copy:
            logger.warning("⚠️ 跳过 - 入场质量检查未通过")
            return

        # 获取目标钱包余额
        target_state = monitor.current_state
        target_balance = target_state.balance if target_state else 100000  # 未知时使用默认值

        # 计算你的仓位大小
        your_balance = 1000  # TODO: 从你的账户获取实际余额
        your_exposure = 0  # TODO: 计算当前敞口

        # 简化计算
        if settings.sizing.mode == "proportional":
            your_size = abs(size) * settings.sizing.portfolio_ratio
        else:
            your_size = settings.sizing.fixed_size / entry_price if entry_price > 0 else 0

        # 计算调整后的杠杆
        your_leverage = position_sizer.calculate_leverage(
            target_leverage,
            settings.leverage.adjustment_ratio,
            settings.leverage.max_leverage,
            settings.leverage.min_leverage
        )

        # 检查最小仓位金额（Hyperliquid 要求）
        your_position_value = your_size * entry_price
        if your_position_value < MIN_POSITION_SIZE_USD:
            logger.warning(f"\n⚠️  跳过持仓: {symbol}")
            logger.warning(f"   仓位价值 ${your_position_value:.2f} 低于 Hyperliquid 最低要求 ${MIN_POSITION_SIZE_USD:.2f}")
            logger.success("=" * 60)
            return

        logger.info(f"\n你的持仓:")
        logger.info(f"   数量: {your_size:.4f} {symbol}")
        logger.info(f"   名义价值: ${your_size * entry_price:,.2f}")
        logger.info(f"   杠杆: {your_leverage}x")
        logger.info(f"   开仓价: ${entry_price:,.2f}")

        # 执行交易
        logger.info(f"\n正在执行交易...")
        result = await executor.execute_market_order(
            symbol=symbol,
            side=side,
            size=your_size,
            leverage=your_leverage
        )

        if result:
            logger.success(f"✅ 交易执行成功！")
            logger.success(f"   结果: {result}")
            trades_copied_count += 1

            # 发送 Telegram 通知
            if notifier:
                await notifier.send_trade_notification(
                    symbol=symbol,
                    side=side.value,
                    size=your_size,
                    entry_price=entry_price,
                    leverage=your_leverage,
                    target_size=abs(size),
                    is_simulated=executor.dry_run
                )
        else:
            logger.error("❌ 交易执行失败")
            if notifier:
                await notifier.send_error_notification(f"执行 {symbol} 交易失败")

        logger.success("=" * 60)

    except Exception as e:
        logger.error(f"跟单持仓出错: {e}")
        if notifier:
            await notifier.send_error_notification(f"跟单持仓出错: {str(e)}")


async def on_position_close(position_data: dict):
    """当目标钱包平仓时调用"""
    global simulated_balance, simulated_positions, simulated_pnl

    symbol = position_data.get("coin", "")
    logger.info(f"🔴 目标已平仓: {symbol}")

    # 平掉模拟持仓并计算盈亏
    if settings.simulated_trading and symbol in simulated_positions:
        pos = simulated_positions[symbol]
        # 从监控器获取当前价格
        current_price = 0
        if monitor.current_state:
            for p in monitor.current_state.positions:
                if p.symbol == symbol:
                    current_price = p.current_price
                    break

        if current_price > 0:
            # 计算盈亏
            if pos['side'] == 'LONG':
                pnl = pos['size'] * (current_price - pos['entry_price'])
            else:
                pnl = abs(pos['size']) * (pos['entry_price'] - current_price)

            # 返还保证金到余额
            margin_used = pos['value'] / pos['leverage']
            simulated_balance += margin_used + pnl
            simulated_pnl += pnl

            logger.success(f"\n💰 模拟持仓已平！")
            logger.success(f"   开仓价: ${pos['entry_price']:,.2f}")
            logger.success(f"   平仓价: ${current_price:,.2f}")
            logger.success(f"   盈亏: ${pnl:,.2f} ({(pnl/pos['value']*100):+.2f}%)")
            logger.success(f"   新余额: ${simulated_balance:,.2f}")
            logger.success(f"   累计盈亏: ${simulated_pnl:,.2f}")

            del simulated_positions[symbol]

    # 平掉你对应的持仓
    logger.info("   -> 正在平掉你的持仓...")
    await executor.close_position(symbol)


async def on_position_update(position_data: dict):
    """当目标钱包更新持仓时调用"""
    symbol = position_data.get("coin", "")
    size = float(position_data.get("szi", 0))
    logger.info(f"📊 目标更新了持仓: {symbol} (新数量: {size})")

    # TODO: 更新你的持仓以匹配


async def on_new_order(order_data: dict):
    """
    当目标钱包挂新订单时调用
    跟单限价单和止损单
    """
    global trades_copied_count, is_paused, simulated_balance

    # 检查是否暂停
    if is_paused:
        logger.warning("⏸️ 机器人已暂停 - 跳过订单跟单")
        return

    # 检查是否应该跟单订单
    if not settings.copy_rules.copy_existing_orders:
        return

    # 检查最大挂单数限制
    if settings.copy_rules.max_open_orders is not None:
        current_orders = len(monitor.current_state.orders) if monitor.current_state else 0
        if current_orders >= settings.copy_rules.max_open_orders:
            logger.warning(f"⚠️ 已达最大挂单数限制 ({current_orders}/{settings.copy_rules.max_open_orders}) - 跳过订单")
            return

    try:
        symbol = order_data.get('coin', '')
        side = order_data.get('side', '')
        order_type = order_data.get('orderType', 'limit')
        target_size = abs(float(order_data.get('sz', 0)))
        price = float(order_data.get('limitPx', 0))

        logger.info(f"\n{'='*50}")
        logger.info(f"📋 检测到新订单！")
        logger.info(f"{'='*50}")
        logger.info(f"交易对: {symbol}")
        logger.info(f"方向: {side}")
        logger.info(f"类型: {order_type}")
        logger.info(f"目标数量: {target_size}")
        logger.info(f"价格: ${price:,.2f}")

        # 计算我们的订单数量
        if settings.copy_rules.auto_adjust_size:
            our_size = position_sizer.calculate_size(
                target_size=target_size,
                symbol=symbol,
                current_exposure=monitor.current_state.total_equity if monitor.current_state else 0
            )
        else:
            our_size = target_size

        logger.info(f"\n📊 订单仓位计算:")
        logger.info(f"   我们的数量: {our_size:.4f}")

        # 执行订单
        result = await executor.execute_limit_order(
            symbol=symbol,
            side=side,
            size=our_size,
            price=price
        )

        if result:
            logger.success(f"✅ 订单跟单成功！")
            trades_copied_count += 1

            # 记录模拟订单
            if settings.simulated_trading:
                order_value = our_size * price
                logger.success(f"\n📋 模拟订单已挂出！")
                logger.success(f"   订单价值: ${order_value:,.2f}")
                logger.success(f"   账户余额: ${simulated_balance:,.2f}")

            # 发送通知
            if notifier:
                await notifier.send_trade_notification(
                    symbol=symbol,
                    side=side,
                    size=our_size,
                    price=price,
                    leverage=1.0,  # 订单在成交前没有杠杆
                    target_size=target_size
                )
        else:
            logger.error(f"❌ 订单跟单失败")

    except Exception as e:
        logger.error(f"跟单订单出错: {e}")


async def on_order_fill(fill_data: dict):
    """
    当订单成交时调用
    跟单已成交的订单
    """
    global trades_copied_count, is_paused, simulated_balance, simulated_positions, simulated_pnl

    # 检查是否暂停
    if is_paused:
        logger.warning("⏸️ 机器人已暂停 - 跳过成交跟单")
        return

    try:
        symbol = fill_data.get('coin', '')
        side_str = fill_data.get('side', '')  # 'B' 买入, 'S' 卖出
        target_size = abs(float(fill_data.get('sz', 0)))
        price = float(fill_data.get('px', 0))
        direction = fill_data.get('dir', '')  # 如 "Open Long", "Close Short"
        crossed = fill_data.get('crossed', False)  # True 为 Maker，False 为 Taker

        # 判断是市价单还是限价单
        # crossed=False 通常是市价单（Taker）
        # crossed=True 通常是限价单成交（Maker）
        order_type = "LIMIT" if crossed else "MARKET"

        # 转换方向为 PositionSide
        if "Long" in direction:
            position_side = PositionSide.LONG
        elif "Short" in direction:
            position_side = PositionSide.SHORT
        else:
            # 备用方案：使用方向指示符
            position_side = PositionSide.LONG if side_str == "B" else PositionSide.SHORT

        logger.info(f"\n{'='*50}")
        logger.info(f"📋 检测到成交！")
        logger.info(f"{'='*50}")
        logger.info(f"交易对: {symbol}")
        logger.info(f"方向: {position_side.value.upper()}")
        logger.info(f"操作: {direction}")
        logger.info(f"目标订单类型: {order_type}")
        logger.info(f"目标数量: {target_size}")
        logger.info(f"价格: ${price:,.4f}")

        # 检查这是开仓/加仓还是平仓/减仓
        is_closing_reducing = "Close" in direction or "Reduce" in direction

        if is_closing_reducing:
            logger.warning(f"⚠️ 目标正在平仓/减仓 - 不跟单")
            logger.warning(f"   原因: 你可能没有该持仓可以平")
            logger.warning(f"   操作: {direction}")
            return

        # 判断是否为开仓事件
        is_position_flip = ">" in direction  # 如 "Short > Long" 或 "Long > Short"
        is_opening = "Open" in direction or "Add" in direction
        is_closing_only = "Close" in direction and not is_position_flip

        logger.info(f"📌 方向分析: '{direction}'")
        logger.info(f"   - 方向翻转: {is_position_flip}")
        logger.info(f"   - 开仓/加仓: {is_opening}")
        logger.info(f"   - 仅平仓: {is_closing_only}")

        # 获取目标持仓以计算我们的仓位
        target_position = None
        if monitor.current_state:
            logger.debug(f"📊 当前缓存持仓数: {len(monitor.current_state.positions)}")
            for pos in monitor.current_state.positions:
                logger.debug(f"   - {pos.symbol}: 数量={pos.size}")
                if pos.symbol == symbol:
                    target_position = pos
                    break

        # 如果没有找到持仓且这是仅平仓交易，跳过
        if not target_position and is_closing_only:
            logger.warning(f"⚠️ 在目标钱包中未找到 {symbol} 的持仓")
            logger.warning(f"   这是仅平仓交易 - 跳过")
            return

        # 如果没有找到持仓但这是翻转或开仓交易，延迟后重试
        if not target_position and (is_position_flip or is_opening):
            logger.warning(f"⚠️ 未找到 {symbol} 的持仓 - 可能是时序问题")
            logger.info(f"⏱️  等待1.5秒后重试查询...")

            # 等待交易所更新
            await asyncio.sleep(1.5)

            # 刷新状态
            await monitor.get_current_state()

            # 重试查找持仓
            if monitor.current_state:
                for pos in monitor.current_state.positions:
                    if pos.symbol == symbol:
                        target_position = pos
                        logger.success(f"✅ 重试后找到持仓: {symbol}")
                        break

            if not target_position:
                logger.error(f"❌ 重试后仍未找到 {symbol} 的持仓")
                logger.error(f"   操作: {direction}")
                logger.error(f"   可能是交易所延迟或持仓已被立即平掉")
                return

        # 计算我们的成交数量
        our_size = position_sizer.calculate_size(
            target_position=target_position,
            target_wallet_balance=monitor.current_state.balance if monitor.current_state else 1000000,
            your_wallet_balance=simulated_balance if settings.simulated_trading else (monitor.current_state.balance if monitor.current_state else 10000)
        )

        if not our_size:
            logger.warning(f"⚠️ 跳过成交 - 仓位计算返回 None")
            return

        # 检查最小仓位金额（Hyperliquid 要求）
        our_position_value = our_size * price
        if our_position_value < MIN_POSITION_SIZE_USD:
            logger.warning(f"\n⚠️  跳过成交: {symbol}")
            logger.warning(f"   仓位价值 ${our_position_value:.2f} 低于 Hyperliquid 最低要求 ${MIN_POSITION_SIZE_USD:.2f}")
            return

        logger.info(f"\n📊 成交仓位计算:")
        logger.info(f"   目标数量: {target_size}")
        logger.info(f"   我们的数量: {our_size:.4f}")

        # 获取目标杠杆
        target_leverage = target_position.leverage if target_position else 1.0

        # 调整杠杆，带有正确的取整和最大限制
        our_leverage = calculate_adjusted_leverage(
            target_leverage=target_leverage,
            adjustment_ratio=settings.leverage.adjustment_ratio,
            symbol=symbol
        )

        logger.info(f"   目标杠杆: {target_leverage}x")
        logger.info(f"   我们的杠杆: {our_leverage}x")

        # 根据设置决定订单类型
        use_limit = settings.copy_rules.use_limit_orders

        if use_limit:
            logger.info(f"   订单类型: 限价单 @ ${price:,.4f}")
        else:
            logger.info(f"   订单类型: 市价单")

        # 执行订单
        if use_limit:
            # 以成交价格挂限价单
            result = await executor.execute_limit_order(
                symbol=symbol,
                side=position_side,
                size=our_size,
                price=price,
                leverage=our_leverage
            )
        else:
            # 下市价单（原始行为）
            result = await executor.execute_market_order(
                symbol=symbol,
                side=position_side,
                size=our_size,
                leverage=our_leverage
            )

        if result:
            logger.success(f"✅ 成交跟单成功！")
            trades_copied_count += 1

            # 更新模拟持仓
            if settings.simulated_trading:
                position_value = our_size * price
                margin_required = position_value / our_leverage

                if symbol not in simulated_positions:
                    simulated_positions[symbol] = {
                        'size': 0,
                        'entry_price': 0,
                        'leverage': our_leverage,
                        'side': position_side.value
                    }

                pos = simulated_positions[symbol]

                # 根据操作方向更新持仓
                if "Open" in direction:
                    # 新开仓或加仓
                    total_value = (abs(pos['size']) * pos['entry_price']) + position_value
                    new_size = abs(pos['size']) + our_size
                    pos['entry_price'] = total_value / new_size if new_size > 0 else price
                    pos['size'] = new_size if position_side == PositionSide.LONG else -new_size
                    pos['side'] = position_side.value
                elif "Close" in direction:
                    # 平仓
                    pos['size'] = abs(pos['size']) - our_size
                    if position_side == PositionSide.SHORT:
                        pos['size'] = -pos['size']
                    if abs(pos['size']) < 0.0001:  # 约等于零
                        del simulated_positions[symbol]
                        logger.info(f"   持仓 {symbol} 已平")

                logger.success(f"\n💰 模拟成交已执行！")
                logger.success(f"   持仓: {symbol}")
                if symbol in simulated_positions:
                    logger.success(f"   新数量: {simulated_positions[symbol]['size']:.4f}")
                    logger.success(f"   开仓价: ${simulated_positions[symbol]['entry_price']:.2f}")
                logger.success(f"   保证金: ${margin_required:,.2f}")
                logger.success(f"   账户余额: ${simulated_balance:,.2f}")

            # 发送通知
            if notifier:
                await notifier.send_trade_notification(
                    symbol=symbol,
                    side=position_side,
                    size=our_size,
                    entry_price=price,
                    leverage=our_leverage,
                    target_size=target_size
                )
        else:
            logger.error(f"❌ 成交跟单失败")

    except Exception as e:
        logger.error(f"跟单成交出错: {e}")
        import traceback
        logger.error(traceback.format_exc())


# Telegram 机器人回调函数
async def get_status() -> str:
    """获取当前机器人状态（供 Telegram 使用）"""
    uptime = (datetime.now() - bot_start_time).total_seconds() / 3600 if bot_start_time else 0

    state = monitor.current_state if monitor else None

    if settings.simulated_trading:
        balance = simulated_balance
        pnl = simulated_pnl
    else:
        balance = state.balance if state else 0
        pnl = state.unrealized_pnl if state else 0

    status_emoji = "🟢" if not is_paused else "⏸️"
    status_text = "运行中" if not is_paused else "已暂停"
    mode = "模拟" if settings.simulated_trading else "实盘"

    return f"""
📊 <b>跟单交易状态</b>

{status_emoji} <b>状态：</b> {status_text}
🎮 <b>模式：</b> {mode}
👤 <b>目标：</b> <code>{settings.target_wallet[:10]}...{settings.target_wallet[-6:]}</code>
💼 <b>你的余额：</b> ${balance:,.2f}
📈 <b>会话盈亏：</b> ${pnl:,.2f}
📊 <b>跟单笔数：</b> {trades_copied_count}
📍 <b>持仓数量：</b> {len(simulated_positions) if settings.simulated_trading else (len(state.positions) if state else 0)}
⏰ <b>运行时间：</b> {uptime:.1f}h

<b>仓位模式：</b> {settings.sizing.mode.title()}
<b>杠杆：</b> {settings.leverage.adjustment_ratio}x（相对目标）
    """.strip()


def get_positions() -> list:
    """获取当前持仓（供 Telegram 命令使用）"""
    if not monitor or not monitor.current_state:
        return []

    positions = []
    for pos in monitor.current_state.positions:
        positions.append({
            'symbol': pos.symbol,
            'size': pos.size,
            'entry_price': pos.entry_price,
            'current_price': pos.current_price,
            'unrealized_pnl': pos.unrealized_pnl,
            'leverage': pos.leverage
        })

    return positions


def get_orders() -> list:
    """获取当前挂单（供 Telegram 命令使用）"""
    if not monitor or not monitor.current_state:
        return []

    orders = []
    for order in monitor.current_state.orders:
        orders.append({
            'symbol': order.symbol,
            'side': order.side,
            'size': order.size,
            'price': order.price,
            'order_type': order.order_type,
            'trigger_price': getattr(order, 'trigger_price', None)
        })

    return orders


async def get_pnl() -> str:
    """获取盈亏信息（供 Telegram 使用）"""
    state = monitor.current_state if monitor else None

    if settings.simulated_trading:
        balance = simulated_balance
        equity = simulated_balance
        pnl = simulated_pnl
        mode = "模拟"
    else:
        balance = state.balance if state else 0
        equity = state.total_equity if state else 0
        pnl = state.unrealized_pnl if state else 0
        mode = "实盘"

    return f"""
💰 <b>账户盈亏摘要</b>

🎮 <b>模式：</b> {mode}

<b>账户：</b>
• 余额: ${balance:,.2f}
• 权益: ${equity:,.2f}
• 未实现盈亏: ${pnl:,.2f}

<b>会话：</b>
• 跟单笔数: {trades_copied_count}
• 持仓数量: {len(simulated_positions) if settings.simulated_trading else (len(state.positions) if state else 0)}
    """.strip()


async def get_positions_formatted() -> str:
    """获取格式化的持仓信息（供 Telegram 使用）"""
    state = monitor.current_state if monitor else None

    if not state or not state.positions:
        return "📍 <b>持仓列表</b>\n\n暂无持仓。"

    message = f"📍 <b>持仓列表 ({len(state.positions)})</b>\n\n"

    for i, pos in enumerate(state.positions, 1):
        pnl_emoji = "📈" if pos.unrealized_pnl > 0 else "📉"
        message += f"""
{i}️⃣ <b>{pos.symbol}</b> {pos.side.value.upper()}
   数量: {pos.size:.4f}
   开仓价: ${pos.entry_price:,.2f}
   现价: ${pos.current_price:,.2f}
   杠杆: {pos.leverage}x
   盈亏: {pnl_emoji} ${pos.unrealized_pnl:,.2f} ({pos.pnl_percentage:+.2f}%)

"""

    return message.strip()


async def handle_pause():
    """处理 Telegram 暂停请求"""
    global is_paused
    is_paused = True
    logger.warning("⏸️ 机器人已通过 Telegram 命令暂停")


async def handle_resume():
    """处理 Telegram 恢复请求"""
    global is_paused
    is_paused = False
    logger.info("▶️ 机器人已通过 Telegram 命令恢复")


async def handle_stop(close_positions: bool = False):
    """处理 Telegram 停止请求"""
    logger.warning(f"🛑 收到 Telegram 停止请求 (平仓={close_positions})")

    # 撤销所有订单
    if executor:
        await executor.cancel_all_orders()

    # 如果要求则平掉持仓
    if close_positions and monitor and monitor.current_state:
        for pos in monitor.current_state.positions:
            logger.info(f"正在平仓: {pos.symbol}")
            await executor.close_position(pos.symbol)

    # 停止监控
    if monitor:
        await monitor.stop_monitoring()

    # 停止 Telegram 机器人
    if telegram_bot:
        await telegram_bot.stop()

    # 退出
    import sys
    sys.exit(0)


async def send_hourly_reports():
    """通过 Telegram 发送每小时报告"""
    while True:
        try:
            await asyncio.sleep(3600)  # 等待1小时

            if notifier and monitor and monitor.current_state:
                state = monitor.current_state

                await notifier.send_hourly_report(
                    trades_copied=trades_copied_count,
                    account_pnl_usd=state.unrealized_pnl,
                    account_pnl_pct=(state.unrealized_pnl / state.balance * 100) if state.balance > 0 else 0,
                    open_positions=len(state.positions),
                    open_orders=len(state.orders),
                    target_wallet=settings.target_wallet
                )
        except Exception as e:
            logger.error(f"发送每小时报告出错: {e}")

async def main():
    """
    跟单交易机器人主入口
    """
    global monitor, executor, position_sizer, client, telegram_bot, notifier, bot_start_time
    global simulated_balance, trades_copied_count

    bot_start_time = datetime.now()
    trades_copied_count = 0

    # 初始化模拟账户
    simulated_balance = settings.simulated_account_balance

    logger.info("=" * 60)
    logger.info("🚀 Hyperliquid 跟单交易机器人启动中...")
    logger.info("=" * 60)

    if settings.simulated_trading:
        logger.warning("🎮 模拟交易模式")
        logger.warning(f"💰 模拟账户余额: ${simulated_balance:,.2f}")
    else:
        # 实盘模式凭证校验
        if not settings.hyperliquid.wallet_address:
            logger.error("❌ 实盘模式必须配置 HYPERLIQUID_WALLET_ADDRESS")
            raise SystemExit(1)
        if not settings.hyperliquid.private_key:
            logger.error("❌ 实盘模式必须配置 HYPERLIQUID_PRIVATE_KEY")
            raise SystemExit(1)
        logger.warning("=" * 60)
        logger.warning("⚠️  实盘交易模式 - 真金白银！")
        logger.warning(f"💳 交易钱包: {settings.hyperliquid.wallet_address}")
        logger.warning("=" * 60)

    target_address = settings.target_wallet
    logger.info(f"📍 目标地址: {target_address}")

    # 初始化组件
    client = HyperliquidClient(settings.hyperliquid.api_url)

    monitor = WalletMonitor(
        target_address,
        settings.hyperliquid.api_url,
        settings.hyperliquid.ws_url
    )

    executor = TradeExecutor(
        wallet_address=settings.hyperliquid.wallet_address,
        private_key=settings.hyperliquid.private_key,
        info_url=settings.hyperliquid.api_url + "/info",
        exchange_url=settings.hyperliquid.api_url + "/exchange",
        dry_run=settings.simulated_trading
    )

    # 实盘模式下获取真实账户余额
    if not settings.simulated_trading:
        logger.info(f"\n💳 正在获取你的账户余额...")
        my_state = await client.get_user_state(settings.hyperliquid.wallet_address)
        if my_state and my_state.balance > 0:
            simulated_balance = my_state.balance
            logger.success(f"   真实账户余额: ${simulated_balance:,.2f}")
        else:
            logger.error("❌ 无法获取账户余额或余额为零，无法进行实盘交易")
            raise SystemExit(1)

    # 获取目标钱包状态以自动计算比率
    logger.info(f"\n📊 正在获取初始状态...")
    state = await monitor.get_current_state()

    if state:
        target_balance = state.balance
        logger.info(f"\n💼 目标账户:")
        logger.info(f"   余额: ${target_balance:,.2f}")
        logger.info(f"   权益: ${state.total_equity:,.2f}")
        logger.info(f"   未实现盈亏: ${state.unrealized_pnl:,.2f}")
        logger.info(f"   持仓数量: {len(state.positions)}")

        # 根据余额自动计算比率
        auto_ratio = simulated_balance / target_balance
        settings.sizing.portfolio_ratio = auto_ratio

        logger.success(f"\n✨ 自动计算仓位比率:")
        logger.success(f"   目标余额: ${target_balance:,.2f}")
        logger.success(f"   你的余额: ${simulated_balance:,.2f}")
        logger.success(f"   📊 比率: 1:{int(1/auto_ratio)} ({auto_ratio*100:.4f}%)")
        logger.success(f"   含义: 目标每交易 ${int(1/auto_ratio)}，你跟单 $1")

        # 计算达到 $10 最小订单金额所需的最低余额
        if state.positions:
            # 找到目标最小的持仓价值
            smallest_target_value = min(abs(pos.size) * pos.entry_price for pos in state.positions)
            # 计算跟单 $10 所需的最低余额
            min_balance_needed = MIN_POSITION_SIZE_USD * (target_balance / smallest_target_value)

            logger.info(f"\n⚠️  最低余额检查:")
            logger.info(f"   Hyperliquid 最小订单金额: ${MIN_POSITION_SIZE_USD:.2f}")
            logger.info(f"   目标最小持仓: ${smallest_target_value:,.2f}")
            logger.info(f"   所需最低余额（当前比率）: ${min_balance_needed:,.2f}")

            if simulated_balance < min_balance_needed:
                positions_below_min = sum(1 for pos in state.positions
                                         if (abs(pos.size) * pos.entry_price * auto_ratio) < MIN_POSITION_SIZE_USD)
                logger.warning(f"   ⚠️  警告: 你的余额 ${simulated_balance:,.2f} 低于建议最低值！")
                logger.warning(f"   {positions_below_min}/{len(state.positions)} 个持仓将被跳过（低于 $10）")
                logger.warning(f"   建议增加余额至 ${min_balance_needed:,.2f} 以跟单所有持仓")
            else:
                logger.success(f"   ✅ 你的余额足够跟单所有持仓！")

        if state.positions:
            logger.info(f"\n📊 当前持仓:")
            logger.info(f"=" * 60)

            total_simulated_margin = 0
            for i, pos in enumerate(state.positions, 1):
                target_position_value = abs(pos.size) * pos.entry_price
                your_position_value = target_position_value * auto_ratio
                your_size = your_position_value / pos.entry_price if pos.entry_price > 0 else 0
                your_leverage = calculate_adjusted_leverage(
                    target_leverage=pos.leverage,
                    adjustment_ratio=settings.leverage.adjustment_ratio,
                    symbol=pos.symbol
                )
                margin_needed = your_position_value / your_leverage
                total_simulated_margin += margin_needed

                logger.info(f"\n   持仓 {i}: {pos.symbol} {pos.side.value.upper()}")
                logger.info(f"   目标: {pos.size:.4f} @ ${pos.entry_price:,.2f} ({pos.leverage}x)")
                logger.info(f"   目标价值: ${target_position_value:,.2f}")
                logger.success(f"   → 你的跟单: {your_size:.4f} @ ${pos.entry_price:,.2f} ({your_leverage}x)")
                logger.success(f"   → 你的价值: ${your_position_value:,.2f}")
                logger.success(f"   → 所需保证金: ${margin_needed:,.2f}")

            logger.info(f"\n" + "=" * 60)
            logger.warning(f"📊 如果跟单全部 {len(state.positions)} 个持仓:")
            logger.warning(f"   总保证金需求: ${total_simulated_margin:,.2f}")
            logger.warning(f"   你的余额: ${simulated_balance:,.2f}")
            logger.warning(f"   剩余: ${simulated_balance - total_simulated_margin:,.2f}")
            logger.info(f"=" * 60)

    logger.info(f"\n🔧 跟单交易设置:")
    logger.info(f"   仓位模式: {settings.sizing.mode}")
    logger.info(f"   杠杆调整: {settings.leverage.adjustment_ratio}x")
    logger.info(f"   最大仓位: ${settings.sizing.max_position_size:,.2f}")

    position_sizer = PositionSizer(
        mode=settings.sizing.mode,
        fixed_size=settings.sizing.fixed_size,
        portfolio_ratio=settings.sizing.portfolio_ratio,
        max_position_size=settings.sizing.max_position_size,
        max_total_exposure=settings.sizing.max_total_exposure
    )

    # 设置回调函数
    monitor.on_new_position = on_new_position
    monitor.on_position_close = on_position_close
    monitor.on_position_update = on_position_update
    monitor.on_new_order = on_new_order
    monitor.on_order_fill = on_order_fill

    # 如果开启，复制现有持仓
    if settings.copy_rules.copy_open_positions and state and state.positions:
        logger.info("=" * 60)
        logger.success("🔄 启动时复制现有持仓")
        logger.info("=" * 60)

        copied_count = 0
        for i, pos in enumerate(state.positions, 1):
            try:
                # 计算你的跟单仓位
                target_position_value = abs(pos.size) * pos.entry_price
                your_position_value = target_position_value * auto_ratio
                your_size = your_position_value / pos.entry_price if pos.entry_price > 0 else 0
                your_leverage = calculate_adjusted_leverage(
                    target_leverage=pos.leverage,
                    adjustment_ratio=settings.leverage.adjustment_ratio,
                    symbol=pos.symbol
                )
                margin_needed = your_position_value / your_leverage

                # 检查最小仓位金额
                if your_position_value < MIN_POSITION_SIZE_USD:
                    logger.warning(f"\n⚠️  跳过持仓 {i}/{len(state.positions)}: {pos.symbol}")
                    logger.warning(f"   仓位价值 ${your_position_value:.2f} 低于 Hyperliquid 最低要求 ${MIN_POSITION_SIZE_USD:.2f}")
                    continue

                logger.info(f"\n📊 复制持仓 {i}/{len(state.positions)}: {pos.symbol}")
                logger.info(f"   目标: {pos.size:.4f} @ ${pos.entry_price:,.2f} ({pos.leverage}x)")
                logger.info(f"   目标价值: ${target_position_value:,.2f}")
                logger.success(f"   → 你的数量: {your_size:.4f} @ ${pos.entry_price:,.2f} ({your_leverage}x)")
                logger.success(f"   → 你的价值: ${your_position_value:,.2f}")
                logger.success(f"   → 保证金: ${margin_needed:,.2f}")

                # 执行跟单
                side = PositionSide.LONG if pos.size > 0 else PositionSide.SHORT
                result = await executor.execute_market_order(
                    symbol=pos.symbol,
                    side=side,
                    size=your_size,
                    leverage=your_leverage
                )

                if result:
                    # 更新模拟账户
                    if settings.simulated_trading:
                        simulated_positions[pos.symbol] = {
                            'size': your_size if side == PositionSide.LONG else -your_size,
                            'entry_price': pos.entry_price,
                            'side': side.value.upper(),
                            'leverage': your_leverage,
                            'value': your_position_value,
                            'margin_used': margin_needed
                        }

                    copied_count += 1
                    logger.success(f"   ✅ 持仓复制成功！")
                else:
                    logger.error(f"   ❌ 持仓复制失败")

            except Exception as e:
                logger.error(f"   ❌ 复制持仓 {pos.symbol} 出错: {e}")

        # 显示最终账户状态
        if settings.simulated_trading:
            total_margin_used = sum(p['margin_used'] for p in simulated_positions.values())
            logger.info("\n" + "=" * 60)
            logger.success("✅ 现有持仓复制完成！")
            logger.info("=" * 60)
            logger.success(f"💰 模拟账户更新:")
            logger.success(f"   已复制持仓: {copied_count}/{len(state.positions)}")
            logger.success(f"   已用保证金: ${total_margin_used:,.2f}")
            logger.success(f"   账户余额: ${simulated_balance:,.2f}")
            logger.success(f"   可用余额: ${simulated_balance - total_margin_used:,.2f}")
            logger.info("=" * 60)

        # 更新全局计数器
        trades_copied_count += copied_count

    # 如果开启，复制现有订单
    if settings.copy_rules.copy_existing_orders and state and state.orders:
        logger.info("\n" + "=" * 60)
        logger.success("📋 启动时复制现有订单")
        logger.info("=" * 60)

        for i, order in enumerate(state.orders, 1):
            try:
                # 跳过无效价格的订单
                if order.price is None or order.price <= 0:
                    logger.warning(f"   ⚠️ 跳过订单 {order.symbol} - 价格无效")
                    continue

                # 计算你的订单数量
                target_order_value = order.size * order.price
                your_order_value = target_order_value * auto_ratio
                your_size = your_order_value / order.price
                your_leverage = 1.0  # 订单默认杠杆

                logger.info(f"\n📝 复制订单 {i}/{len(state.orders)}: {order.symbol}")
                logger.info(f"   目标: {order.size:.4f} @ ${order.price:,.2f}")
                logger.success(f"   → 你的数量: {your_size:.4f} @ ${order.price:,.2f}")

                # 将 OrderSide 转换为 PositionSide
                position_side = PositionSide.LONG if order.side == OrderSide.BUY else PositionSide.SHORT

                # 执行订单
                result = await executor.execute_limit_order(
                    symbol=order.symbol,
                    side=position_side,
                    size=your_size,
                    price=order.price,
                    leverage=your_leverage
                )

                if result:
                    logger.success(f"   ✅ 订单复制成功！")
                else:
                    logger.error(f"   ❌ 订单复制失败")

            except Exception as e:
                logger.error(f"   ❌ 复制订单 {order.symbol} 出错: {e}")

        logger.info("=" * 60)

    # 如果配置了 Telegram 机器人则初始化
    if settings.telegram.bot_token and settings.telegram.chat_id:
        logger.info("🤖 正在初始化 Telegram 机器人...")

        notifier = NotificationService(
            settings.telegram.bot_token,
            settings.telegram.chat_id
        )

        telegram_bot = TelegramBot(
            settings.telegram.bot_token,
            settings.telegram.chat_id
        )

        # 设置 Telegram 回调
        telegram_bot.get_status_callback = get_status
        telegram_bot.get_positions_callback = get_positions_formatted
        telegram_bot.get_orders_callback = get_orders
        telegram_bot.get_pnl_callback = get_pnl
        telegram_bot.on_pause_requested = handle_pause
        telegram_bot.on_resume_requested = handle_resume
        telegram_bot.on_stop_requested = handle_stop

        # 启动 Telegram 机器人
        await telegram_bot.start()

        # 启动每小时报告任务
        asyncio.create_task(send_hourly_reports())

        logger.info("✅ Telegram 机器人就绪！")
    else:
        logger.warning("⚠️ Telegram 机器人未配置（请在 .env 中添加 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID）")

    try:
        # 获取初始状态
        logger.info(f"\n📊 正在获取初始状态...")
        state = await monitor.get_current_state()

        if state:
            logger.info(f"\n💼 目标账户:")
            logger.info(f"   余额: ${state.balance:,.2f}")
            logger.info(f"   权益: ${state.total_equity:,.2f}")
            logger.info(f"   未实现盈亏: ${state.unrealized_pnl:,.2f}")
            logger.info(f"   持仓数量: {len(state.positions)}")

            if state.positions:
                logger.info(f"\n📊 当前持仓:")
                for i, pos in enumerate(state.positions, 1):
                    logger.info(f"   {i}. {pos.symbol} {pos.side.value.upper()}: {pos.size} @ ${pos.entry_price:,.2f} ({pos.leverage}x)")

        # 如果配置了则复制现有挂单
        if settings.copy_rules.copy_existing_orders and state and state.orders:
            logger.info(f"\n📋 正在复制 {len(state.orders)} 个现有订单...")
            for order in state.orders:
                try:
                    order_dict = {
                        'coin': order.symbol,
                        'side': order.side,
                        'orderType': order.order_type,
                        'sz': str(order.size),
                        'limitPx': str(order.price)
                    }
                    await on_new_order(order_dict)
                except Exception as e:
                    logger.error(f"复制现有订单失败: {e}")

        logger.info(f"\n🔌 正在启动监控...")
        logger.info("✅ 机器人已上线，正在监控交易！")
        logger.info(f"   复制持仓: {settings.copy_rules.copy_open_positions}")
        logger.info(f"   复制订单: {settings.copy_rules.copy_existing_orders}")
        logger.info(f"   自动调整仓位: {settings.copy_rules.auto_adjust_size}")
        logger.info(f"   最大持仓数: {'无限制' if settings.copy_rules.max_open_trades is None else settings.copy_rules.max_open_trades}")
        logger.info(f"   最大挂单数: {'无限制' if settings.copy_rules.max_open_orders is None else settings.copy_rules.max_open_orders}")
        logger.info(f"   最大账户权益: {'无限制' if settings.copy_rules.max_account_equity is None else f'${settings.copy_rules.max_account_equity:,.2f}'}")
        logger.info("按 Ctrl+C 停止\n")

        # 发送启动通知
        if notifier:
            await notifier.send_startup_notification(
                target_wallet=settings.target_wallet,
                sizing_mode=settings.sizing.mode,
                ratio=f"1:{int(1/settings.sizing.portfolio_ratio)}",
                leverage_adjustment=settings.leverage.adjustment_ratio
            )

        # 开始监控
        await monitor.start_monitoring()

    except KeyboardInterrupt:
        logger.info("\n⚠️ 收到停止信号...")
    except Exception as e:
        logger.error(f"❌ 错误: {e}")
        raise
    finally:
        logger.info("🛑 正在停止监控...")

        # 发送关闭通知
        if notifier:
            await notifier.send_shutdown_notification()

        # 停止组件
        if monitor:
            await monitor.stop_monitoring()

        if telegram_bot:
            await telegram_bot.stop()

        logger.info("👋 机器人已安全停止")

if __name__ == "__main__":
    asyncio.run(main())
