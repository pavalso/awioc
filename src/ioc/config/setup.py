import logging
from logging import Logger
from typing import Optional


def setup_logging(
        name: Optional[str] = None,
        level: int = logging.INFO
) -> Logger:
    """
    Set up and configure a logger.

    :param name: Name for the logger. If None, returns root logger.
    :param level: Logging level.
    :return: Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
