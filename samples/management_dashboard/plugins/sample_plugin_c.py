"""
Sample Plugin C - Metrics Collector Simulator

A sample plugin that simulates a metrics collection service for testing
the management dashboard's enable/disable functionality.
"""

import time

from awioc import get_logger, inject

__metadata__ = {
    "name": "metrics_plugin",
    "version": "0.5.0",
    "description": "Simulates a metrics collection service",
    "wire": True,
}

_metrics: dict = {}
_collecting = False
_start_time = None


@inject
async def initialize(logger=get_logger()):
    global _collecting, _start_time, _metrics
    logger.info("Metrics plugin: Starting collector...")
    _metrics = {
        "requests_total": 0,
        "errors_total": 0,
        "latency_sum": 0.0,
    }
    _start_time = time.time()
    _collecting = True
    logger.info("Metrics plugin: Collector started")


@inject
async def shutdown(logger=get_logger()):
    global _collecting, _start_time
    logger.info("Metrics plugin: Stopping collector...")
    _collecting = False
    _start_time = None
    logger.info("Metrics plugin: Collector stopped")


def is_collecting() -> bool:
    return _collecting


def record_request(latency: float = 0.0, error: bool = False):
    if not _collecting:
        return
    _metrics["requests_total"] += 1
    _metrics["latency_sum"] += latency
    if error:
        _metrics["errors_total"] += 1


def get_metrics() -> dict:
    if not _collecting:
        return {}
    uptime = time.time() - _start_time if _start_time else 0
    return {
        **_metrics,
        "uptime_seconds": uptime,
        "avg_latency": (_metrics["latency_sum"] / _metrics["requests_total"])
        if _metrics["requests_total"] > 0 else 0,
    }
