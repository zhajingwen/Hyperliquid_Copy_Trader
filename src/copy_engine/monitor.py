import asyncio
from typing import Callable, Optional, List
from loguru import logger
from hyperliquid.client import HyperliquidClient
from hyperliquid.websocket import HyperliquidWebSocket
from hyperliquid.models import Position, Order, UserState, WebSocketUpdate


class WalletMonitor:
    """
    监控多个目标钱包的交易活动
    """

    def __init__(
        self,
        target_addresses: list[str],
        api_url: str = "https://api.hyperliquid.xyz",
        ws_url: str = "wss://api.hyperliquid.xyz/ws"
    ):
        self.target_addresses = target_addresses
        self.client = HyperliquidClient(api_url)
        self.ws = HyperliquidWebSocket(ws_url)

        # 每个目标的状态追踪
        self.target_states: dict[str, Optional[UserState]] = {addr: None for addr in target_addresses}
        self.last_positions: dict[str, List[Position]] = {addr: [] for addr in target_addresses}
        self.last_orders: dict[str, List[Order]] = {addr: [] for addr in target_addresses}

        # 回调函数（签名: async def callback(target_address: str, data: dict)）
        self.on_position_update: Optional[Callable] = None
        self.on_position_close: Optional[Callable] = None
        self.on_new_order: Optional[Callable] = None
        self.on_order_fill: Optional[Callable] = None

        for addr in target_addresses:
            logger.info(f"钱包监控器已初始化，目标地址: {addr}")

    @property
    def current_state(self) -> Optional[UserState]:
        """向后兼容：返回第一个目标的状态"""
        if self.target_addresses:
            return self.target_states.get(self.target_addresses[0])
        return None

    async def get_current_state(self, address: Optional[str] = None) -> Optional[UserState]:
        """获取目标钱包的当前状态

        Args:
            address: 目标地址，为 None 时获取第一个目标的状态
        """
        if address is None:
            address = self.target_addresses[0] if self.target_addresses else None
        if not address:
            return None

        async with self.client:
            state = await self.client.get_user_state(address)

            if state:
                self.target_states[address] = state
                self.last_positions[address] = state.positions.copy()
                self.last_orders[address] = state.orders.copy()

            return state

    async def get_all_states(self) -> dict[str, Optional[UserState]]:
        """获取所有目标钱包的当前状态"""
        for addr in self.target_addresses:
            await self.get_current_state(addr)
        return self.target_states

    async def start_monitoring(self):
        """开始监控所有目标钱包"""
        for addr in self.target_addresses:
            logger.info(f"开始监控 {addr}")

        # 获取所有目标的初始状态
        await self.get_all_states()

        # 连接 WebSocket
        await self.ws.connect()

        # 为每个目标创建闭包 handler 并订阅
        for addr in self.target_addresses:
            handler = self._make_update_handler(addr)
            await self.ws.subscribe_user(addr, handler)

        # 开始监听
        await self.ws.listen()

    def _make_update_handler(self, address: str):
        """为指定目标地址创建绑定的更新处理器"""
        async def handler(update: WebSocketUpdate):
            await self._handle_update(address, update)
        return handler

    async def stop_monitoring(self):
        """停止监控"""
        logger.info("正在停止钱包监控")
        await self.ws.stop()

    async def _handle_update(self, address: str, update: WebSocketUpdate):
        """处理来自目标钱包的 WebSocket 更新"""
        short_addr = f"{address[:6]}...{address[-4:]}"
        logger.info(f"🔔 [{short_addr}] 收到 WebSocket 更新: {update.channel}")

        try:
            if "data" not in update.data:
                logger.warning(f"⚠️ [{short_addr}] 更新中没有 'data' 字段: {update.data}")
                return

            data = update.data["data"]
            logger.info(f"📦 [{short_addr}] 更新数据键: {list(data.keys())}")

            # 处理成交（已完成的交易）
            if "fills" in data:
                logger.success(f"💥 [{short_addr}] 检测到成交: {len(data['fills'])} 笔")
                await self._handle_fills(address, data["fills"])

            # 处理持仓更新
            if "positions" in data:
                logger.success(f"📊 [{short_addr}] 持仓更新: {len(data['positions'])} 个持仓")
                await self._handle_positions(address, data["positions"])

            # 处理订单更新
            if "orders" in data:
                logger.success(f"📋 [{short_addr}] 订单更新: {len(data['orders'])} 个订单")
                await self._handle_orders(address, data["orders"])

        except Exception as e:
            logger.error(f"[{short_addr}] 处理更新出错: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def _handle_fills(self, address: str, fills: List[dict]):
        """处理成交记录"""
        short_addr = f"{address[:6]}...{address[-4:]}"

        # 处理成交前先刷新持仓状态，确保数据最新
        logger.debug(f"🔄 [{short_addr}] 处理成交前刷新持仓状态...")
        await self.get_current_state(address)

        for fill in fills:
            # 从成交数据中提取交易对
            symbol = fill.get("coin", "").upper()

            # 检查资产是否被屏蔽
            from config.settings import settings
            if symbol in settings.copy_rules.blocked_assets:
                logger.warning(f"⛔ [{short_addr}] 已屏蔽资产 - 忽略 {symbol} 的成交（在屏蔽列表中）")
                continue

            logger.success(f"🎯 [{short_addr}] 检测到成交: {fill}")

            if self.on_order_fill:
                try:
                    if asyncio.iscoroutinefunction(self.on_order_fill):
                        await self.on_order_fill(address, fill)
                    else:
                        self.on_order_fill(address, fill)
                except Exception as e:
                    logger.error(f"[{short_addr}] 成交回调执行出错: {e}")

    async def _handle_positions(self, address: str, positions: List[dict]):
        """处理持仓更新"""
        short_addr = f"{address[:6]}...{address[-4:]}"
        logger.info(f"📍 [{short_addr}] 收到持仓更新: {len(positions)} 个持仓")

        from config.settings import settings

        last_pos = self.last_positions.get(address, [])

        for pos_data in positions:
            # 解析持仓数据
            symbol = pos_data.get("coin", "").upper()
            size = float(pos_data.get("szi", 0))

            # 检查资产是否被屏蔽
            if symbol in settings.copy_rules.blocked_assets:
                logger.debug(f"⛔ [{short_addr}] 忽略已屏蔽资产的持仓更新: {symbol}")
                continue

            # 检查是否为新持仓
            existing = next((p for p in last_pos if p.symbol == symbol), None)

            if not existing and size != 0:
                # 新开仓（由 on_order_fill 处理交易执行）
                logger.success(f"🆕 [{short_addr}] 检测到新持仓: {symbol}")

            elif existing and size == 0:
                # 持仓已平
                logger.info(f"❌ [{short_addr}] 持仓已平: {symbol}")

                if self.on_position_close:
                    try:
                        if asyncio.iscoroutinefunction(self.on_position_close):
                            await self.on_position_close(address, pos_data)
                        else:
                            self.on_position_close(address, pos_data)
                    except Exception as e:
                        logger.error(f"[{short_addr}] 平仓回调执行出错: {e}")

            elif existing and abs(size) != abs(existing.size):
                # 持仓数量变化
                logger.info(f"📊 [{short_addr}] 持仓已更新: {symbol} ({existing.size} -> {size})")

                if self.on_position_update:
                    try:
                        if asyncio.iscoroutinefunction(self.on_position_update):
                            await self.on_position_update(address, pos_data)
                        else:
                            self.on_position_update(address, pos_data)
                    except Exception as e:
                        logger.error(f"[{short_addr}] 持仓更新回调执行出错: {e}")

        # 更新状态
        await self.get_current_state(address)

    async def _handle_orders(self, address: str, orders: List[dict]):
        """处理订单更新"""
        short_addr = f"{address[:6]}...{address[-4:]}"
        logger.info(f"📝 [{short_addr}] 收到订单更新: {len(orders)} 个订单")

        last_ord = self.last_orders.get(address, [])

        for order_data in orders:
            order_id = str(order_data.get("oid", ""))
            symbol = order_data.get("coin", "")

            # 检查是否为新订单
            existing = next((o for o in last_ord if o.order_id == order_id), None)

            if not existing:
                logger.success(f"📋 [{short_addr}] 新订单: {symbol} - ID: {order_id}")

                if self.on_new_order:
                    try:
                        if asyncio.iscoroutinefunction(self.on_new_order):
                            await self.on_new_order(address, order_data)
                        else:
                            self.on_new_order(address, order_data)
                    except Exception as e:
                        logger.error(f"[{short_addr}] 新订单回调执行出错: {e}")

        # 更新状态
        await self.get_current_state(address)
