"""Run command - starts the AWIOC application."""

import logging
import os

from .base import BaseCommand, CommandContext, register_command
from ..bootstrap import initialize_ioc_app
from ..components.lifecycle import (
    initialize_components,
    shutdown_components,
    wait_for_components,
)
from ..components.registry import as_component

logger = logging.getLogger(__name__)


@register_command("run")
@as_component(
    name="Run Command",
    version="1.0.0",
    description="Start the AWIOC application and run components",
)
class RunCommand(BaseCommand):
    """Run command that starts the AWIOC application.

    This is the default command that initializes all components,
    waits for the application to complete, and handles graceful shutdown.
    """

    @property
    def name(self) -> str:
        return "run"

    @property
    def description(self) -> str:
        return "Start the AWIOC application"

    @property
    def help_text(self) -> str:
        return """Run the AWIOC application.

This command initializes all configured components (app, libraries, plugins),
waits for the application to complete, and handles graceful shutdown.

Usage:
    awioc run [options]
    awioc [options]  (run is the default command)

Options:
    -c, --config-path PATH    Path to configuration file (YAML/JSON)
    --context CONTEXT         Environment context (loads .{context}.env)
    -v, --verbose            Increase verbosity (-v, -vv, -vvv)
"""

    async def execute(self, ctx: CommandContext) -> int:
        """Execute the run command."""

        if ctx.config_path:
            os.environ["CONFIG_PATH"] = str(ctx.config_path)

        if ctx.context:
            os.environ["CONTEXT"] = ctx.context

        api = initialize_ioc_app()
        app = api.provided_app()

        try:
            await initialize_components(app)

            exceptions = await initialize_components(
                *api.provided_libs(),
                return_exceptions=True
            )

            if exceptions:
                logger.error(
                    "Error during library initialization",
                    exc_info=ExceptionGroup("Initialization Errors", exceptions)
                )
                return 1

            exceptions = await initialize_components(
                *api.provided_plugins(),
                return_exceptions=True
            )

            if exceptions:
                logger.error(
                    "Error during plugin initialization",
                    exc_info=ExceptionGroup("Initialization Errors", exceptions)
                )

            await wait_for_components(app)
            return 0
        finally:
            await shutdown_components(app)
