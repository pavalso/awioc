"""Entry point for running the IOC framework as a module (python -m ioc)."""

import asyncio
import logging
import logging.config
import sys

from .config.models import IOCBaseConfig
from . import (
    compile_ioc_app,
    initialize_ioc_app,
    initialize_components,
    shutdown_components,
    wait_for_components
)


def preprocess_verbose_args() -> None:
    """Convert -v, -vv, -vvv flags to --verbose N format.

    This allows standard Unix-style verbose flags while using pydantic-settings
    for argument parsing.
    """
    new_argv = [sys.argv[0]]
    verbose_count = 0

    for arg in sys.argv[1:]:
        if arg.startswith("-v") and not arg.startswith("--"):
            if arg == "-v":
                verbose_count += 1
            elif all(c == "v" for c in arg[1:]):
                verbose_count += len(arg) - 1
            else:
                new_argv.append(arg)
        else:
            new_argv.append(arg)

    if verbose_count > 0:
        new_argv.append(f"--verbose={verbose_count}")

    sys.argv = new_argv


def configure_logging(config: IOCBaseConfig) -> None:
    """Configure logging based on CLI arguments.

    Priority:
    1. logging_config (.ini file) if provided
    2. verbose level (-v, -vv, -vvv)
    3. Default (WARNING level)
    """
    if config.logging_config and config.logging_config.exists():
        logging.config.fileConfig(config.logging_config)
        return

    level_map = {
        0: logging.WARNING,
        1: logging.INFO,
        2: logging.DEBUG,
    }
    level = level_map.get(min(config.verbose, 2), logging.DEBUG)

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


async def run():
    api = initialize_ioc_app()
    app = api.provided_app()

    compile_ioc_app(api)

    await initialize_components(app)

    try:
        await wait_for_components(app)
    finally:
        await shutdown_components(app)


def main():
    preprocess_verbose_args()
    config = IOCBaseConfig.load_config()
    configure_logging(config)
    logger = logging.getLogger(__name__)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user (KeyboardInterrupt).")


if __name__ == "__main__":
    main()
