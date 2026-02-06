from typing import Optional
from loguru import logger
from hyperliquid.models import Position


class PositionSizer:
    """
    根据不同的仓位模式计算跟单仓位大小
    """

    def __init__(
        self,
        portfolio_ratio: float = 0.01,
        max_position_size: float = 1000.0,
        max_total_exposure: float = 5000.0
    ):
        """初始化仓位计算器

        Args:
            portfolio_ratio: 按比例模式下的比率（如 0.01 = 1:100）
            max_position_size: 单个仓位最大金额
            max_total_exposure: 所有仓位最大总敞口
        """
        self.portfolio_ratio = portfolio_ratio
        self.max_position_size = max_position_size
        self.max_total_exposure = max_total_exposure

        logger.info(f"仓位计算器已初始化 - 比率: {portfolio_ratio}")

    def calculate_size(
        self,
        target_position: Position,
        target_wallet_balance: float,
        your_wallet_balance: float,
        your_current_exposure: float = 0.0
    ) -> Optional[float]:
        """
        计算跟单的合适仓位大小

        Args:
            target_position: 目标钱包的持仓
            target_wallet_balance: 目标钱包的总余额
            your_wallet_balance: 你的钱包余额
            your_current_exposure: 你当前的总敞口

        Returns:
            应交易的仓位大小，如果应跳过则返回 None
        """
        size = self._calculate_proportional_size(
            target_position,
            target_wallet_balance,
            your_wallet_balance
        )

        # 应用最大仓位限制
        if size and size > self.max_position_size:
            logger.warning(f"仓位大小 ${size:.2f} 超过上限 ${self.max_position_size:.2f}，已截断")
            size = self.max_position_size

        # 检查总敞口限制
        if size and (your_current_exposure + size) > self.max_total_exposure:
            logger.error(f"将超过最大敞口: ${your_current_exposure + size:.2f} > ${self.max_total_exposure:.2f}")
            return None

        return size

    def _calculate_proportional_size(
        self,
        target_position: Position,
        target_wallet_balance: float,
        your_wallet_balance: float
    ) -> Optional[float]:
        """
        按比例计算仓位大小

        示例：
            目标钱包: $100k, 你的钱包: $1k (比率 = 0.01)
            目标开仓: $5k
            你的仓位: $5k * 0.01 = $50
        """
        # 计算目标持仓名义价值
        target_notional = target_position.size * target_position.entry_price

        # 计算钱包之间的比率
        if target_wallet_balance > 0:
            wallet_ratio = your_wallet_balance / target_wallet_balance
        else:
            wallet_ratio = self.portfolio_ratio

        # 计算你的仓位大小
        your_notional = target_notional * wallet_ratio

        # 转换回币的数量
        your_size = your_notional / target_position.entry_price if target_position.entry_price > 0 else 0

        logger.info(
            f"按比例计算: 目标 ${target_notional:.2f} -> 你的 ${your_notional:.2f} "
            f"(比率 {wallet_ratio:.4f}) = {your_size:.4f} 个币"
        )

        return your_size

