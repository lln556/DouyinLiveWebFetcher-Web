"""
全局 Loguru 日志模块
提供统一的日志记录功能，支持房间上下文绑定
"""
import sys
from pathlib import Path
from loguru import logger

import config

# 移除默认的 handler
logger.remove()

# 日志格式定义
# 控制台格式（带颜色）
CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <7}</level> | "
    "<cyan>[{extra[room_id]}]</cyan> "
    "<blue>{extra[module]}</blue> | "
    "<level>{message}</level>"
)

# 文件格式（纯文本，便于检索）
FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss} | "
    "{level: <7} | "
    "[{extra[room_id]}] "
    "{extra[module]} | "
    "{message}"
)


def setup_logger():
    """
    配置全局日志器
    """
    # 确保日志目录存在
    log_dir = Path(config.BASE_DIR) / 'logs'
    log_dir.mkdir(exist_ok=True)
    
    # 控制台输出（彩色，INFO级别以上）
    logger.add(
        sys.stdout,
        format=CONSOLE_FORMAT,
        level=config.LOG_LEVEL,
        colorize=True,
        filter=lambda record: record["extra"].get("room_id") is not None
    )
    
    # 全局日志文件（所有级别）
    logger.add(
        log_dir / "app_{time:YYYY-MM-DD}.log",
        format=FILE_FORMAT,
        level="DEBUG",
        rotation="50 MB",
        retention="30 days",
        encoding="utf-8",
        filter=lambda record: record["extra"].get("room_id") is not None
    )
    
    # 错误日志单独记录
    logger.add(
        log_dir / "error_{time:YYYY-MM-DD}.log",
        format=FILE_FORMAT,
        level="ERROR",
        rotation="20 MB",
        retention="30 days",
        encoding="utf-8",
        filter=lambda record: record["extra"].get("room_id") is not None
    )
    
    return logger


def get_logger(module: str = "global", room_id: str = "全局"):
    """
    获取带上下文的日志器
    
    :param module: 模块名称
    :param room_id: 房间ID，默认为"全局"
    :return: 绑定上下文的日志器
    
    使用示例:
        log = get_logger("liveMan", "123456")
        log.info("连接成功")
        # 输出: 2026-01-31 11:00:00 | INFO    | [123456] liveMan | 连接成功
    """
    return logger.bind(module=module, room_id=room_id)


# 初始化日志配置
setup_logger()

# 导出默认日志器（用于全局日志）
log = get_logger()
