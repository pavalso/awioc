"""Remove command - removes plugins or libraries from an AWIOC project."""

import logging
from pathlib import Path

import yaml

from .base import BaseCommand, CommandContext, register_command
from ..components.registry import as_component

logger = logging.getLogger(__name__)


@register_command("remove")
@as_component(
    name="Remove Command",
    version="1.0.0",
    description="Remove plugins or libraries from an AWIOC project",
)
class RemoveCommand(BaseCommand):
    """Remove command that removes plugins or libraries from the configuration.

    Modifies the ioc.yaml file to remove existing plugins or libraries.
    """

    @property
    def name(self) -> str:
        return "remove"

    @property
    def description(self) -> str:
        return "Remove plugins or libraries from the project"

    @property
    def help_text(self) -> str:
        return """Remove plugins or libraries from an AWIOC project.

Usage:
    awioc remove plugin <path|index>
    awioc remove library <name>

Arguments:
    plugin              Remove a plugin component
    library             Remove a library component
    <path|index>        Plugin path or index (0-based) in the plugins list
    <name>              Library identifier

Options:
    -c, --config-path   Path to ioc.yaml (default: ./ioc.yaml)

Examples:
    awioc remove plugin plugins/my_plugin.py
    awioc remove plugin 0        # Remove first plugin
    awioc remove library db
"""

    async def execute(self, ctx: CommandContext) -> int:
        """Execute the remove command."""
        args = ctx.args.copy()

        if not args:
            logger.error("Usage: awioc remove <plugin|library> <path|name|index>")
            return 1

        component_type = args.pop(0).lower()

        if component_type == "plugin":
            return await self._remove_plugin(args, ctx)
        elif component_type == "library":
            return await self._remove_library(args, ctx)
        else:
            logger.error(f"Unknown component type: {component_type}")
            logger.error("Use 'plugin' or 'library'")
            return 1

    async def _remove_plugin(self, args: list[str], ctx: CommandContext) -> int:
        """Remove a plugin from the configuration."""
        if not args:
            logger.error("Usage: awioc remove plugin <path|index>")
            return 1

        identifier = args.pop(0)
        config_path = self._get_config_path(ctx)

        if not config_path.exists():
            logger.error(f"Configuration file not found: {config_path}")
            return 1

        # Load existing configuration
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

        plugins = config.get("components", {}).get("plugins", [])

        if not plugins:
            logger.error("No plugins configured")
            return 1

        # Try to interpret as index first
        removed_plugin = None
        try:
            index = int(identifier)
            if 0 <= index < len(plugins):
                removed_plugin = plugins.pop(index)
            else:
                logger.error(f"Plugin index out of range: {index} (0-{len(plugins) - 1})")
                return 1
        except ValueError:
            # Not an index, treat as path
            if identifier in plugins:
                plugins.remove(identifier)
                removed_plugin = identifier
            else:
                logger.error(f"Plugin not found: {identifier}")
                logger.info("Configured plugins:")
                for i, p in enumerate(plugins):
                    logger.info(f"  [{i}] {p}")
                return 1

        # Write back
        config["components"]["plugins"] = plugins
        config_path.write_text(
            yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8"
        )

        logger.info(f"Removed plugin: {removed_plugin}")
        return 0

    async def _remove_library(self, args: list[str], ctx: CommandContext) -> int:
        """Remove a library from the configuration."""
        if not args:
            logger.error("Usage: awioc remove library <name>")
            return 1

        lib_name = args.pop(0)
        config_path = self._get_config_path(ctx)

        if not config_path.exists():
            logger.error(f"Configuration file not found: {config_path}")
            return 1

        # Load existing configuration
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

        libraries = config.get("components", {}).get("libraries", {})

        if not libraries:
            logger.error("No libraries configured")
            return 1

        if lib_name not in libraries:
            logger.error(f"Library not found: {lib_name}")
            logger.info("Configured libraries:")
            for name, path in libraries.items():
                logger.info(f"  {name}: {path}")
            return 1

        # Remove the library
        removed_path = libraries.pop(lib_name)

        # Write back
        config["components"]["libraries"] = libraries
        config_path.write_text(
            yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8"
        )

        logger.info(f"Removed library '{lib_name}': {removed_path}")
        return 0

    def _get_config_path(self, ctx: CommandContext) -> Path:
        """Get the configuration file path."""
        if ctx.config_path:
            return Path(ctx.config_path)
        return Path.cwd() / "ioc.yaml"
