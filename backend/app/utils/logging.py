"""
KMatch 统一日志配置

用法:
    from app.utils.logging import get_logger
    logger = get_logger(__name__)
    logger.info("...")
    logger.warning("...")
"""

import logging
import sys

# 根 logger 格式
_FORMAT = "%(asctime)s [%(levelname)-7s] %(name)s | %(message)s"
_DATE_FMT = "%H:%M:%S"

_handler: logging.Handler | None = None


def _ensure_handler() -> logging.Handler:
    global _handler
    if _handler is None:
        _handler = logging.StreamHandler(sys.stdout)
        _handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FMT))
    return _handler


def get_logger(name: str) -> logging.Logger:
    """获取命名 logger，自动挂载统一 handler"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.addHandler(_ensure_handler())
    logger.setLevel(logging.DEBUG)
    return logger
