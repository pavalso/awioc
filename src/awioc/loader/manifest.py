"""Manifest handling for AWIOC plugins.

This module provides utilities for loading and validating plugin manifests,
which describe component metadata without requiring Python code execution.
"""

import logging
from pathlib import Path
from typing import Optional, Union

import pydantic
import yaml

logger = logging.getLogger(__name__)

# Manifest directory and filename constants
AWIOC_DIR = ".awioc"
MANIFEST_FILENAME = "manifest.yaml"


def get_manifest_path(directory: Path) -> Path:
    """Get the path to manifest.yaml within a .awioc directory.

    Args:
        directory: Path to the directory containing .awioc/

    Returns:
        Path to directory/.awioc/manifest.yaml
    """
    return directory / AWIOC_DIR / MANIFEST_FILENAME


def has_awioc_dir(directory: Path) -> bool:
    """Check if a directory contains a .awioc subdirectory with manifest.yaml.

    Args:
        directory: Path to check

    Returns:
        True if directory/.awioc/manifest.yaml exists
    """
    return get_manifest_path(directory).exists()


class ComponentConfigRef(pydantic.BaseModel):
    """Reference to a Pydantic config model.

    Config models are referenced by their module path and class name,
    allowing them to be resolved at load time without executing Python.
    """

    model: str  # Format: "module_name:ClassName" or "relative/path:ClassName"
    prefix: Optional[str] = None  # Override for __prefix__

    model_config = pydantic.ConfigDict(extra="forbid")


class ComponentEntry(pydantic.BaseModel):
    """Single component entry in a manifest.

    Describes a component's metadata including its location, configuration,
    and dependencies.
    """

    name: str
    version: str = "0.0.0"
    description: str = ""
    file: str  # Relative path to Python file
    class_name: Optional[str] = pydantic.Field(default=None, alias="class")
    wire: bool = False
    wirings: list[str] = pydantic.Field(default_factory=list)
    requires: list[str] = pydantic.Field(default_factory=list)  # Component names
    config: Union[list[ComponentConfigRef], ComponentConfigRef, None] = None

    model_config = pydantic.ConfigDict(
        populate_by_name=True,
        extra="forbid",
    )

    @pydantic.field_validator("config", mode="before")
    @classmethod
    def normalize_config(cls, v):
        """Normalize config to always be a list or None."""
        if v is None:
            return None
        if isinstance(v, dict):
            return [v]
        if isinstance(v, list):
            return v
        return [{"model": v}] if isinstance(v, str) else v

    def get_config_list(self) -> list[ComponentConfigRef]:
        """Get config as a list, handling single item case."""
        if self.config is None:
            return []
        if isinstance(self.config, list):
            return self.config
        return [self.config]


class PluginManifest(pydantic.BaseModel):
    """Schema for manifest.yaml file.

    A manifest describes all components in a plugin directory,
    including their metadata, configuration, and dependencies.
    """

    manifest_version: str = "1.0"
    name: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    components: list[ComponentEntry] = pydantic.Field(default_factory=list)

    model_config = pydantic.ConfigDict(extra="forbid")

    def get_component(self, name: str) -> Optional[ComponentEntry]:
        """Get a component entry by name."""
        for component in self.components:
            if component.name == name:
                return component
        return None

    def get_component_by_file(
            self, file: str, class_name: Optional[str] = None
    ) -> Optional[ComponentEntry]:
        """Get a component entry by file path and optional class name."""
        for component in self.components:
            if component.file == file:
                if class_name is None or component.class_name == class_name:
                    return component
        return None


def load_manifest(directory: Path) -> PluginManifest:
    """Load and validate a manifest from a directory's .awioc folder.

    Args:
        directory: Path to the directory containing .awioc/manifest.yaml

    Returns:
        Validated PluginManifest object

    Raises:
        FileNotFoundError: If .awioc/manifest.yaml doesn't exist
        pydantic.ValidationError: If manifest is invalid
    """
    manifest_path = get_manifest_path(directory)

    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Manifest not found: {manifest_path}. "
            f"Expected manifest at: {directory / AWIOC_DIR / MANIFEST_FILENAME}"
        )

    logger.debug("Loading manifest from: %s", manifest_path)

    content = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    manifest = PluginManifest.model_validate(content)

    logger.debug(
        "Loaded manifest with %d component(s)", len(manifest.components)
    )

    return manifest


