import asyncio
import json
import websockets
from typing import Optional, Callable, Dict, Any
from datetime import datetime
from loguru import logger
from .models import WebSocketUpdate

class HyperliquidWebSocket:
    """
    Hyperliquid 实时 WebSocket 客户端
    """

    def __init__(self, ws_url: str = "wss://api.hyperliquid.xyz/ws"):
        self.ws_url = ws_url
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.is_running = False
        self.reconnect_delay = 5
        self.subscriptions: Dict[str, Any] = {}
        self.callbacks: Dict[str, Callable] = {}

    async def connect(self):
        """建立 WebSocket 连接"""
        try:
            logger.info(f"正在连接 Hyperliquid WebSocket: {self.ws_url}")
            self.ws = await websockets.connect(self.ws_url)
            self.is_running = True
            logger.info("WebSocket 连接成功")

            # 重连后重新订阅频道
            for channel, sub_data in self.subscriptions.items():
                await self._send_subscription(sub_data)

        except Exception as e:
            logger.error(f"WebSocket 连接失败: {e}")
            raise

    async def disconnect(self):
        """关闭 WebSocket 连接"""
        self.is_running = False
        if self.ws:
            await self.ws.close()
            logger.info("WebSocket 已断开")

    async def _send_subscription(self, data: dict):
        """发送订阅消息"""
        if self.ws:
            try:
                await self.ws.send(json.dumps(data))
                logger.debug(f"已发送订阅: {data}")
            except Exception as e:
                logger.error(f"发送订阅失败: {e}")

    async def subscribe_user(self, address: str, callback: Optional[Callable] = None):
        """
        订阅用户更新（持仓、订单、成交）

        Args:
            address: 要监控的钱包地址
            callback: 收到更新时调用的回调函数
        """
        channel = f"user:{address}"

        subscription = {
            "method": "subscribe",
            "subscription": {
                "type": "userEvents",
                "user": address
            }
        }

        self.subscriptions[channel] = subscription
        if callback:
            self.callbacks[channel] = callback

        if self.ws:
            await self._send_subscription(subscription)

        logger.info(f"已订阅用户更新: {address}")

    async def subscribe_trades(self, symbol: str, callback: Optional[Callable] = None):
        """
        订阅指定交易对的成交更新

        Args:
            symbol: 交易对（如 "BTC"）
            callback: 收到成交时调用的回调函数
        """
        channel = f"trades:{symbol}"

        subscription = {
            "method": "subscribe",
            "subscription": {
                "type": "trades",
                "coin": symbol
            }
        }

        self.subscriptions[channel] = subscription
        if callback:
            self.callbacks[channel] = callback

        if self.ws:
            await self._send_subscription(subscription)

        logger.info(f"已订阅 {symbol} 成交数据")

    async def subscribe_all_mids(self, callback: Optional[Callable] = None):
        """
        订阅所有中间价格

        Args:
            callback: 收到价格更新时调用的回调函数
        """
        channel = "allMids"

        subscription = {
            "method": "subscribe",
            "subscription": {
                "type": "allMids"
            }
        }

        self.subscriptions[channel] = subscription
        if callback:
            self.callbacks[channel] = callback

        if self.ws:
            await self._send_subscription(subscription)

        logger.info("已订阅所有中间价格")

    async def _handle_message(self, message: str):
        """处理收到的 WebSocket 消息"""
        try:
            # 记录原始消息
            logger.info(f"📨 原始 WebSocket 消息: {message[:500]}...")  # 前500字符

            data = json.loads(message)

            # 判断更新的频道/类型
            channel = data.get("channel", "unknown")

            # 记录解析后的数据
            logger.info(f"📦 已解析 - 频道: '{channel}', 键: {list(data.keys())}")

            # 创建更新对象
            update = WebSocketUpdate(
                channel=channel,
                data=data,
                timestamp=datetime.utcnow()
            )

            # 调用对应的回调函数
            callback_found = False
            for callback_channel, callback in self.callbacks.items():
                logger.info(f"🔍 检查回调: {callback_channel} vs {channel}")

                # 匹配逻辑：
                # 1. 完全匹配：channel == callback_channel
                # 2. 回调是频道的子串：callback_channel in channel
                # 3. 频道是回调的子串：channel in callback_channel（用于 "user" 匹配 "user:0x..."）
                # 4. 冒号前缀匹配（用于 user:address 匹配 user 频道）
                should_call = False
                if channel == callback_channel:
                    should_call = True
                elif callback_channel in channel:
                    should_call = True
                elif channel in callback_channel:
                    should_call = True
                elif ":" in callback_channel:
                    # 检查频道是否匹配前缀（如 "user" 匹配 "user:0x..."）
                    prefix = callback_channel.split(":")[0]
                    if channel == prefix:
                        should_call = True

                if should_call:
                    callback_found = True
                    logger.info(f"✅ 调用 {callback_channel} 的回调")
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(update)
                        else:
                            callback(update)
                    except Exception as e:
                        logger.error(f"{callback_channel} 回调执行出错: {e}")
                        import traceback
                        logger.error(traceback.format_exc())

            if not callback_found:
                # subscriptionResponse 只是确认消息，不算错误
                if channel == "subscriptionResponse":
                    logger.debug(f"✅ 订阅已确认: {data.get('data', {})}")
                else:
                    logger.warning(f"⚠️ 未找到频道 {channel} 的回调")

        except json.JSONDecodeError as e:
            logger.error(f"解析 WebSocket 消息失败: {e}")
            logger.error(f"原始消息: {message}")
        except Exception as e:
            logger.error(f"处理 WebSocket 消息出错: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def listen(self):
        """
        WebSocket 消息监听主循环
        连接断开时自动重连
        """
        while self.is_running:
            try:
                if not self.ws or self.ws.closed:
                    await self.connect()

                async for message in self.ws:
                    await self._handle_message(message)

            except websockets.exceptions.ConnectionClosed:
                logger.warning(f"WebSocket 连接已关闭，{self.reconnect_delay}秒后重连...")
                await asyncio.sleep(self.reconnect_delay)

            except Exception as e:
                logger.error(f"WebSocket 监听出错: {e}")
                await asyncio.sleep(self.reconnect_delay)

    async def run(self):
        """启动 WebSocket 连接和监听循环"""
        self.is_running = True
        await self.listen()

    async def stop(self):
        """停止 WebSocket 连接"""
        self.is_running = False
        await self.disconnect()
