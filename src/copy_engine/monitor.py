import asyncio
from typing import Callable, Optional, List
from loguru import logger
from hyperliquid.client import HyperliquidClient
from hyperliquid.websocket import HyperliquidWebSocket
from hyperliquid.models import Position, Order, UserState, WebSocketUpdate


class WalletMonitor:
    """
    监控目标钱包的交易活动
    """

    def __init__(
        self,
        target_address: str,
        api_url: str = "https://api.hyperliquid.xyz",
        ws_url: str = "wss://api.hyperliquid.xyz/ws"
    ):
        self.target_address = target_address
        self.client = HyperliquidClient(api_url)
        self.ws = HyperliquidWebSocket(ws_url)

        # 当前状态追踪
        self.current_state: Optional[UserState] = None
        self.last_positions: List[Position] = []
        self.last_orders: List[Order] = []

        # 回调函数
        self.on_new_position: Optional[Callable] = None
        self.on_position_update: Optional[Callable] = None
        self.on_position_close: Optional[Callable] = None
        self.on_new_order: Optional[Callable] = None
        self.on_order_fill: Optional[Callable] = None
        self.on_order_cancel: Optional[Callable] = None

        logger.info(f"钱包监控器已初始化，目标地址: {target_address}")

    async def get_current_state(self) -> Optional[UserState]:
        """获取目标钱包的当前状态"""
        async with self.client:
            self.current_state = await self.client.get_user_state(self.target_address)

            if self.current_state:
                self.last_positions = self.current_state.positions.copy()
                self.last_orders = self.current_state.orders.copy()

            return self.current_state

    async def start_monitoring(self):
        """开始监控目标钱包"""
        logger.info(f"开始监控 {self.target_address}")

        # 获取初始状态
        await self.get_current_state()

        # 连接 WebSocket
        await self.ws.connect()

        # 订阅用户更新
        await self.ws.subscribe_user(self.target_address, self._handle_update)

        # 开始监听
        await self.ws.listen()

    async def stop_monitoring(self):
        """停止监控"""
        logger.info("正在停止钱包监控")
        await self.ws.stop()

    async def _handle_update(self, update: WebSocketUpdate):
        """处理来自目标钱包的 WebSocket 更新"""
        logger.info(f"🔔 收到 WebSocket 更新: {update.channel}")

        try:
            if "data" not in update.data:
                logger.warning(f"⚠️ 更新中没有 'data' 字段: {update.data}")
                return

            data = update.data["data"]
            logger.info(f"📦 更新数据键: {list(data.keys())}")

            # 处理成交（已完成的交易）
            if "fills" in data:
                logger.success(f"💥 检测到成交: {len(data['fills'])} 笔")
                await self._handle_fills(data["fills"])

            # 处理持仓更新
            if "positions" in data:
                logger.success(f"📊 持仓更新: {len(data['positions'])} 个持仓")
                await self._handle_positions(data["positions"])

            # 处理订单更新
            if "orders" in data:
                logger.success(f"📋 订单更新: {len(data['orders'])} 个订单")
                await self._handle_orders(data["orders"])

        except Exception as e:
            logger.error(f"处理更新出错: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def _handle_fills(self, fills: List[dict]):
        """处理成交记录"""
        # 处理成交前先刷新持仓状态，确保数据最新
        logger.debug("🔄 处理成交前刷新持仓状态...")
        await self.get_current_state()

        for fill in fills:
            # 从成交数据中提取交易对
            symbol = fill.get("coin", "").upper()

            # 检查资产是否被屏蔽
            from config.settings import settings
            if symbol in settings.copy_rules.blocked_assets:
                logger.warning(f"⛔ 已屏蔽资产 - 忽略 {symbol} 的成交（在屏蔽列表中）")
                continue

            logger.success(f"🎯 检测到成交: {fill}")

            if self.on_order_fill:
                try:
                    if asyncio.iscoroutinefunction(self.on_order_fill):
                        await self.on_order_fill(fill)
                    else:
                        self.on_order_fill(fill)
                except Exception as e:
                    logger.error(f"成交回调执行出错: {e}")

    async def _handle_positions(self, positions: List[dict]):
        """处理持仓更新"""
        logger.info(f"📍 收到持仓更新: {len(positions)} 个持仓")

        from config.settings import settings

        for pos_data in positions:
            # 解析持仓数据
            symbol = pos_data.get("coin", "").upper()
            size = float(pos_data.get("szi", 0))

            # 检查资产是否被屏蔽
            if symbol in settings.copy_rules.blocked_assets:
                logger.debug(f"⛔ 忽略已屏蔽资产的持仓更新: {symbol}")
                continue

            # 检查是否为新持仓
            existing = next((p for p in self.last_positions if p.symbol == symbol), None)

            if not existing and size != 0:
                # 新开仓！
                logger.success(f"🆕 检测到新持仓: {symbol}")

                if self.on_new_position:
                    try:
                        if asyncio.iscoroutinefunction(self.on_new_position):
                            await self.on_new_position(pos_data)
                        else:
                            self.on_new_position(pos_data)
                    except Exception as e:
                        logger.error(f"新持仓回调执行出错: {e}")

            elif existing and size == 0:
                # 持仓已平
                logger.info(f"❌ 持仓已平: {symbol}")

                if self.on_position_close:
                    try:
                        if asyncio.iscoroutinefunction(self.on_position_close):
                            await self.on_position_close(pos_data)
                        else:
                            self.on_position_close(pos_data)
                    except Exception as e:
                        logger.error(f"平仓回调执行出错: {e}")

            elif existing and abs(size) != abs(existing.size):
                # 持仓数量变化
                logger.info(f"📊 持仓已更新: {symbol} ({existing.size} -> {size})")

                if self.on_position_update:
                    try:
                        if asyncio.iscoroutinefunction(self.on_position_update):
                            await self.on_position_update(pos_data)
                        else:
                            self.on_position_update(pos_data)
                    except Exception as e:
                        logger.error(f"持仓更新回调执行出错: {e}")

        # 更新状态
        await self.get_current_state()

    async def _handle_orders(self, orders: List[dict]):
        """处理订单更新"""
        logger.info(f"📝 收到订单更新: {len(orders)} 个订单")

        for order_data in orders:
            order_id = str(order_data.get("oid", ""))
            symbol = order_data.get("coin", "")

            # 检查是否为新订单
            existing = next((o for o in self.last_orders if o.order_id == order_id), None)

            if not existing:
                logger.success(f"📋 新订单: {symbol} - ID: {order_id}")

                if self.on_new_order:
                    try:
                        if asyncio.iscoroutinefunction(self.on_new_order):
                            await self.on_new_order(order_data)
                        else:
                            self.on_new_order(order_data)
                    except Exception as e:
                        logger.error(f"新订单回调执行出错: {e}")

        # 更新状态
        await self.get_current_state()
