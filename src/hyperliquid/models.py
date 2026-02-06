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
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"

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
    liquidation_price: Optional[float] = None
    margin: Optional[float] = None
    timestamp: Optional[datetime] = None

    @property
    def notional_value(self) -> float:
        """计算持仓名义价值"""
        return self.size * self.current_price

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
    filled_size: float = 0.0
    status: str = "open"  # open, filled, cancelled, rejected
    timestamp: Optional[datetime] = None
    trigger_price: Optional[float] = None  # 止损单触发价格

    @property
    def is_filled(self) -> bool:
        return self.status == "filled"

    @property
    def is_open(self) -> bool:
        return self.status == "open"

@dataclass
class Trade:
    """已完成的交易记录"""
    trade_id: str
    symbol: str
    side: OrderSide
    size: float
    price: float
    timestamp: datetime
    fee: Optional[float] = None
    order_id: Optional[str] = None

@dataclass
class UserState:
    """用户账户完整状态"""
    address: str
    positions: List[Position]
    orders: List[Order]
    balance: float
    margin_used: float
    unrealized_pnl: float
    timestamp: datetime

    @property
    def available_balance(self) -> float:
        """计算可用余额"""
        return self.balance - self.margin_used

    @property
    def total_equity(self) -> float:
        """计算总权益（余额 + 未实现盈亏）"""
        return self.balance + self.unrealized_pnl

    @property
    def margin_ratio(self) -> float:
        """计算保证金使用率"""
        if self.balance == 0:
            return 0.0
        return (self.margin_used / self.balance) * 100

@dataclass
class WebSocketUpdate:
    """WebSocket 更新事件"""
    channel: str
    data: dict
    timestamp: datetime
