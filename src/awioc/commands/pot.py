"""Pot command - manages component repositories (pots).

A "pot" is a local repository where AWIOC components can be stored and
shared across multiple projects. Components in pots are referenced using
the @pot-name/component syntax in ioc.yaml.

Example:
    plugins:
      - @my-pot/http-server
      - @my-pot/auth-plugin
"""

import logging
import shutil
from pathlib import Path
from typing import Optional

import yaml

from .base import BaseCommand, CommandContext, register_command
from ..components.registry import as_component
from ..loader.module_loader import _load_module

logger = logging.getLogger(__name__)

# Default pot directory
DEFAULT_POT_DIR = Path.home() / ".awioc" / "pots"

# Pot manifest filename (compatible with standard manifest)
POT_MANIFEST_FILENAME = "pot.yaml"


def get_pot_dir() -> Path:
    """Get the pot directory, creating it if needed."""
    pot_dir = DEFAULT_POT_DIR
    pot_dir.mkdir(parents=True, exist_ok=True)
    return pot_dir


def get_pot_path(pot_name: str) -> Path:
    """Get the path to a specific pot."""
    return get_pot_dir() / pot_name


def load_pot_manifest(pot_path: Path) -> dict:
    """Load a pot's manifest file.

    The pot manifest format is compatible with the standard manifest.yaml format,
    using a list of component entries instead of a dict for consistency.
    """
    manifest_path = pot_path / POT_MANIFEST_FILENAME
    if not manifest_path.exists():
        return {
            "manifest_version": "1.0",
            "name": pot_path.name,
            "version": "1.0.0",
            "components": {},  # Legacy format uses dict for quick lookup by name
        }
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}

    # Ensure manifest_version exists
    if "manifest_version" not in manifest:
        manifest["manifest_version"] = "1.0"

    return manifest


