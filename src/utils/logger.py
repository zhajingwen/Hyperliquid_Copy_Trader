import sys
from pathlib import Path
from loguru import logger

def setup_logger(log_file: str = "./logs/trading.log", log_level: str = "INFO"):
    """
    配置 loguru 日志器，支持文件和控制台输出
    """
    # 如果日志目录不存在则创建
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # 移除默认处理器
    logger.remove()

    # 添加带颜色的控制台处理器
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=log_level,
        colorize=True
    )

    # 添加文件处理器
    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
        level=log_level,
        rotation="100 MB",
        retention="30 days",
        compression="zip"
    )

    return logger
