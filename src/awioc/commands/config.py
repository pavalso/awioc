"""Config command - manages AWIOC project configuration."""

import logging
from pathlib import Path
from typing import Any

import yaml

from .base import BaseCommand, CommandContext, register_command
from ..components.registry import as_component

logger = logging.getLogger(__name__)


@register_command("config")
@as_component(
    name="Config Command",
    version="1.0.0",
    description="Manage AWIOC project configuration",
)
class ConfigCommand(BaseCommand):
    """Config command that manages project configuration.

    Allows viewing, getting, and setting configuration values in ioc.yaml.
    """

    @property
    def name(self) -> str:
        return "config"

    @property
    def description(self) -> str:
        return "Manage project configuration"

    @property
    def help_text(self) -> str:
        return """Manage AWIOC project configuration.

Usage:
    awioc config                     Show all configuration
    awioc config get <key>           Get a configuration value
    awioc config set <key> <value>   Set a configuration value
    awioc config unset <key>         Remove a configuration value

Arguments:
    <key>       Dot-separated path to configuration key (e.g., server.port)
    <value>     Value to set (strings, numbers, booleans, JSON supported)

Options:
    -c, --config-path   Path to ioc.yaml (default: ./ioc.yaml)

Examples:
    awioc config get server.port
    awioc config set server.port 8080
    awioc config set server.host "0.0.0.0"
    awioc config set features.enabled true
    awioc config unset server.debug
"""

    async def execute(self, ctx: CommandContext) -> int:
        """Execute the config command."""
        args = ctx.args.copy()

        if not args:
            return await self._show_config(ctx)

        subcommand = args.pop(0).lower()

        if subcommand == "get":
            return await self._get_config(args, ctx)
        elif subcommand == "set":
            return await self._set_config(args, ctx)
        elif subcommand == "unset":
            return await self._unset_config(args, ctx)
        else:
            logger.error(f"Unknown subcommand: {subcommand}")
            logger.error("Use 'get', 'set', or 'unset'")
            return 1

    async def _show_config(self, ctx: CommandContext) -> int:
        """Show all configuration."""
        config_path = self._get_config_path(ctx)

        if not config_path.exists():
            logger.error(f"Configuration file not found: {config_path}")
            return 1

        try:
            config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing configuration: {e}")
            return 1

        # Pretty print the configuration
        print(yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False))
        return 0

    async def _get_config(self, args: list[str], ctx: CommandContext) -> int:
        """Get a configuration value."""
        if not args:
            logger.error("Usage: awioc config get <key>")
            return 1

        key = args.pop(0)
        config_path = self._get_config_path(ctx)

        if not config_path.exists():
            logger.error(f"Configuration file not found: {config_path}")
            return 1

        try:
            config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing configuration: {e}")
            return 1

        # Navigate to the key
        value = self._get_nested(config, key)

        if value is None:
            logger.error(f"Key not found: {key}")
            return 1

        if isinstance(value, dict):
            print(yaml.dump(value, default_flow_style=False, allow_unicode=True))
        else:
            print(value)

        return 0

    async def _set_config(self, args: list[str], ctx: CommandContext) -> int:
        """Set a configuration value."""
        if len(args) < 2:
            logger.error("Usage: awioc config set <key> <value>")
            return 1

        key = args.pop(0)
        value_str = " ".join(args)  # Join remaining args for values with spaces
        config_path = self._get_config_path(ctx)

        if not config_path.exists():
            logger.error(f"Configuration file not found: {config_path}")
            return 1

        try:
            config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing configuration: {e}")
            return 1

        # Parse the value
        value = self._parse_value(value_str)

        # Set the value
        self._set_nested(config, key, value)

        # Write back
        config_path.write_text(
            yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8"
        )

        logger.info(f"Set {key} = {value}")
        return 0

    async def _unset_config(self, args: list[str], ctx: CommandContext) -> int:
        """Remove a configuration value."""
        if not args:
            logger.error("Usage: awioc config unset <key>")
            return 1

        key = args.pop(0)
        config_path = self._get_config_path(ctx)

        if not config_path.exists():
            logger.error(f"Configuration file not found: {config_path}")
            return 1

        try:
            config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing configuration: {e}")
            return 1

        # Remove the value
        if not self._unset_nested(config, key):
            logger.error(f"Key not found: {key}")
            return 1

        # Write back
        config_path.write_text(
            yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8"
        )

        logger.info(f"Removed: {key}")
        return 0

    def _get_nested(self, obj: dict, key: str) -> Any:
        """Get a nested value by dot-separated key."""
        parts = key.split(".")
        current = obj
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current

    def _set_nested(self, obj: dict, key: str, value: Any) -> None:
        """Set a nested value by dot-separated key."""
        parts = key.split(".")
        current = obj
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value

    def _unset_nested(self, obj: dict, key: str) -> bool:
        """Remove a nested value by dot-separated key. Returns True if removed."""
        parts = key.split(".")
        current = obj
        for part in parts[:-1]:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return False
        if isinstance(current, dict) and parts[-1] in current:
            del current[parts[-1]]
            return True
        return False

    def _parse_value(self, value_str: str) -> Any:
        """Parse a string value into the appropriate type."""
        import json

        # Strip quotes if present
        value_str = value_str.strip()
        if (value_str.startswith('"') and value_str.endswith('"')) or \
                (value_str.startswith("'") and value_str.endswith("'")):
            return value_str[1:-1]

        # Try to parse as JSON (handles booleans, numbers, arrays, objects)
        try:
            return json.loads(value_str)
        except json.JSONDecodeError:
            pass

        # Boolean detection
        if value_str.lower() in ("true", "yes", "on"):
            return True
        if value_str.lower() in ("false", "no", "off"):
            return False

        # Try as number
        try:
            if "." in value_str:
                return float(value_str)
            return int(value_str)
        except ValueError:
            pass

        # Return as string
        return value_str

    def _get_config_path(self, ctx: CommandContext) -> Path:
        """Get the configuration file path."""
        if ctx.config_path:
            return Path(ctx.config_path)
        return Path.cwd() / "ioc.yaml"
