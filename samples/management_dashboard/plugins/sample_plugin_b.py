"""
Sample Plugin B - Cache Service Simulator

A sample plugin that simulates a cache service for testing
the management dashboard's enable/disable functionality.
"""

from awioc import get_logger, inject

__metadata__ = {
    "name": "cache_plugin",
    "version": "1.2.0",
    "description": "Simulates an in-memory cache service",
    "wire": True,
}

_cache: dict = {}
_enabled = False


@inject
async def initialize(logger=get_logger()):
    global _enabled, _cache
    logger.info("Cache plugin: Initializing cache...")
    _cache = {}
    _enabled = True
    logger.info("Cache plugin: Cache ready")


@inject
async def shutdown(logger=get_logger()):
    global _enabled, _cache
    logger.info("Cache plugin: Clearing cache...")
    _cache = {}
    _enabled = False
    logger.info("Cache plugin: Cache cleared")


def is_enabled() -> bool:
    return _enabled


def get(key: str):
    if not _enabled:
        raise RuntimeError("Cache not enabled")
    return _cache.get(key)


def set(key: str, value):
    if not _enabled:
        raise RuntimeError("Cache not enabled")
    _cache[key] = value


def clear():
    global _cache
    _cache = {}
