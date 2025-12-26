"""Entry point for running the IOC framework as a module (python -m ioc)."""

import argparse
import asyncio
import logging

logger = logging.getLogger(__name__)

import logging.config
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import (
    initialize_ioc_app,
    initialize_components,
    shutdown_components,
    wait_for_components,
)
from .utils import expanded_path


@dataclass
class CLIConfig:
    """CLI-specific configuration for logging and IOC settings."""
    logging_config: Optional[Path] = None
    verbose: int = 0
    config_path: Optional[Path] = None
    context: Optional[str] = None


def parse_args() -> CLIConfig:
    """Parse command-line arguments using argparse."""
    parser = argparse.ArgumentParser(
        description="Run the IOC framework application",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "-c", "--config-path",
        type=Path,
        default=None,
        help="Path to the IOC components configuration file (YAML/JSON)"
    )

    parser.add_argument(
        "--context",
        type=str,
        default=None,
        help="Environment context (loads .{context}.env file)"
    )

    parser.add_argument(
        "--logging-config",
        type=Path,
        default=None,
        help="Path to logging configuration file (.ini)"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Verbosity level: -v (INFO), -vv (DEBUG), -vvv (DEBUG + libs)"
    )

    args, _ = parser.parse_known_args()

    logging_config = None
    if args.logging_config:
        logging_config = expanded_path(args.logging_config)

    config_path = None
    if args.config_path:
        config_path = expanded_path(args.config_path)

    return CLIConfig(
        logging_config=logging_config,
        verbose=args.verbose,
        config_path=config_path,
        context=args.context
    )


def configure_logging(config: CLIConfig) -> None:
    """Configure logging based on CLI arguments.

    Priority:
    1. logging_config (.ini file) if provided
    2. verbose level (-v, -vv, -vv)
    3. Default (INFO level, simple format)
    """
    if config.logging_config and config.logging_config.exists():
        logging.config.fileConfig(config.logging_config)
        return

    level_map = {
        0: logging.INFO,
        1: logging.DEBUG
    }
    level = level_map.get(min(config.verbose, len(level_map)), logging.DEBUG)

    format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    if config.verbose >= 2:
        format_str = "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"

    logging.basicConfig(
        level=level,
        format=format_str,
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    if config.verbose < 3:
        for lib in ("asyncio", "urllib3", "httpcore", "httpx"):
            logging.getLogger(lib).setLevel(logging.WARNING)


async def run(cli_config: CLIConfig):
    if cli_config.config_path:
        os.environ["CONFIG_PATH"] = str(cli_config.config_path)

    if cli_config.context:
        os.environ["CONTEXT"] = cli_config.context

    api = initialize_ioc_app()
    app = api.provided_app()

    try:
        await initialize_components(app)

        exceptions = await initialize_components(
            *api.provided_libs(),
            return_exceptions=True
        )

        if exceptions:
            logger.error("Error during library initialization",
                         exc_info=ExceptionGroup("Initialization Errors", exceptions))
            return  # Abort initialization on library errors

        exceptions = await initialize_components(
            *api.provided_plugins(),
            return_exceptions=True
        )

        if exceptions:
            logger.error("Error during plugin initialization",
                         exc_info=ExceptionGroup("Initialization Errors", exceptions))

        await wait_for_components(app)
    finally:
        await shutdown_components(app)


def main():
    cli_config = parse_args()

    configure_logging(cli_config)

    try:
        asyncio.run(run(cli_config))
    except KeyboardInterrupt:
        ...


if __name__ == "__main__":
    main()
