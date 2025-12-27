"""Init command - initializes a new AWIOC project."""

import logging
import re
from pathlib import Path

import yaml

from .base import BaseCommand, CommandContext, register_command
from ..components.registry import as_component
from ..loader.manifest import AWIOC_DIR, MANIFEST_FILENAME

logger = logging.getLogger(__name__)


def to_snake_case(name: str) -> str:
    """Convert a name to snake_case for file names."""
    # Replace spaces and hyphens with underscores
    name = re.sub(r'[\s\-]+', '_', name)
    # Insert underscore before uppercase letters and lowercase them
    name = re.sub(r'([a-z])([A-Z])', r'\1_\2', name)
    # Remove non-alphanumeric characters except underscores
    name = re.sub(r'[^a-zA-Z0-9_]', '', name)
    return name.lower()


def to_pascal_case(name: str) -> str:
    """Convert a name to PascalCase for class names."""
    # Split on spaces, hyphens, and underscores
    words = re.split(r'[\s\-_]+', name)
    # Capitalize each word and join
    return ''.join(word.capitalize() for word in words if word)


# Template for ioc.yaml configuration file
IOC_YAML_TEMPLATE = """# AWIOC Configuration File
# See documentation for all available options

components:
  # Main application component
  app: "{module_name}:{class_name}()"

  # Libraries (named components that can be injected)
  libraries: {{}}

  # Plugins (optional components loaded at runtime)
  plugins: []

# Application-specific configuration
# Add your component configurations here using their __prefix__
"""

# Template for a basic app component
APP_COMPONENT_TEMPLATE = '''"""{app_name} - Main application component."""

import asyncio
from awioc import inject, get_logger


class {class_name}:
    """Main application component for {app_name}.

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

# Template for __init__.py
INIT_TEMPLATE = '''"""{app_name} - AWIOC Application."""

from .{module_name} import {class_name}

__all__ = ["{class_name}"]
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
    - <name>.py: Application component file
    - __init__.py: Module exports
    - .awioc/manifest.yaml: Component manifest
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
  - <name>.py: Application component (named after your app)
  - __init__.py: Module exports
  - .awioc/manifest.yaml: Component manifest
  - .env: Environment configuration

Usage:
    awioc init [directory] [options]

Arguments:
    directory           Target directory (default: current directory)

Options:
    --name NAME         Application name (default: "My App")
    --force             Overwrite existing files

Examples:
    awioc init                      # Initialize in current directory
    awioc init my_project           # Initialize in my_project directory
    awioc init --name "My Service"  # Initialize with custom app name
"""

    async def execute(self, ctx: CommandContext) -> int:
        """Execute the init command."""
        # Parse arguments
        target_dir = Path.cwd()
        app_name = "My App"
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

        # Derive names from app_name
        module_name = to_snake_case(app_name)
        class_name = to_pascal_case(app_name) + "Component"

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
            content = IOC_YAML_TEMPLATE.format(
                module_name=module_name,
                class_name=class_name,
            )
            ioc_yaml_path.write_text(content, encoding="utf-8")
            files_created.append("ioc.yaml")

        # Create app component file (<name>.py)
        app_path = target_dir / f"{module_name}.py"
        if app_path.exists() and not force:
            files_skipped.append(f"{module_name}.py")
            logger.warning(f"{module_name}.py already exists, skipping (use --force to overwrite)")
        else:
            content = APP_COMPONENT_TEMPLATE.format(
                app_name=app_name,
                class_name=class_name,
            )
            app_path.write_text(content, encoding="utf-8")
            files_created.append(f"{module_name}.py")

        # Create __init__.py
        init_path = target_dir / "__init__.py"
        if init_path.exists() and not force:
            files_skipped.append("__init__.py")
            logger.warning("__init__.py already exists, skipping (use --force to overwrite)")
        else:
            content = INIT_TEMPLATE.format(
                app_name=app_name,
                module_name=module_name,
                class_name=class_name,
            )
            init_path.write_text(content, encoding="utf-8")
            files_created.append("__init__.py")

        # Create .awioc/manifest.yaml
        awioc_dir = target_dir / AWIOC_DIR
        awioc_dir.mkdir(exist_ok=True)
        manifest_path = awioc_dir / MANIFEST_FILENAME
        if manifest_path.exists() and not force:
            files_skipped.append(f"{AWIOC_DIR}/{MANIFEST_FILENAME}")
            logger.warning(f"{AWIOC_DIR}/{MANIFEST_FILENAME} already exists, skipping (use --force to overwrite)")
        else:
            manifest = {
                "manifest_version": "1.0",
                "name": app_name,
                "version": "1.0.0",
                "description": f"Main application for {app_name}",
                "components": [
                    {
                        "name": app_name,
                        "version": "1.0.0",
                        "description": f"Main application component for {app_name}",
                        "file": f"{module_name}.py",
                        "class": class_name,
                        "wire": True,
                    }
                ],
            }
            manifest_path.write_text(
                yaml.dump(manifest, default_flow_style=False, allow_unicode=True, sort_keys=False),
                encoding="utf-8"
            )
            files_created.append(f"{AWIOC_DIR}/{MANIFEST_FILENAME}")

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
        print(f"\nInitializing AWIOC project: {app_name}")
        print(f"Directory: {target_dir}")
        print(f"Module: {module_name}.py")
        print(f"Class: {class_name}")
        print()

        if files_created:
            print("Created files:")
            for f in files_created:
                print(f"  - {f}")

        if files_skipped:
            print(f"\nSkipped existing files: {', '.join(files_skipped)}")

        if files_created:
            print(f"\nProject initialized! Run 'awioc run -c {ioc_yaml_path}' to start.")
            return 0
        else:
            print("No files created. Directory already contains an AWIOC project.")
            return 0
