"""Entry point for running the IOC framework as a module (python -m ioc)."""

import asyncio
import logging
import logging.config
import sys
from pathlib import Path
from typing import Optional

import pydantic
import pydantic_settings

from . import (
    compile_ioc_app,
    initialize_ioc_app,
    initialize_components,
    shutdown_components,
    wait_for_components,
)
from .utils import expanded_path


class CLIConfig(pydantic_settings.BaseSettings):
    """CLI-specific configuration for logging options."""

    logging_config: Optional[Path] = pydantic.Field(
        default=None,
        description="Path to logging configuration file (.ini)"
    )

    verbose: int = pydantic.Field(
        default=0,
        description="Verbosity level: -v (INFO), -vv (DEBUG), -vvv (DEBUG + libs)"
    )

    @pydantic.field_validator("logging_config", mode="before")
    @classmethod
    def validate_logging_config(cls, v):
        if v is None:
            return v
        return expanded_path(v)

    model_config = pydantic_settings.SettingsConfigDict(
        cli_parse_args=True,
        cli_ignore_unknown_args=True,
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


def configure_logging(config: CLIConfig) -> None:
    """Configure logging based on CLI arguments.

    Priority:
    1. logging_config (.ini file) if provided
    2. verbose level (-v, -vv, -vvv)
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


async def run():
    cli_config = CLIConfig()

    api = initialize_ioc_app()
    app = api.provided_app()

    configure_logging(cli_config)
    logger = api.provided_logger()

    compile_ioc_app(api)

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
    preprocess_verbose_args()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        ...


if __name__ == "__main__":
    main()
