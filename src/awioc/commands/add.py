"""Add command - adds plugins or libraries to an AWIOC project."""

import logging
from pathlib import Path

import yaml

from .base import BaseCommand, CommandContext, register_command
from ..components.registry import as_component

logger = logging.getLogger(__name__)


@register_command("add")
@as_component(
    name="Add Command",
    version="1.0.0",
    description="Add plugins or libraries to an AWIOC project",
)
class AddCommand(BaseCommand):
    """Add command that adds plugins or libraries to the configuration.

    Modifies the ioc.yaml file to include new plugins or libraries.
    """

    @property
    def name(self) -> str:
        return "add"

    @property
    def description(self) -> str:
        return "Add plugins or libraries to the project"

    @property
    def help_text(self) -> str:
        return """Add plugins or libraries to an AWIOC project.

Usage:
    awioc add plugin <path> [options]
    awioc add library <name> <path> [options]

Arguments:
    plugin              Add a plugin component
    library             Add a library component
    <path>              Path to the component file or directory
    <name>              Library identifier (for library type)

Options:
    -c, --config-path   Path to ioc.yaml (default: ./ioc.yaml)

Examples:
    awioc add plugin plugins/my_plugin.py
    awioc add plugin plugins/my_module:MyClass()
    awioc add library db plugins/database.py
"""

    async def execute(self, ctx: CommandContext) -> int:
        """Execute the add command."""
        args = ctx.args.copy()

        if not args:
            logger.error("Usage: awioc add <plugin|library> <path> [options]")
            return 1

        component_type = args.pop(0).lower()

        if component_type == "plugin":
            return await self._add_plugin(args, ctx)
        elif component_type == "library":
            return await self._add_library(args, ctx)
        else:
            logger.error(f"Unknown component type: {component_type}")
            logger.error("Use 'plugin' or 'library'")
            return 1

    async def _add_plugin(self, args: list[str], ctx: CommandContext) -> int:
        """Add a plugin to the configuration."""
        if not args:
            logger.error("Usage: awioc add plugin <path>")
            return 1

        plugin_path = args.pop(0)
        config_path = self._get_config_path(ctx)

        if not config_path.exists():
            logger.error(f"Configuration file not found: {config_path}")
            logger.error("Run 'awioc init' first or specify --config-path")
            return 1

        # Load existing configuration
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

        # Ensure components.plugins exists
        if "components" not in config:
            config["components"] = {}
        if "plugins" not in config["components"]:
            config["components"]["plugins"] = []

        plugins = config["components"]["plugins"]

        # Check if plugin already exists
        if plugin_path in plugins:
            logger.warning(f"Plugin already configured: {plugin_path}")
            return 0

        # Add the plugin
        plugins.append(plugin_path)

        # Write back
        config_path.write_text(
            yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8"
        )

        logger.info(f"Added plugin: {plugin_path}")
        return 0

    async def _add_library(self, args: list[str], ctx: CommandContext) -> int:
        """Add a library to the configuration."""
        if len(args) < 2:
            logger.error("Usage: awioc add library <name> <path>")
            return 1

        lib_name = args.pop(0)
        lib_path = args.pop(0)
        config_path = self._get_config_path(ctx)

        if not config_path.exists():
            logger.error(f"Configuration file not found: {config_path}")
            logger.error("Run 'awioc init' first or specify --config-path")
            return 1

        # Load existing configuration
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

        # Ensure components.libraries exists
        if "components" not in config:
            config["components"] = {}
        if "libraries" not in config["components"]:
            config["components"]["libraries"] = {}

        libraries = config["components"]["libraries"]

        # Check if library already exists
        if lib_name in libraries:
            logger.warning(f"Library '{lib_name}' already configured, updating path")

        # Add/update the library
        libraries[lib_name] = lib_path

        # Write back
        config_path.write_text(
            yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8"
        )

        logger.info(f"Added library '{lib_name}': {lib_path}")
        return 0

    def _get_config_path(self, ctx: CommandContext) -> Path:
        """Get the configuration file path."""
        if ctx.config_path:
            return Path(ctx.config_path)
        return Path.cwd() / "ioc.yaml"
