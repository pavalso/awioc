"""Generate command - generates .awioc/manifest.yaml from existing components."""

import ast
import logging
import shutil
from pathlib import Path
from typing import Optional

import yaml

from .base import BaseCommand, CommandContext, register_command
from ..components.registry import as_component
from ..loader.manifest import AWIOC_DIR, MANIFEST_FILENAME

logger = logging.getLogger(__name__)


def _extract_decorator_metadata(node: ast.ClassDef) -> Optional[dict]:
    """Extract metadata from @as_component decorator on a class."""
    for decorator in node.decorator_list:
        # Check for @as_component or @as_component(...)
        if isinstance(decorator, ast.Name) and decorator.id == "as_component":
            # Simple @as_component without args
            return {"name": node.name, "class": node.name}

        if isinstance(decorator, ast.Call):
            func = decorator.func
            if isinstance(func, ast.Name) and func.id == "as_component":
                # @as_component(...) with arguments
                metadata = {"class": node.name}

                # Parse keyword arguments
                for keyword in decorator.keywords:
                    key = keyword.arg
                    value = _ast_literal_eval(keyword.value)
                    if value is not None:
                        metadata[key] = value

                # Set default name if not provided
                if "name" not in metadata:
                    metadata["name"] = node.name

                return metadata

    return None


def _extract_module_metadata(tree: ast.Module) -> Optional[dict]:
    """Extract __metadata__ dict from module-level assignment."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__metadata__":
                    if isinstance(node.value, ast.Dict):
                        metadata = {}
                        for key, value in zip(node.value.keys, node.value.values):
                            if isinstance(key, ast.Constant):
                                val = _ast_literal_eval(value)
                                if val is not None:
                                    metadata[str(key.value)] = val
                        return metadata
    return None


def _ast_literal_eval(node: ast.expr) -> Optional[any]:
    """Safely evaluate an AST node to a Python literal."""
    try:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Str):  # Python 3.7 compatibility
            return node.s
        if isinstance(node, ast.Num):  # Python 3.7 compatibility
            return node.n
        if isinstance(node, ast.NameConstant):  # Python 3.7 compatibility
            return node.value
        if isinstance(node, ast.List):
            return [_ast_literal_eval(elt) for elt in node.elts]
        if isinstance(node, ast.Set):
            return {_ast_literal_eval(elt) for elt in node.elts}
        if isinstance(node, ast.Dict):
            return {
                _ast_literal_eval(k): _ast_literal_eval(v)
                for k, v in zip(node.keys, node.values)
                if k is not None
            }
        if isinstance(node, ast.Name):
            # Reference to a class or variable - return as string reference
            return f":{node.id}"
        if isinstance(node, ast.Attribute):
            # Attribute access like module.Class
            parts = []
            current = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            parts.reverse()
            return ":".join(parts)
    except Exception:
        pass
    return None


def _scan_python_file(file_path: Path) -> list[dict]:
    """Scan a Python file for components and extract their metadata."""
    components = []

    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
    except Exception as e:
        logger.warning("Failed to parse %s: %s", file_path, e)
        return components

    # Check for module-level __metadata__
    module_meta = _extract_module_metadata(tree)
    if module_meta:
        entry = {
            "name": module_meta.get("name", file_path.stem),
            "version": module_meta.get("version", "0.0.0"),
            "description": module_meta.get("description", ""),
            "file": file_path.name,
            "wire": module_meta.get("wire", False),
        }

        # Handle config
        config_value = module_meta.get("config")
        if config_value:
            entry["config"] = _format_config_ref(config_value, file_path)

        components.append(entry)
        return components  # Module-level metadata takes precedence

    # Scan for class-based components
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            meta = _extract_decorator_metadata(node)
            if meta:
                entry = {
                    "name": meta.get("name", node.name),
                    "version": meta.get("version", "0.0.0"),
                    "description": meta.get("description", ""),
                    "file": file_path.name,
                    "class": meta.get("class", node.name),
                    "wire": meta.get("wire", False),
                }

                # Handle config
                config_value = meta.get("config")
                if config_value:
                    entry["config"] = _format_config_ref(config_value, file_path)

                components.append(entry)

    return components


def _format_config_ref(config_value: any, file_path: Path) -> list[dict]:
    """Format config references for manifest."""
    configs = []

    if isinstance(config_value, str) and config_value.startswith(":"):
        # Single class reference
        class_name = config_value[1:]
        configs.append({"model": f"{file_path.stem}:{class_name}"})
    elif isinstance(config_value, (list, set)):
        for item in config_value:
            if isinstance(item, str) and item.startswith(":"):
                class_name = item[1:]
                configs.append({"model": f"{file_path.stem}:{class_name}"})

    return configs if configs else None


def _generate_manifest(directory: Path) -> dict:
    """Generate manifest content for a directory."""
    manifest = {
        "manifest_version": "1.0",
        "name": directory.name,
        "version": "1.0.0",
        "description": f"Auto-generated manifest for {directory.name}",
        "components": [],
    }

    # Scan all Python files
    py_files = sorted(directory.glob("*.py"))

    for py_file in py_files:
        if py_file.name.startswith("_"):
            continue  # Skip __init__.py and private files

        components = _scan_python_file(py_file)
        manifest["components"].extend(components)

    return manifest


@register_command("generate")
@as_component(
    name="Generate Command",
    version="1.0.0",
    description="Generate .awioc/manifest.yaml from existing components",
)
class GenerateCommand(BaseCommand):
    """Generate command that creates .awioc/manifest.yaml from decorated components.

    Scans Python files for @as_component decorators and __metadata__ dicts,
    then generates a manifest.yaml file in the .awioc directory.
    """

    @property
    def name(self) -> str:
        return "generate"

    @property
    def description(self) -> str:
        return "Generate .awioc/manifest.yaml from existing components"

    @property
    def help_text(self) -> str:
        return """Generate .awioc/manifest.yaml from existing components.

