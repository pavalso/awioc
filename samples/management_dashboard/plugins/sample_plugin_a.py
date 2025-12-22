"""
Sample Plugin A - Database Connection Simulator

A sample plugin that simulates a database connection for testing
the management dashboard's enable/disable functionality.
"""

from typing import Literal

import pydantic

from awioc import get_logger, inject, get_config


class DatabaseConfig(pydantic.BaseModel):
    """Configuration for the database plugin."""
    __prefix__ = "database"

    host: str = "localhost"
    port: int = 5432
    database: str = "app_db"
    pool_size: int = 5
    timeout: int = 30
    ssl_mode: Literal["disable", "prefer", "require", "verify-ca", "verify-full"] = "prefer"
    max_overflow: int = 5

__metadata__ = {
    "name": "database_plugin",
    "version": "1.0.0",
    "description": "Simulates a database connection service",
    "wire": True,
    "config": DatabaseConfig
}

@inject
async def initialize(logger=get_logger(), config=get_config(DatabaseConfig)):
    logger.info(f"Database plugin: Connecting to {config.host}:{config.port}/{config.database}")
    logger.info(f"Database plugin: Pool size={config.pool_size}, timeout={config.timeout}s")
    logger.info("Database plugin: Connection established")


@inject
async def shutdown(logger=get_logger()):
    logger.info("Database plugin: Closing connection...")
    logger.info("Database plugin: Connection closed")
