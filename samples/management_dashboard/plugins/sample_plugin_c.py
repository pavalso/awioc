"""
Sample Plugin C - Metrics Collector Simulator

A sample plugin that simulates a metrics collection service for testing
the management dashboard's enable/disable functionality.
"""

from typing import Literal

import pydantic

from awioc import get_logger, inject, get_config


class MetricsConfig(pydantic.BaseModel):
    """Configuration for the metrics plugin."""
    __prefix__ = "metrics"

    collection_interval: int = 10
    export_format: Literal["prometheus", "json", "statsd"] = "prometheus"
    retention_hours: int = 24
    enable_histogram: bool = True
    labels: dict[str, str] = pydantic.Field(default_factory=dict)

__metadata__ = {
    "name": "metrics_plugin",
    "version": "0.5.0",
    "description": "Simulates a metrics collection service",
    "wire": True,
    "config": MetricsConfig
}

@inject
async def initialize(logger=get_logger(), config=get_config(MetricsConfig)):
    logger.info("Metrics plugin: Starting collector...")
    logger.info(f"Metrics plugin: interval={config.collection_interval}s, format={config.export_format}")
    logger.info(f"Metrics plugin: retention={config.retention_hours}h, histogram={config.enable_histogram}")
    logger.info("Metrics plugin: Collector started")


@inject
async def shutdown(logger=get_logger()):
    logger.info("Metrics plugin: Stopping collector...")
    logger.info("Metrics plugin: Collector stopped")