Scans Python files for @as_component decorators and __metadata__ dicts,
then generates a manifest.yaml file in the .awioc directory.

Usage:
    awioc generate manifest [path] [options]
    awioc generate migrate [path] [options]

Subcommands:
    manifest            Generate a .awioc/manifest.yaml file
    migrate             Migrate existing manifest.yaml to .awioc/manifest.yaml

Arguments:
    [path]              Directory to scan/migrate (default: current directory)

Options:
    -o, --output PATH   Output file path (default: <path>/.awioc/manifest.yaml)
    --dry-run           Preview without writing
    --force             Overwrite existing manifest

Examples:
    awioc generate manifest plugins/
    awioc generate manifest plugins/ --dry-run
    awioc generate manifest plugins/ --force
    awioc generate migrate plugins/
"""

    async def execute(self, ctx: CommandContext) -> int:
        """Execute the generate command."""
        args = ctx.args.copy()

        if not args:
            print(self.help_text)
            return 1

        subcommand = args.pop(0).lower()

        if subcommand == "manifest":
            return await self._generate_manifest(args, ctx)
        elif subcommand == "migrate":
            return await self._migrate_manifest(args, ctx)
        elif subcommand == "help":
            print(self.help_text)
            return 0
        else:
            logger.error(f"Unknown subcommand: {subcommand}")
            print(self.help_text)
            return 1

    async def _generate_manifest(self, args: list[str], ctx: CommandContext) -> int:
        """Generate .awioc/manifest.yaml for a directory."""
        # Parse arguments
        target_dir = Path.cwd()
        output_path = None
        dry_run = False
        force = False

        while args:
            arg = args.pop(0)
            if arg in ("-o", "--output") and args:
                output_path = Path(args.pop(0))
            elif arg == "--dry-run":
                dry_run = True
            elif arg == "--force":
                force = True
            elif not arg.startswith("-"):
                target_dir = Path(arg)

        # Resolve paths
        target_dir = target_dir.resolve()

        if not target_dir.exists():
            logger.error(f"Directory not found: {target_dir}")
            return 1

        if not target_dir.is_dir():
            logger.error(f"Not a directory: {target_dir}")
            return 1

        # Default output path is .awioc/manifest.yaml
        if output_path is None:
            awioc_dir = target_dir / AWIOC_DIR
            output_path = awioc_dir / MANIFEST_FILENAME

        # Check if manifest already exists
        if output_path.exists() and not force and not dry_run:
            logger.error(f"Manifest already exists: {output_path}")
            logger.error("Use --force to overwrite or --dry-run to preview")
            return 1

        # Generate manifest
        print(f"Scanning {target_dir}...")
        manifest = _generate_manifest(target_dir)

        if not manifest["components"]:
            logger.warning("No components found in directory")
            return 0

        # Format output
        yaml_content = yaml.dump(
            manifest,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

        print(f"\nFound {len(manifest['components'])} component(s):")
        for comp in manifest["components"]:
            class_info = f" ({comp['class']})" if comp.get("class") else ""
            print(f"  - {comp['name']} v{comp['version']}{class_info}")

        if dry_run:
            print(f"\n--- Preview of {output_path} ---\n")
            print(yaml_content)
            print("--- End preview (--dry-run, no file written) ---")
        else:
            # Create .awioc directory if needed
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(yaml_content, encoding="utf-8")
            print(f"\nGenerated: {output_path}")

        return 0

    async def _migrate_manifest(self, args: list[str], ctx: CommandContext) -> int:
        """Migrate existing manifest.yaml to .awioc/manifest.yaml."""
        # Parse arguments
        target_dir = Path.cwd()
        force = False

        while args:
            arg = args.pop(0)
            if arg == "--force":
                force = True
            elif not arg.startswith("-"):
                target_dir = Path(arg)

        # Resolve paths
        target_dir = target_dir.resolve()

        if not target_dir.exists():
            logger.error(f"Directory not found: {target_dir}")
            return 1

        if not target_dir.is_dir():
            logger.error(f"Not a directory: {target_dir}")
            return 1

        # Check for old manifest
        old_manifest = target_dir / MANIFEST_FILENAME
        if not old_manifest.exists():
            logger.error(f"No manifest.yaml found in {target_dir}")
            return 1

        # Set up new paths
        awioc_dir = target_dir / AWIOC_DIR
        new_manifest = awioc_dir / MANIFEST_FILENAME

        # Check if new manifest already exists
        if new_manifest.exists() and not force:
            logger.error(f"New manifest already exists: {new_manifest}")
            logger.error("Use --force to overwrite")
            return 1

        # Create .awioc directory
        awioc_dir.mkdir(exist_ok=True)

        # Move manifest
        if new_manifest.exists():
            new_manifest.unlink()
        shutil.move(str(old_manifest), str(new_manifest))

        print(f"Migrated: {old_manifest} -> {new_manifest}")
        return 0