def find_manifest(path: Path) -> Optional[Path]:
    """Find the manifest.yaml file for a given path.

    Search order:
    1. If path is a directory (package component): path/.awioc/manifest.yaml
    2. Parent directory: path.parent/.awioc/manifest.yaml
       (for single-file components registered in parent's manifest)

    Args:
        path: Path to a file or directory

    Returns:
        Path to .awioc/manifest.yaml if found, None otherwise
    """
    path = path.resolve()

    # If path is a directory (package component), check for its own .awioc
    if path.is_dir():
        manifest_path = get_manifest_path(path)
        if manifest_path.exists():
            return manifest_path

    # For files or directories without own manifest, check parent's .awioc
    parent_manifest = get_manifest_path(path.parent)
    if parent_manifest.exists():
        return parent_manifest

    return None


def manifest_to_metadata(
        entry: ComponentEntry,
        manifest_path: Path,
) -> dict:
    """Convert a ComponentEntry to a component metadata dict.

    This creates a metadata dict compatible with the Component protocol's
    __metadata__ attribute.

    Args:
        entry: The component entry from the manifest
        manifest_path: Path to the manifest file (for resolving relative paths)

    Returns:
        Metadata dict compatible with ComponentMetadata TypedDict
    """
    metadata = {
        "name": entry.name,
        "version": entry.version,
        "description": entry.description,
        "wire": entry.wire,
        "wirings": set(entry.wirings) if entry.wirings else set(),
        "requires": None,  # Will be resolved later with actual component refs
        "config": None,  # Will be resolved when configs are loaded
        "_internals": None,
        "_manifest_path": str(manifest_path),
        "_requires_names": entry.requires,  # Store names for later resolution
        "_config_refs": [
            {"model": c.model, "prefix": c.prefix} for c in entry.get_config_list()
        ],
    }

    return metadata


def resolve_config_models(
        config_refs: list[dict],
        base_path: Path,
) -> set:
    """Resolve config model references to actual Pydantic model classes.

    Args:
        config_refs: List of config reference dicts with 'model' and 'prefix' keys
        base_path: Base path for resolving relative module paths

    Returns:
        Set of resolved Pydantic BaseModel classes
    """
    from pydantic import BaseModel

    resolved = set()

    for ref in config_refs:
        model_ref = ref["model"]
        prefix = ref.get("prefix")

        try:
            model_class = _resolve_model_reference(model_ref, base_path)

            if not isinstance(model_class, type) or not issubclass(
                    model_class, BaseModel
            ):
                logger.warning(
                    "Config reference '%s' is not a Pydantic BaseModel", model_ref
                )
                continue

            # Apply prefix override if specified
            if prefix is not None:
                model_class.__prefix__ = prefix

            resolved.add(model_class)
            logger.debug("Resolved config model: %s", model_ref)

        except Exception as e:
            logger.error("Failed to resolve config model '%s': %s", model_ref, e)

    return resolved


def _resolve_model_reference(reference: str, base_path: Path) -> type:
    """Resolve a model reference string to an actual class.

    Reference formats:
    - "module_name:ClassName" - relative to base_path
    - "./relative/path:ClassName" - explicit relative path
    - "package.module:ClassName" - absolute import

    Args:
        reference: The model reference string
        base_path: Base path for relative imports

    Returns:
        The resolved class

    Raises:
        ValueError: If reference format is invalid
        ImportError: If module cannot be imported
        AttributeError: If class doesn't exist in module
    """
    if ":" not in reference:
        raise ValueError(
            f"Invalid config model reference: '{reference}'. "
            "Expected format: 'module:ClassName'"
        )

    module_part, class_name = reference.rsplit(":", 1)

    # Handle relative paths
    if module_part.startswith("./") or module_part.startswith(".\\"):
        module_path = base_path / module_part[2:]
    else:
        module_path = base_path / module_part

    # Try to load as a file path first
    if module_path.with_suffix(".py").exists() or module_path.exists():
        from .module_loader import _load_module

        module = _load_module(module_path)
        return getattr(module, class_name)

    # Fall back to absolute import
    import importlib

    module = importlib.import_module(module_part)
    return getattr(module, class_name)
