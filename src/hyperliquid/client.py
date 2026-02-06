import aiohttp
from typing import Optional
from loguru import logger
from .models import Position, Order, UserState, PositionSide, OrderSide

class HyperliquidClient:
    """
    Hyperliquid REST API 客户端
    """

    def __init__(self, api_url: str = "https://api.hyperliquid.xyz"):
        self.api_url = api_url
        self.info_url = f"{api_url}/info"
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _post(self, url: str, data: dict) -> dict:
        """发送 POST 请求到 API"""
        if not self.session:
            self.session = aiohttp.ClientSession()

        try:
            async with self.session.post(url, json=data) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"API 请求失败: {e}")
            raise

    async def get_user_state(self, address: str) -> Optional[UserState]:
        """
        获取用户完整状态，包括持仓和订单

        Args:
            address: 钱包地址

        Returns:
            UserState 对象，失败则返回 None
        """
        try:
            data = {
                "type": "clearinghouseState",
                "user": address
            }

            response = await self._post(self.info_url, data)

            if not response:
                return None

            # 解析持仓
            positions = []
            if "assetPositions" in response:
                for pos_data in response["assetPositions"]:
                    position = pos_data.get("position", {})
                    if position and position.get("szi") != "0":  # szi 为持仓数量
                        size = float(position.get("szi", 0))
                        side = PositionSide.LONG if size > 0 else PositionSide.SHORT

                        positions.append(Position(
                            symbol=pos_data.get("coin", ""),
                            side=side,
                            size=abs(size),
                            entry_price=float(position.get("entryPx", 0)),
                            current_price=float(position.get("positionValue", 0)) / abs(size) if size != 0 else 0,
                            leverage=float(position.get("leverage", {}).get("value", 1)),
                            unrealized_pnl=float(position.get("unrealizedPnl", 0))
                        ))

            # 解析订单
            orders = []
            if "openOrders" in response:
                for order_data in response["openOrders"]:
                    order = order_data.get("order", {})
                    orders.append(Order(
                        order_id=str(order.get("oid", "")),
                        symbol=order.get("coin", ""),
                        side=OrderSide.BUY if order.get("side") == "B" else OrderSide.SELL,
                        order_type=order.get("orderType", "limit").lower(),
                        size=float(order.get("sz", 0)),
                        price=float(order.get("limitPx", 0)) if order.get("limitPx") else None,
                        trigger_price=float(order.get("triggerPx", 0)) if order.get("triggerPx") else None
                    ))

            # 解析账户余额
            balance = float(response.get("marginSummary", {}).get("accountValue", 0))
            unrealized_pnl = float(response.get("marginSummary", {}).get("totalNtlPos", 0))

            from datetime import datetime
            return UserState(
                address=address,
                positions=positions,
                orders=orders,
                balance=balance,
                unrealized_pnl=unrealized_pnl,
                timestamp=datetime.utcnow()
            )

        except Exception as e:
            logger.error(f"获取用户状态失败 {address}: {e}")
            return None
