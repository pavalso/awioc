"""
Sample Plugin B - Cache Service Simulator

A sample plugin that simulates a cache service for testing
the management dashboard's enable/disable functionality.
"""

from typing import Literal

import pydantic

from awioc import get_logger, inject, get_config


class CacheConfig(pydantic.BaseModel):
    """Configuration for the cache plugin."""
    __prefix__ = "cache"

    backend: Literal["memory", "redis", "memcached"] = "memory"
    max_size: int = 1000
    default_ttl: int = 3600
    eviction_policy: Literal["lru", "lfu", "fifo"] = "lru"
    compression: bool = False

__metadata__ = {
    "name": "cache_plugin",
    "version": "1.2.0",
    "description": "Simulates an in-memory cache service",
    "wire": True,
    "config": CacheConfig
}

@inject
async def initialize(logger=get_logger(), config=get_config(CacheConfig)):
    logger.info(f"Cache plugin: Initializing {config.backend} cache...")
    logger.info(f"Cache plugin: max_size={config.max_size}, ttl={config.default_ttl}s, policy={config.eviction_policy}")
    logger.info("Cache plugin: Cache ready")


@inject
async def shutdown(logger=get_logger()):
    logger.info("Cache plugin: Clearing cache...")
    logger.info("Cache plugin: Cache cleared")
