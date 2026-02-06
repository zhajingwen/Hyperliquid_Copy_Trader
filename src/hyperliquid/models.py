from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime
from enum import Enum

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"

class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"

@dataclass
class Position:
    """持仓信息"""
    symbol: str
    side: PositionSide
    size: float
    entry_price: float
    current_price: float
    leverage: float
    unrealized_pnl: float

    @property
    def pnl_percentage(self) -> float:
        """计算盈亏百分比"""
        if self.entry_price == 0:
            return 0.0

        if self.side == PositionSide.LONG:
            return ((self.current_price - self.entry_price) / self.entry_price) * 100
        else:  # 空仓
            return ((self.entry_price - self.current_price) / self.entry_price) * 100

@dataclass
class Order:
    """订单信息（挂单或已成交）"""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    size: float
    price: Optional[float] = None
    trigger_price: Optional[float] = None  # 止损单触发价格

@dataclass
class UserState:
    """用户账户完整状态"""
    address: str
    positions: List[Position]
    orders: List[Order]
    balance: float
    unrealized_pnl: float
    timestamp: datetime

    @property
    def total_equity(self) -> float:
        """计算总权益（余额 + 未实现盈亏）"""
        return self.balance + self.unrealized_pnl

@dataclass
class WebSocketUpdate:
    """WebSocket 更新事件"""
    channel: str
    data: dict
