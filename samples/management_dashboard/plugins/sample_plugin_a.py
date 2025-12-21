"""
Sample Plugin A - Database Connection Simulator

A sample plugin that simulates a database connection for testing
the management dashboard's enable/disable functionality.
"""

from awioc import get_logger, inject

__metadata__ = {
    "name": "database_plugin",
    "version": "1.0.0",
    "description": "Simulates a database connection service",
    "wire": True,
}

_connected = False


@inject
async def initialize(logger=get_logger()):
    global _connected
    logger.info("Database plugin: Establishing connection...")
    _connected = True
    logger.info("Database plugin: Connection established")


@inject
async def shutdown(logger=get_logger()):
    global _connected
    logger.info("Database plugin: Closing connection...")
    _connected = False
    logger.info("Database plugin: Connection closed")


def is_connected() -> bool:
    return _connected


async def query(sql: str) -> dict:
    if not _connected:
        raise RuntimeError("Database not connected")
    return {"result": f"Executed: {sql}"}
