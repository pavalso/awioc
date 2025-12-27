"""Info command - shows information about an AWIOC project."""

import logging
from pathlib import Path

import yaml

from .base import BaseCommand, CommandContext, register_command
from ..components.registry import as_component

logger = logging.getLogger(__name__)


@register_command("info")
@as_component(
    name="Info Command",
    version="1.0.0",
    description="Show information about an AWIOC project",
)
class InfoCommand(BaseCommand):
    """Info command that displays project information.

    Shows details about the configured components, plugins, and libraries.
    """

    @property
    def name(self) -> str:
        return "info"

    @property
    def description(self) -> str:
        return "Show project information"

    @property
    def help_text(self) -> str:
        return """Show information about an AWIOC project.

Displays the project configuration including:
  - Application component
  - Configured libraries
  - Configured plugins
  - Environment files

Usage:
    awioc info [options]

Options:
    -c, --config-path   Path to ioc.yaml (default: ./ioc.yaml)
    --verbose           Show detailed component information
"""

    async def execute(self, ctx: CommandContext) -> int:
        """Execute the info command."""
        config_path = self._get_config_path(ctx)

        if not config_path.exists():
            logger.error(f"Configuration file not found: {config_path}")
            logger.info("Run 'awioc init' to create a new project")
            return 1

        # Load configuration
        try:
            config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing configuration: {e}")
            return 1

        # Display project info
        print(f"\n{'=' * 60}")
        print(f" AWIOC Project Information")
        print(f"{'=' * 60}")
        print(f"\nConfiguration: {config_path}")

        # Check for environment files
        config_dir = config_path.parent
        env_files = []
        if (config_dir / ".env").exists():
            env_files.append(".env")
        for f in config_dir.glob(".*.env"):
            env_files.append(f.name)
        if env_files:
            print(f"Environment files: {', '.join(env_files)}")

        # Application component
        components = config.get("components", {})
        app = components.get("app", "Not configured")
        print(f"\n--- Application ---")
        print(f"  App: {app}")

        # Libraries
        libraries = components.get("libraries", {})
        print(f"\n--- Libraries ({len(libraries)}) ---")
        if libraries:
            for name, path in libraries.items():
                exists = self._check_path(path, config_dir)
                status = "[OK]" if exists else "[NOT FOUND]"
                print(f"  {name}: {path} {status}")
        else:
            print("  (none)")

        # Plugins
        plugins = components.get("plugins", [])
        print(f"\n--- Plugins ({len(plugins)}) ---")
        if plugins:
            for i, plugin in enumerate(plugins):
                exists = self._check_path(plugin, config_dir)
                status = "[OK]" if exists else "[NOT FOUND]"
                print(f"  [{i}] {plugin} {status}")
        else:
            print("  (none)")

        # Other configuration sections
        other_sections = [k for k in config.keys() if k != "components"]
        if other_sections and ctx.verbose > 0:
            print(f"\n--- Configuration Sections ---")
            for section in other_sections:
                print(f"  {section}:")
                section_config = config[section]
                if isinstance(section_config, dict):
                    for key, value in section_config.items():
                        print(f"    {key}: {value}")
                else:
                    print(f"    {section_config}")

        print(f"\n{'=' * 60}\n")
        return 0

    def _check_path(self, path_str: str, base_dir: Path) -> bool:
        """Check if a component path exists."""
        # Handle class reference syntax (path:ClassName())
        if ":" in path_str and not path_str.startswith(":"):
            path_str = path_str.split(":")[0]
        elif path_str.startswith(":"):
            # Local module reference
            return True

        path = Path(path_str)
        if not path.is_absolute():
            path = base_dir / path

        return path.exists()

    def _get_config_path(self, ctx: CommandContext) -> Path:
        """Get the configuration file path."""
        if ctx.config_path:
            return Path(ctx.config_path)
        return Path.cwd() / "ioc.yaml"
