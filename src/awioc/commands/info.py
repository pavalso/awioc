"""Info command - shows information about an AWIOC project."""

import logging
from pathlib import Path
from typing import Optional

import yaml

from .base import BaseCommand, CommandContext, register_command
from ..components.registry import as_component
from ..loader.manifest import find_manifest, load_manifest

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
  - Manifest information (when .awioc/manifest.yaml present)

Usage:
    awioc info [options]

Options:
    -c, --config-path   Path to ioc.yaml (default: ./ioc.yaml)
    --verbose           Show detailed component information
    --show-manifest     Display .awioc/manifest.yaml contents for directories
"""

    async def execute(self, ctx: CommandContext) -> int:
        """Execute the info command."""
        config_path = self._get_config_path(ctx)

        # Check for --show-manifest flag in args
        show_manifest = "--show-manifest" in ctx.args

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
                exists, manifest_info = self._check_path_with_manifest(plugin, config_dir)
                status = "[OK]" if exists else "[NOT FOUND]"
                manifest_tag = " [MANIFEST]" if manifest_info else ""
                print(f"  [{i}] {plugin} {status}{manifest_tag}")

                # Show manifest details if requested
                if show_manifest and manifest_info:
                    self._print_manifest_info(manifest_info, indent=6)
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

    def _print_manifest_info(self, manifest_path: Path, indent: int = 4) -> None:
        """Print manifest information."""
        prefix = " " * indent
        try:
            # manifest_path is .awioc/manifest.yaml, so parent.parent is the component directory
            component_dir = manifest_path.parent.parent
            manifest = load_manifest(component_dir)
            print(f"{prefix}Manifest: {manifest_path}")
            print(f"{prefix}Components ({len(manifest.components)}):")
            for comp in manifest.components:
                class_info = f" ({comp.class_name})" if comp.class_name else ""
                print(f"{prefix}  - {comp.name} v{comp.version}{class_info}")
        except Exception as e:
            print(f"{prefix}Manifest: {manifest_path} [ERROR: {e}]")

    def _check_path(self, path_str: str, base_dir: Path) -> bool:
        """Check if a component path exists."""
        exists, _ = self._check_path_with_manifest(path_str, base_dir)
        return exists

    def _check_path_with_manifest(
            self, path_str: str, base_dir: Path
    ) -> tuple[bool, Optional[Path]]:
        """Check if a component path exists and has a manifest.

        Returns:
            Tuple of (exists, manifest_path or None)
        """
        # Handle pot references
        if path_str.startswith("@"):
            return True, None  # Pot references handled separately

        # Handle class reference syntax (path:ClassName())
        if ":" in path_str and not path_str.startswith(":"):
            path_str = path_str.split(":")[0]
        elif path_str.startswith(":"):
            # Local module reference
            return True, None

        path = Path(path_str)
        if not path.is_absolute():
            path = base_dir / path

        if not path.exists():
            return False, None

        # Check for manifest
        manifest_path = find_manifest(path)
        return True, manifest_path

    def _get_config_path(self, ctx: CommandContext) -> Path:
        """Get the configuration file path."""
        if ctx.config_path:
            return Path(ctx.config_path)
        return Path.cwd() / "ioc.yaml"