def save_pot_manifest(pot_path: Path, manifest: dict) -> None:
    """Save a pot's manifest file."""
    manifest_path = pot_path / POT_MANIFEST_FILENAME
    manifest_path.write_text(
        yaml.dump(manifest, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8"
    )


def extract_component_metadata(component_path: Path) -> Optional[dict]:
    """Extract metadata from a component file/directory.

    Returns dict with name, version, description if found.
    """
    try:
        module = _load_module(component_path)

        # Check for module-level __metadata__
        if hasattr(module, "__metadata__"):
            metadata = module.__metadata__
            if isinstance(metadata, dict):
                return {
                    "name": metadata.get("name", component_path.stem),
                    "version": metadata.get("version", "1.0.0"),
                    "description": metadata.get("description", ""),
                }

        # Check for class with __metadata__ (class-based components)
        import inspect
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if hasattr(obj, "__metadata__"):
                metadata = obj.__metadata__
                if isinstance(metadata, dict):
                    return {
                        "name": metadata.get("name", component_path.stem),
                        "version": metadata.get("version", "1.0.0"),
                        "description": metadata.get("description", ""),
                        "class_name": name,
                    }

        return None
    except Exception as e:
        logger.debug(f"Could not extract metadata from {component_path}: {e}")
        return None


def resolve_pot_component(pot_ref: str) -> Optional[Path]:
    """Resolve a @pot-name/component reference to a file path.

    Args:
        pot_ref: Reference in format @pot-name/component-name

    Returns:
        Path to the component file/directory, or None if not found.
    """
    if not pot_ref.startswith("@"):
        return None

    # Parse @pot-name/component-name
    ref = pot_ref[1:]  # Remove @
    if "/" not in ref:
        logger.error(f"Invalid pot reference: {pot_ref} (expected @pot-name/component)")
        return None

    pot_name, component_name = ref.split("/", 1)
    pot_path = get_pot_path(pot_name)

    if not pot_path.exists():
        logger.error(f"Pot not found: {pot_name}")
        return None

    # Load manifest to find component
    manifest = load_pot_manifest(pot_path)
    components = manifest.get("components", {})

    if component_name not in components:
        logger.error(f"Component '{component_name}' not found in pot '{pot_name}'")
        return None

    component_info = components[component_name]
    component_file = pot_path / component_info.get("path", component_name)

    if not component_file.exists():
        logger.error(f"Component file not found: {component_file}")
        return None

    return component_file


@register_command("pot")
@as_component(
    name="Pot Command",
    version="1.0.0",
    description="Manage component repositories (pots)",
)
class PotCommand(BaseCommand):
    """Pot command for managing component repositories.

    A "pot" is a local repository where components can be stored and
    referenced by name across multiple projects using @pot-name/component syntax.
    """

    @property
    def name(self) -> str:
        return "pot"

    @property
    def description(self) -> str:
        return "Manage component repositories"

    @property
    def help_text(self) -> str:
        return """Manage component repositories (pots).

A "pot" is a local repository for storing and sharing AWIOC components.
Components in pots are referenced using @pot-name/component syntax.

Usage:
    awioc pot <subcommand> [options]

Subcommands:
    init <name>                    Create a new pot
    push <path> [--pot <name>]     Push a component to a pot
    update <pot>/<component> [source-path]  Update a component from source
    remove <pot>/<component>       Remove a component from a pot
    list [pot-name]                List pots or components in a pot
    info <pot>/<component>         Show component details
    delete <pot-name>              Delete an entire pot

Examples:
    awioc pot init my-components
    awioc pot push ./my_plugin.py --pot my-components
    awioc pot push ./http_server/ --pot my-components
    awioc pot update my-components/http-server ./http_server/
    awioc pot list my-components
    awioc pot remove my-components/http-server

In ioc.yaml, reference pot components like:
    plugins:
      - @my-components/http-server
      - @my-components/auth-plugin
"""

    async def execute(self, ctx: CommandContext) -> int:
        """Execute the pot command."""
        args = ctx.args.copy()

        if not args:
            return self._show_help()

        subcommand = args.pop(0).lower()

        if subcommand == "init":
            return await self._pot_init(args, ctx)
        elif subcommand == "push":
            return await self._pot_push(args, ctx)
        elif subcommand == "update":
            return await self._pot_update(args, ctx)
        elif subcommand == "remove":
            return await self._pot_remove(args, ctx)
        elif subcommand == "list":
            return await self._pot_list(args, ctx)
        elif subcommand == "info":
            return await self._pot_info(args, ctx)
        elif subcommand == "delete":
            return await self._pot_delete(args, ctx)
        elif subcommand == "help":
            return self._show_help()
        else:
            logger.error(f"Unknown subcommand: {subcommand}")
            return self._show_help()

    def _show_help(self) -> int:
        """Show pot command help."""
        print(self.help_text)
        return 0

    async def _pot_init(self, args: list[str], ctx: CommandContext) -> int:
        """Initialize a new pot."""
        if not args:
            logger.error("Usage: awioc pot init <name>")
            return 1

        pot_name = args.pop(0)

        # Validate pot name
        if not pot_name.replace("-", "").replace("_", "").isalnum():
            logger.error(f"Invalid pot name: {pot_name}")
            logger.error("Pot names must be alphanumeric with hyphens or underscores")
            return 1

        pot_path = get_pot_path(pot_name)

        if pot_path.exists():
            logger.error(f"Pot already exists: {pot_name}")
            return 1

        # Create pot structure
        pot_path.mkdir(parents=True)

        manifest = {
            "manifest_version": "1.0",
            "name": pot_name,
            "version": "1.0.0",
            "description": f"AWIOC component pot: {pot_name}",
            "components": {},
        }
        save_pot_manifest(pot_path, manifest)

        logger.info(f"Created pot: {pot_name}")
        logger.info(f"Location: {pot_path}")
        logger.info(f"\nPush components with: awioc pot push <path> --pot {pot_name}")
        return 0

    async def _pot_push(self, args: list[str], ctx: CommandContext) -> int:
        """Push a component to a pot."""
        if not args:
            logger.error("Usage: awioc pot push <component-path> [--pot <pot-name>]")
            return 1

        component_path = None
        pot_name = None
        component_name_override = None

        # Parse arguments
        while args:
            arg = args.pop(0)
            if arg == "--pot" and args:
                pot_name = args.pop(0)
            elif arg == "--name" and args:
                component_name_override = args.pop(0)
            elif not arg.startswith("-"):
                component_path = Path(arg)

        if component_path is None:
            logger.error("Component path required")
            return 1

        # Resolve component path
        if not component_path.is_absolute():
            component_path = Path.cwd() / component_path
        component_path = component_path.resolve()

        if not component_path.exists():
            logger.error(f"Component not found: {component_path}")
            return 1

        # Get list of available pots
        pot_dir = get_pot_dir()
        available_pots = [d.name for d in pot_dir.iterdir() if d.is_dir()]

        if not pot_name:
            if not available_pots:
                logger.error("No pots available. Create one with: awioc pot init <name>")
                return 1
            elif len(available_pots) == 1:
                pot_name = available_pots[0]
                logger.info(f"Using pot: {pot_name}")
            else:
                logger.error("Multiple pots available. Specify with --pot <name>")
                logger.info(f"Available pots: {', '.join(available_pots)}")
                return 1

        pot_path = get_pot_path(pot_name)
        if not pot_path.exists():
            logger.error(f"Pot not found: {pot_name}")
            return 1

        # Extract component metadata
        metadata = extract_component_metadata(component_path)
        if metadata is None:
            logger.error(f"Could not find component metadata in: {component_path}")
            logger.error("Ensure the component has __metadata__ (use @as_component decorator)")
            return 1

        component_name = component_name_override or metadata["name"]
        # Normalize component name for filesystem
        safe_name = component_name.lower().replace(" ", "-").replace("_", "-")

        # Load manifest
        manifest = load_pot_manifest(pot_path)
        components = manifest.setdefault("components", {})

        # Check if component already exists
        if safe_name in components:
            existing = components[safe_name]
            logger.warning(f"Component '{safe_name}' already exists (v{existing.get('version', '?')})")
            logger.info("Updating to new version...")

        # Determine destination path
        if component_path.is_file():
            dest_filename = f"{safe_name}.py"
            dest_path = pot_path / dest_filename
            # Copy file
            shutil.copy2(component_path, dest_path)
        else:
            # Directory - copy entire directory
            dest_path = pot_path / safe_name
            if dest_path.exists():
                shutil.rmtree(dest_path)
            shutil.copytree(component_path, dest_path)
            dest_filename = safe_name

        # Update manifest - use format compatible with manifest.yaml
        component_entry = {
            "name": metadata["name"],
            "version": metadata["version"],
            "file": dest_filename,  # Use 'file' for consistency with manifest.yaml
            "path": dest_filename,  # Keep 'path' for backwards compatibility
        }
        if metadata.get("description"):
            component_entry["description"] = metadata["description"]
        if metadata.get("class_name"):
            component_entry["class"] = metadata["class_name"]  # Use 'class' for consistency
            component_entry["class_name"] = metadata["class_name"]  # Backwards compat

        components[safe_name] = component_entry
        save_pot_manifest(pot_path, manifest)

        logger.info(f"Pushed: {metadata['name']} v{metadata['version']}")
        logger.info(f"To pot: {pot_name}")
        logger.info(f"\nUse in ioc.yaml as: @{pot_name}/{safe_name}")
        return 0

    async def _pot_update(self, args: list[str], ctx: CommandContext) -> int:
        """Update a component in a pot from a source path.

        Usage:
            awioc pot update <pot>/<component> [source-path]

        If source-path is provided, copies files from that path.
        If not provided, re-extracts metadata from the existing component files.
        """
        if not args:
            print("Usage: awioc pot update <pot-name>/<component-name> [source-path]")
            return 1

        ref = args.pop(0)
        source_path = Path(args.pop(0)) if args else None

        # Handle @pot/component syntax
        if ref.startswith("@"):
            ref = ref[1:]

        if "/" not in ref:
            print("Error: Invalid format. Use: pot-name/component-name")
            return 1

        pot_name, component_name = ref.split("/", 1)
        pot_path = get_pot_path(pot_name)

        if not pot_path.exists():
            print(f"Error: Pot not found: {pot_name}")
            return 1

        # Load manifest
        manifest = load_pot_manifest(pot_path)
        components = manifest.get("components", {})

        if component_name not in components:
            print(f"Error: Component not found: {component_name}")
            print(f"Available components: {', '.join(components.keys()) or '(none)'}")
            return 1

        component_info = components[component_name]
        old_version = component_info.get("version", "?")

        if source_path:
            # Update from external source
            if not source_path.is_absolute():
                source_path = Path.cwd() / source_path
            source_path = source_path.resolve()

            if not source_path.exists():
                print(f"Error: Source not found: {source_path}")
                return 1

            # Extract metadata from source
            metadata = extract_component_metadata(source_path)
            if metadata is None:
                print(f"Error: Could not find component metadata in: {source_path}")
                return 1

            # Get destination path from existing component info
            dest_filename = component_info.get("path", component_name)
            dest_path = pot_path / dest_filename

            # Copy files
            if source_path.is_file():
                shutil.copy2(source_path, dest_path)
            else:
                # Directory - remove old and copy new
                if dest_path.exists():
                    shutil.rmtree(dest_path)
                shutil.copytree(source_path, dest_path)

            # Update manifest entry
            component_info["name"] = metadata["name"]
            component_info["version"] = metadata["version"]
            if metadata.get("description"):
                component_info["description"] = metadata["description"]
            if metadata.get("class_name"):
                component_info["class"] = metadata["class_name"]
                component_info["class_name"] = metadata["class_name"]

            new_version = metadata["version"]
            print(f"Updated from source: {source_path}")

        else:
            # Re-extract metadata from existing files in pot
            component_file = pot_path / component_info.get("path", component_name)

            if not component_file.exists():
                print(f"Error: Component file not found: {component_file}")
                return 1

            metadata = extract_component_metadata(component_file)
            if metadata is None:
                print(f"Error: Could not extract metadata from: {component_file}")
                return 1

            # Update manifest entry with refreshed metadata
            component_info["name"] = metadata["name"]
            component_info["version"] = metadata["version"]
            if metadata.get("description"):
                component_info["description"] = metadata["description"]
            if metadata.get("class_name"):
                component_info["class"] = metadata["class_name"]
                component_info["class_name"] = metadata["class_name"]

            new_version = metadata["version"]
            print(f"Refreshed metadata from: {component_file}")

        # Save updated manifest
        components[component_name] = component_info
        save_pot_manifest(pot_path, manifest)

        print(f"\nUpdated: {component_info['name']}")
        print(f"  Version: {old_version} -> {new_version}")
        print(f"  Pot: {pot_name}")
        return 0

    async def _pot_remove(self, args: list[str], ctx: CommandContext) -> int:
        """Remove a component from a pot."""
        if not args:
            logger.error("Usage: awioc pot remove <pot-name>/<component-name>")
            return 1

        ref = args.pop(0)
        if "/" not in ref:
            logger.error("Invalid format. Use: pot-name/component-name")
            return 1

        pot_name, component_name = ref.split("/", 1)
        pot_path = get_pot_path(pot_name)

        if not pot_path.exists():
            logger.error(f"Pot not found: {pot_name}")
            return 1

        # Load manifest
        manifest = load_pot_manifest(pot_path)
        components = manifest.get("components", {})

        if component_name not in components:
            logger.error(f"Component not found: {component_name}")
            logger.info(f"Available components: {', '.join(components.keys()) or '(none)'}")
            return 1

        # Get component info and delete file
        component_info = components[component_name]
        component_file = pot_path / component_info.get("path", component_name)

        if component_file.exists():
            if component_file.is_dir():
                shutil.rmtree(component_file)
            else:
                component_file.unlink()

        # Update manifest
        del components[component_name]
        save_pot_manifest(pot_path, manifest)

        logger.info(f"Removed: {component_name} from {pot_name}")
        return 0

    async def _pot_list(self, args: list[str], ctx: CommandContext) -> int:
        """List pots or components in a pot."""
        pot_dir = get_pot_dir()

        # If pot name specified, list its components
        if args:
            pot_name = args.pop(0)
            pot_path = get_pot_path(pot_name)

            if not pot_path.exists():
                logger.error(f"Pot not found: {pot_name}")
                return 1

            manifest = load_pot_manifest(pot_path)
            components = manifest.get("components", {})

            print(f"\nPot: {pot_name} (v{manifest.get('version', '?')})")
            if manifest.get("description"):
                print(f"  {manifest['description']}")
            print(f"\nComponents ({len(components)}):")

            if not components:
                print("  (none)")
            else:
                for name, info in sorted(components.items()):
                    version = info.get("version", "?")
                    desc = info.get("description", "")
                    desc_text = f" - {desc}" if desc else ""
                    print(f"  {name} (v{version}){desc_text}")
                    print(f"    Usage: @{pot_name}/{name}")

            return 0

        # List all pots
        if not pot_dir.exists():
            print("No pots directory found.")
            print(f"Create a pot with: awioc pot init <name>")
            return 0

        pots = [d for d in pot_dir.iterdir() if d.is_dir()]

        if not pots:
            print("No pots found.")
            print(f"Create a pot with: awioc pot init <name>")
            return 0

        print(f"\nPots in {pot_dir}:\n")
        for pot_path in sorted(pots):
            manifest = load_pot_manifest(pot_path)
            version = manifest.get("version", "?")
            components = manifest.get("components", {})
            desc = manifest.get("description", "")

            print(f"  {pot_path.name} (v{version}) - {len(components)} component(s)")
            if desc:
                print(f"    {desc}")

        print(f"\nUse 'awioc pot list <pot-name>' to see components in a pot.")
        return 0

    async def _pot_info(self, args: list[str], ctx: CommandContext) -> int:
        """Show detailed info about a component."""
        if not args:
            logger.error("Usage: awioc pot info <pot-name>/<component-name>")
            return 1

        ref = args.pop(0)
        if "/" not in ref:
            logger.error("Invalid format. Use: pot-name/component-name")
            return 1

        pot_name, component_name = ref.split("/", 1)
        pot_path = get_pot_path(pot_name)

        if not pot_path.exists():
            logger.error(f"Pot not found: {pot_name}")
            return 1

        manifest = load_pot_manifest(pot_path)
        components = manifest.get("components", {})

        if component_name not in components:
            logger.error(f"Component not found: {component_name}")
            return 1

        info = components[component_name]

        print(f"\nComponent: {info.get('name', component_name)}")
        print(f"  Version: {info.get('version', '?')}")
        print(f"  Pot: {pot_name}")
        print(f"  Path: {info.get('path', component_name)}")
        if info.get("description"):
            print(f"  Description: {info['description']}")
        if info.get("class_name"):
            print(f"  Class: {info['class_name']}")
        print(f"\n  ioc.yaml reference: @{pot_name}/{component_name}")

        # Check if class reference is needed
        if info.get("class_name"):
            print(f"  Full reference: @{pot_name}/{component_name}:{info['class_name']}()")

        return 0

    async def _pot_delete(self, args: list[str], ctx: CommandContext) -> int:
        """Delete an entire pot."""
        if not args:
            logger.error("Usage: awioc pot delete <pot-name>")
            return 1

        pot_name = args.pop(0)
        pot_path = get_pot_path(pot_name)

        if not pot_path.exists():
            logger.error(f"Pot not found: {pot_name}")
            return 1

        # Confirm deletion
        manifest = load_pot_manifest(pot_path)
        component_count = len(manifest.get("components", {}))

        if component_count > 0:
            logger.warning(f"Pot '{pot_name}' contains {component_count} component(s)")

        # Delete pot
        shutil.rmtree(pot_path)
        logger.info(f"Deleted pot: {pot_name}")
        return 0
