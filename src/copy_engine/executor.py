"""Hyperliquid 交易执行引擎"""
import time
from typing import Optional, Dict, Any
from decimal import Decimal
from eth_account import Account
import aiohttp

from utils.logger import logger
from hyperliquid.models import OrderType, OrderSide


class TradeExecutor:
    """在 Hyperliquid 交易所执行交易"""

    def __init__(
        self,
        wallet_address: str,
        private_key: str,
        info_url: str = "https://api.hyperliquid.xyz/info",
        exchange_url: str = "https://api.hyperliquid.xyz/exchange",
        dry_run: bool = True
    ):
        """初始化交易执行器

        Args:
            wallet_address: Hyperliquid 钱包地址
            private_key: 用于签名交易的私钥
            info_url: Hyperliquid 信息 API 地址
            exchange_url: Hyperliquid 交易 API 地址
            dry_run: 为 True 时仅模拟订单，不实际执行
        """
        self.wallet_address = wallet_address.lower() if wallet_address else None
        self.private_key = private_key
        self.info_url = info_url
        self.exchange_url = exchange_url
        self.dry_run = dry_run

        # 如果有凭证则初始化签名账户
        self.account = None
        if self.private_key and not self.dry_run:
            try:
                self.account = Account.from_key(self.private_key)
                # 验证地址是否匹配
                if self.account.address.lower() != self.wallet_address:
                    raise ValueError(
                        f"私钥地址 {self.account.address} 与配置地址 "
                        f"{self.wallet_address} 不匹配"
                    )
                logger.info(f"✅ 执行器已初始化，钱包地址: {self.wallet_address}")
            except Exception as e:
                logger.error(f"初始化签名账户失败: {e}")
                raise
        elif not self.dry_run:
            raise ValueError("实盘模式必须提供私钥")
        else:
            logger.warning("⚠️ 当前为模拟运行模式 - 不会执行真实交易")

    def _sign_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """使用 EIP-712 结构化数据签名对操作进行签名

        Args:
            action: 要签名的操作

        Returns:
            带签名的操作数据
        """
        if not self.account:
            raise ValueError("没有签名账户，无法签名操作")

        # 添加时间戳随机数
        timestamp = int(time.time() * 1000)

        # 创建 EIP-712 结构化数据
        structured_data = {
            "domain": {
                "name": "Exchange",
                "version": "1",
                "chainId": 1337,
                "verifyingContract": "0x0000000000000000000000000000000000000000"
            },
            "primaryType": "Agent",
            "types": {
                "Agent": [
                    {"name": "source", "type": "string"},
                    {"name": "connectionId", "type": "bytes32"}
                ],
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"}
                ]
            },
            "message": {
                "source": "a",  # "a" 表示 API 订单
                "connectionId": "0x" + "0" * 64
            }
        }

        # 使用 sign_typed_data 方法签名
        signed_message = self.account.sign_typed_data(
            structured_data["domain"],
            {"Agent": structured_data["types"]["Agent"]},
            structured_data["message"]
        )

        # 构建签名对象
        signature = {
            "r": "0x" + signed_message.r.to_bytes(32, "big").hex(),
            "s": "0x" + signed_message.s.to_bytes(32, "big").hex(),
            "v": signed_message.v
        }

        # 构建最终请求
        return {
            "action": action,
            "nonce": timestamp,
            "signature": signature,
            "vaultAddress": None
        }

    async def _update_leverage(
        self,
        symbol: str,
        leverage: int,
        is_cross: bool = True
    ) -> bool:
        """更新指定交易对的杠杆倍数

        Args:
            symbol: 交易对（如 "BTC"）
            leverage: 杠杆倍数（整数）
            is_cross: 为 True 使用全仓模式，为 False 使用逐仓模式

        Returns:
            成功返回 True，失败返回 False
        """
        try:
            action = {
                "type": "updateLeverage",
                "asset": symbol,
                "isCross": is_cross,
                "leverage": leverage
            }

            signed_action = self._sign_action(action)

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.exchange_url,
                    json=signed_action,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        await response.json()  # 读取响应
                        logger.success(f"✅ 已将 {symbol} 杠杆更新为 {leverage}x")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"更新杠杆失败: {error_text}")
                        return False

        except Exception as e:
            logger.error(f"更新杠杆出错: {e}")
            return False

    async def execute_market_order(
        self,
        symbol: str,
        side: OrderSide,
        size: Decimal,
        leverage: int = 1,
        reduce_only: bool = False
    ) -> Optional[str]:
        """执行市价单

        Args:
            symbol: 交易对（如 "BTC"）
            side: 订单方向（BUY 或 SELL）
            size: 订单数量
            leverage: 使用的杠杆倍数
            reduce_only: 为 True 时仅允许减仓

        Returns:
            成功返回订单ID，失败返回 None
        """
        if self.dry_run:
            return await self._simulate_order(
                symbol=symbol,
                side=side,
                size=size,
                order_type=OrderType.MARKET,
                leverage=leverage
            )

        try:
            # 如果需要先更新杠杆
            if leverage > 1:
                await self._update_leverage(symbol, leverage)

            # 创建市价单操作（价格0 = 市价单）
            action = {
                "type": "order",
                "orders": [{
                    "a": self.wallet_address,
                    "b": side == OrderSide.BUY,
                    "p": "0",  # 0 = 市价单
                    "s": str(float(size)),
                    "r": reduce_only,
                    "t": {"limit": {"tif": "Ioc"}},  # 立即成交或取消
                    "c": symbol
                }],
                "grouping": "na"
            }

            signed_action = self._sign_action(action)

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.exchange_url,
                    json=signed_action,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.success(
                            f"✅ 市价{side.value}单已执行: {symbol} "
                            f"数量={size} 杠杆={leverage}x"
                        )
                        # 从响应中提取订单ID
                        if result.get("status") == "ok" and result.get("response", {}).get("data"):
                            order_id = result["response"]["data"].get("statuses", [{}])[0].get("resting", {}).get("oid")
                            return order_id
                        return "executed"  # 订单已立即成交
                    else:
                        error_text = await response.text()
                        logger.error(f"执行市价单失败: {error_text}")
                        return None

        except Exception as e:
            logger.error(f"执行市价单出错: {e}")
            return None

    async def execute_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        size: Decimal,
        price: Decimal,
        leverage: int = 1,
        reduce_only: bool = False,
        post_only: bool = False
    ) -> Optional[str]:
        """执行限价单

        Args:
            symbol: 交易对（如 "BTC"）
            side: 订单方向（BUY 或 SELL）
            size: 订单数量
            price: 限价价格
            leverage: 使用的杠杆倍数
            reduce_only: 为 True 时仅允许减仓
            post_only: 为 True 时仅允许做 Maker（只挂单）

        Returns:
            成功返回订单ID，失败返回 None
        """
        if self.dry_run:
            return await self._simulate_order(
                symbol=symbol,
                side=side,
                size=size,
                order_type=OrderType.LIMIT,
                price=price,
                leverage=leverage
            )

        try:
            # 如果需要先更新杠杆
            if leverage > 1:
                await self._update_leverage(symbol, leverage)

            # 创建限价单操作
            tif = "Alo" if post_only else "Gtc"  # Alo = 仅添加流动性, Gtc = 撤单前有效

            action = {
                "type": "order",
                "orders": [{
                    "a": self.wallet_address,
                    "b": side == OrderSide.BUY,
                    "p": str(float(price)),
                    "s": str(float(size)),
                    "r": reduce_only,
                    "t": {"limit": {"tif": tif}},
                    "c": symbol
                }],
                "grouping": "na"
            }

            signed_action = self._sign_action(action)

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.exchange_url,
                    json=signed_action,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.success(
                            f"✅ 限价{side.value}单已挂出: {symbol} "
                            f"数量={size} 价格={price} 杠杆={leverage}x"
                        )
                        # 从响应中提取订单ID
                        if result.get("status") == "ok" and result.get("response", {}).get("data"):
                            order_id = result["response"]["data"].get("statuses", [{}])[0].get("resting", {}).get("oid")
                            return order_id
                        return None
                    else:
                        error_text = await response.text()
                        logger.error(f"挂限价单失败: {error_text}")
                        return None

        except Exception as e:
            logger.error(f"挂限价单出错: {e}")
            return None

    async def close_position(
        self,
        symbol: str,
        size: Optional[Decimal] = None,
        side: Optional[OrderSide] = None
    ) -> Optional[str]:
        """使用市价单平仓

        Args:
            symbol: 交易对
            size: 平仓数量（可选 - 不填则全部平仓）
            side: 平仓方向（可选 - 与当前持仓相反）

        Returns:
            成功返回订单ID，失败返回 None
        """
        if self.dry_run:
            if size and side:
                logger.info(f"🔵 模拟运行: 将平仓 {side.value} {size} {symbol}")
            else:
                logger.info(f"🔵 模拟运行: 将平仓 {symbol}")
            return f"dry_run_close_{symbol}_{int(time.time())}"

        # 如果未提供数量和方向，获取当前持仓信息
        if size is None or side is None:
            logger.warning(f"⚠️ 未提供 {symbol} 的数量和/或方向，使用 reduce_only 市价单")
            # 使用带 reduce_only 标志的小额市价单来平掉当前持仓
            return await self.execute_market_order(
                symbol=symbol,
                side=OrderSide.SELL,  # 无论方向都会被 reduce_only 限制
                size=Decimal("0.001"),  # 最小数量配合 reduce_only
                reduce_only=True
            )

        return await self.execute_market_order(
            symbol=symbol,
            side=side,
            size=size,
            reduce_only=True
        )

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """撤销订单

        Args:
            symbol: 交易对
            order_id: 要撤销的订单ID

        Returns:
            成功返回 True，失败返回 False
        """
        if self.dry_run:
            logger.info(f"🔵 模拟运行: 将撤销 {symbol} 的订单 {order_id}")
            return True

        try:
            action = {
                "type": "cancel",
                "cancels": [{
                    "a": self.wallet_address,
                    "o": order_id
                }]
            }

            signed_action = self._sign_action(action)

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.exchange_url,
                    json=signed_action,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        logger.success(f"✅ 已撤销 {symbol} 的订单 {order_id}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"撤销订单失败: {error_text}")
                        return False

        except Exception as e:
            logger.error(f"撤销订单出错: {e}")
            return False

    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """撤销所有订单

        Args:
            symbol: 如果指定，仅撤销该交易对的订单

        Returns:
            已撤销的订单数量
        """
        if self.dry_run:
            logger.info(f"🔵 模拟运行: 将撤销所有订单{f' ({symbol})' if symbol else ''}")
            return 0

        try:
            action = {
                "type": "cancelByCloid",
                "cancels": [{
                    "asset": symbol if symbol else None,
                    "cloid": None  # 撤销全部
                }]
            }

            signed_action = self._sign_action(action)

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.exchange_url,
                    json=signed_action,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        count = len(result.get("response", {}).get("data", {}).get("statuses", []))
                        logger.success(f"✅ 已撤销 {count} 个订单{f' ({symbol})' if symbol else ''}")
                        return count
                    else:
                        error_text = await response.text()
                        logger.error(f"撤销所有订单失败: {error_text}")
                        return 0

        except Exception as e:
            logger.error(f"撤销所有订单出错: {e}")
            return 0

    async def _simulate_order(
        self,
        symbol: str,
        side: OrderSide,
        size: Decimal,
        order_type: OrderType,
        price: Optional[Decimal] = None,
        leverage: int = 1
    ) -> str:
        """模拟订单（不实际执行）

        Args:
            symbol: 交易对
            side: 订单方向
            size: 订单数量
            order_type: 订单类型
            price: 订单价格（限价单用）
            leverage: 杠杆倍数

        Returns:
            模拟订单ID
        """
        order_id = f"sim_{symbol}_{int(time.time())}"

        if order_type == OrderType.MARKET:
            logger.info(
                f"🔵 模拟运行: 将执行市价{side.value}单 {symbol} "
                f"数量={size} 杠杆={leverage}x → 订单ID: {order_id}"
            )
        else:
            logger.info(
                f"🔵 模拟运行: 将挂限价{side.value}单 {symbol} "
                f"数量={size} 价格={price} 杠杆={leverage}x → 订单ID: {order_id}"
            )

        return order_id
