"""Init command - initializes a new AWIOC project."""

import logging
from pathlib import Path

from .base import BaseCommand, CommandContext, register_command
from ..components.registry import as_component

logger = logging.getLogger(__name__)

# Template for ioc.yaml configuration file
IOC_YAML_TEMPLATE = """# AWIOC Configuration File
# See documentation for all available options

components:
  # Main application component
  app: app:AppComponent()

  # Libraries (named components that can be injected)
  libraries: {}

  # Plugins (optional components loaded at runtime)
  plugins: []

# Application-specific configuration
# Add your component configurations here using their __prefix__
"""

# Template for a basic app component
APP_COMPONENT_TEMPLATE = '''"""Main application component."""

import asyncio
from awioc import as_component, inject, get_logger


@as_component(
    name="{app_name}",
    version="1.0.0",
    description="{app_description}",
    wire=True,
)
class AppComponent:
    """Main application component.

    This component serves as the entry point for your AWIOC application.
    """

    def __init__(self):
        self._shutdown_event = asyncio.Event()

    @inject
    async def initialize(self, logger=get_logger()) -> None:
        """Initialize the application."""
        logger.info("{app_name} starting...")

    async def wait(self) -> None:
        """Wait for shutdown signal."""
        await self._shutdown_event.wait()

    async def shutdown(self) -> None:
        """Shutdown the application."""
        self._shutdown_event.set()
'''

# Template for .env file
ENV_TEMPLATE = """# Environment configuration for AWIOC application
# Uncomment and modify as needed

# CONFIG_PATH=ioc.yaml
# CONTEXT=dev
"""


@register_command("init")
@as_component(
    name="Init Command",
    version="1.0.0",
    description="Initialize a new AWIOC project",
)
class InitCommand(BaseCommand):
    """Init command that creates a new AWIOC project structure.

    Creates the necessary files and directories for a new AWIOC application:
    - ioc.yaml: Main configuration file
    - app.py: Basic application component
    - .env: Environment configuration template
    """

    @property
    def name(self) -> str:
        return "init"

    @property
    def description(self) -> str:
        return "Initialize a new AWIOC project"

    @property
    def help_text(self) -> str:
        return """Initialize a new AWIOC project.

Creates the basic project structure with template files:
  - ioc.yaml: Main configuration file
  - app.py: Basic application component
  - .env: Environment configuration

Usage:
    awioc init [directory] [options]

Arguments:
    directory           Target directory (default: current directory)

Options:
    --name NAME         Application name (default: "My AWIOC App")
    --force             Overwrite existing files
"""

    async def execute(self, ctx: CommandContext) -> int:
        """Execute the init command."""
        # Parse arguments
        target_dir = Path.cwd()
        app_name = "My AWIOC App"
        force = False

        args = ctx.args.copy()
        while args:
            arg = args.pop(0)
            if arg == "--name" and args:
                app_name = args.pop(0)
            elif arg == "--force":
                force = True
            elif not arg.startswith("-"):
                target_dir = Path(arg)

        # Create target directory if needed
        target_dir = target_dir.resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        files_created = []
        files_skipped = []

        # Create ioc.yaml
        ioc_yaml_path = target_dir / "ioc.yaml"
        if ioc_yaml_path.exists() and not force:
            files_skipped.append("ioc.yaml")
            logger.warning("ioc.yaml already exists, skipping (use --force to overwrite)")
        else:
            ioc_yaml_path.write_text(IOC_YAML_TEMPLATE, encoding="utf-8")
            files_created.append("ioc.yaml")

        # Create app.py
        app_path = target_dir / "app.py"
        if app_path.exists() and not force:
            files_skipped.append("app.py")
            logger.warning("app.py already exists, skipping (use --force to overwrite)")
        else:
            content = APP_COMPONENT_TEMPLATE.format(
                app_name=app_name,
                app_description=f"Main application for {app_name}",
            )
            app_path.write_text(content, encoding="utf-8")
            files_created.append("app.py")

        # Create .env
        env_path = target_dir / ".env"
        if env_path.exists() and not force:
            files_skipped.append(".env")
            logger.warning(".env already exists, skipping (use --force to overwrite)")
        else:
            env_path.write_text(ENV_TEMPLATE, encoding="utf-8")
            files_created.append(".env")

        # Create plugins directory
        plugins_dir = target_dir / "plugins"
        if not plugins_dir.exists():
            plugins_dir.mkdir()
            files_created.append("plugins/")

        # Summary
        if files_created:
            logger.info(f"Created files in {target_dir}:")
            for f in files_created:
                logger.info(f"  - {f}")

        if files_skipped:
            logger.info(f"Skipped existing files: {', '.join(files_skipped)}")

        if files_created:
            logger.info(f"\nProject initialized! Run 'awioc run -c {ioc_yaml_path}' to start.")
            return 0
        else:
            logger.info("No files created. Directory already contains an AWIOC project.")
            return 0
