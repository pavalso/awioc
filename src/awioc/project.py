"""AWIOC Project API.

This module provides a high-level API for working with AWIOC projects,
including manifest reading, modification, and component compilation.

Example usage:
    from awioc import is_awioc_project, open_project, create_project

    # Check if a path is an AWIOC project
    if is_awioc_project("./my_plugin"):
        project = open_project("./my_plugin")
        print(f"Project: {project.name} v{project.version}")

        # List components
        for comp in project.components:
            print(f"  - {comp.name}")

        # Compile and use components
        components = project.compile_components()

    # Create a new project
    project = create_project("./new_plugin", name="My Plugin", version="1.0.0")
    project.save()
"""

import logging
from pathlib import Path
from typing import Optional, Union, Iterator

import yaml

from .loader.manifest import (
    AWIOC_DIR,
    MANIFEST_FILENAME,
    PluginManifest,
    ComponentEntry,
    ComponentConfigRef,
    get_manifest_path,
    has_awioc_dir,
    load_manifest as _load_manifest,
)

logger = logging.getLogger(__name__)

__all__ = [
    "AWIOCProject",
    "is_awioc_project",
    "open_project",
    "create_project",
]


def is_awioc_project(path: Union[str, Path]) -> bool:
    """Check if a path is an AWIOC project (has .awioc/manifest.yaml).

    Args:
        path: Path to check (file or directory)

    Returns:
        True if the path contains a valid AWIOC project structure

    Example:
        >>> is_awioc_project("./my_plugin")
        True
        >>> is_awioc_project("./random_folder")
        False
    """
    path = Path(path).resolve()

    if path.is_file():
        # For files, check parent directory
        path = path.parent

    return has_awioc_dir(path)


def open_project(path: Union[str, Path]) -> "AWIOCProject":
    """Open an existing AWIOC project.

    Args:
        path: Path to the project directory (or a file within it)

    Returns:
        AWIOCProject instance for working with the project

    Raises:
        FileNotFoundError: If the path doesn't contain a valid AWIOC project

    Example:
        >>> project = open_project("./my_plugin")
        >>> print(project.name)
        "My Plugin"
    """
    path = Path(path).resolve()

    if path.is_file():
        path = path.parent

    if not has_awioc_dir(path):
        raise FileNotFoundError(
            f"Not an AWIOC project: {path}. "
            f"Missing {AWIOC_DIR}/{MANIFEST_FILENAME}"
        )

    return AWIOCProject(path)


def create_project(
        path: Union[str, Path],
        name: Optional[str] = None,
        version: str = "1.0.0",
        description: str = "",
        overwrite: bool = False,
) -> "AWIOCProject":
    """Create a new AWIOC project.

    Creates the .awioc directory and manifest.yaml file.

    Args:
        path: Path where to create the project
        name: Project name (defaults to directory name)
        version: Project version
        description: Project description
        overwrite: If True, overwrite existing manifest

    Returns:
        AWIOCProject instance for the new project

    Raises:
        FileExistsError: If project already exists and overwrite=False

    Example:
        >>> project = create_project("./my_plugin", name="My Plugin")
        >>> project.save()
    """
    path = Path(path).resolve()

    # Create directory if it doesn't exist
    path.mkdir(parents=True, exist_ok=True)

    # Check for existing project
    if has_awioc_dir(path) and not overwrite:
        raise FileExistsError(
            f"AWIOC project already exists at {path}. "
            "Use overwrite=True to replace it."
        )

    # Create .awioc directory
    awioc_dir = path / AWIOC_DIR
    awioc_dir.mkdir(exist_ok=True)

    # Create manifest
    manifest = PluginManifest(
        manifest_version="1.0",
        name=name or path.name,
        version=version,
        description=description,
        components=[],
    )

    project = AWIOCProject(path, manifest=manifest)
    project.save()

    logger.info("Created AWIOC project at %s", path)
    return project


class AWIOCProject:
    """Represents an AWIOC project with manifest management capabilities.

    This class provides a high-level interface for:
    - Reading project and component metadata
    - Modifying components in the manifest
    - Saving changes back to disk
    - Compiling components for use

    Attributes:
        path: The project root directory
        manifest: The underlying PluginManifest model

    Example:
        >>> project = open_project("./my_plugin")
        >>> print(f"{project.name} v{project.version}")
        >>> for comp in project.components:
        ...     print(f"  Component: {comp.name}")
    """

    def __init__(
            self,
            path: Path,
            manifest: Optional[PluginManifest] = None,
    ):
        """Initialize an AWIOCProject.

        Args:
            path: Path to the project directory
            manifest: Optional pre-loaded manifest (loads from disk if None)
        """
        self._path = path.resolve()
        self._manifest = manifest or _load_manifest(path)
        self._dirty = False  # Track unsaved changes

    # -------------------------------------------------------------------------
    # Properties - Project metadata
    # -------------------------------------------------------------------------

    @property
    def path(self) -> Path:
        """The project root directory."""
        return self._path

    @property
    def manifest_path(self) -> Path:
        """Path to the manifest.yaml file."""
        return get_manifest_path(self._path)

    @property
    def manifest(self) -> PluginManifest:
        """The underlying PluginManifest model."""
        return self._manifest

    @property
    def name(self) -> str:
        """Project name."""
        return self._manifest.name or self._path.name

    @name.setter
    def name(self, value: str):
        """Set project name."""
        self._manifest.name = value
        self._dirty = True

    @property
    def version(self) -> Optional[str]:
        """Project version."""
        return self._manifest.version

    @version.setter
    def version(self, value: str):
        """Set project version."""
        self._manifest.version = value
        self._dirty = True

    @property
    def description(self) -> Optional[str]:
        """Project description."""
        return self._manifest.description

    @description.setter
    def description(self, value: str):
        """Set project description."""
        self._manifest.description = value
        self._dirty = True

    @property
    def manifest_version(self) -> str:
        """Manifest schema version."""
        return self._manifest.manifest_version

    @property
    def is_dirty(self) -> bool:
        """True if there are unsaved changes."""
        return self._dirty

    # -------------------------------------------------------------------------
    # Component access
    # -------------------------------------------------------------------------

    @property
    def components(self) -> list[ComponentEntry]:
        """List of all components in the project."""
        return self._manifest.components

    def __len__(self) -> int:
        """Number of components in the project."""
        return len(self._manifest.components)

    def __iter__(self) -> Iterator[ComponentEntry]:
        """Iterate over components."""
        return iter(self._manifest.components)

    def __contains__(self, name: str) -> bool:
        """Check if a component exists by name."""
        return self.get_component(name) is not None

    def get_component(self, name: str) -> Optional[ComponentEntry]:
        """Get a component by name.

        Args:
            name: Component name to find

        Returns:
            ComponentEntry if found, None otherwise
        """
        return self._manifest.get_component(name)

    def get_component_by_class(
            self,
            class_name: str,
            file: Optional[str] = None,
    ) -> Optional[ComponentEntry]:
        """Get a component by class name.

        Args:
            class_name: The class name to find
            file: Optional file path to narrow search

        Returns:
            ComponentEntry if found, None otherwise
        """
        for comp in self._manifest.components:
            if comp.class_name == class_name:
                if file is None or comp.file == file:
                    return comp
        return None

    # -------------------------------------------------------------------------
    # Component modification
    # -------------------------------------------------------------------------

    def add_component(
            self,
            name: str,
            file: str,
            class_name: Optional[str] = None,
            version: str = "1.0.0",
            description: str = "",
            wire: bool = False,
            wirings: Optional[list[str]] = None,
            requires: Optional[list[str]] = None,
            config: Optional[Union[str, dict, list]] = None,
    ) -> ComponentEntry:
        """Add a new component to the manifest.

        Args:
            name: Component name
            file: Relative path to the Python file
            class_name: Class name within the file (None for module components)
            version: Component version
            description: Component description
            wire: Enable automatic dependency injection
            wirings: List of wiring specifications
            requires: List of required component names
            config: Config model reference(s)

        Returns:
            The created ComponentEntry

        Raises:
            ValueError: If a component with the same name already exists
        """
        if self.get_component(name) is not None:
            raise ValueError(f"Component '{name}' already exists in manifest")

        # Normalize config
        config_normalized = None
        if config is not None:
            if isinstance(config, str):
                config_normalized = [ComponentConfigRef(model=config)]
            elif isinstance(config, dict):
                config_normalized = [ComponentConfigRef(**config)]
            elif isinstance(config, list):
                config_normalized = [
                    ComponentConfigRef(**c) if isinstance(c, dict)
                    else ComponentConfigRef(model=c)
                    for c in config
                ]

        entry = ComponentEntry(
            name=name,
            file=file,
            class_name=class_name,
            version=version,
            description=description,
            wire=wire,
            wirings=wirings or [],
            requires=requires or [],
            config=config_normalized,
        )

        self._manifest.components.append(entry)
        self._dirty = True

        logger.debug("Added component '%s' to manifest", name)
        return entry

    def remove_component(self, name: str) -> bool:
        """Remove a component from the manifest.

        Args:
            name: Name of the component to remove

        Returns:
            True if component was removed, False if not found
        """
        for i, comp in enumerate(self._manifest.components):
            if comp.name == name:
                del self._manifest.components[i]
                self._dirty = True
                logger.debug("Removed component '%s' from manifest", name)
                return True
        return False

    def update_component(
            self,
            name: str,
            *,
            new_name: Optional[str] = None,
            version: Optional[str] = None,
            description: Optional[str] = None,
            file: Optional[str] = None,
            class_name: Optional[str] = None,
            wire: Optional[bool] = None,
            wirings: Optional[list[str]] = None,
            requires: Optional[list[str]] = None,
            config: Optional[Union[str, dict, list]] = None,
    ) -> Optional[ComponentEntry]:
        """Update an existing component in the manifest.

        Only provided parameters will be updated. Pass None to keep existing value.

        Args:
            name: Name of the component to update
            new_name: New name for the component
            version: New version
            description: New description
            file: New file path
            class_name: New class name
            wire: New wire setting
            wirings: New wirings list
            requires: New requires list
            config: New config reference(s)

        Returns:
            Updated ComponentEntry, or None if not found
        """
        entry = self.get_component(name)
        if entry is None:
            return None

        # Find index for replacement
        idx = self._manifest.components.index(entry)

        # Build update dict
        updates = {}
        if new_name is not None:
            updates["name"] = new_name
        if version is not None:
            updates["version"] = version
        if description is not None:
            updates["description"] = description
        if file is not None:
            updates["file"] = file
        if class_name is not None:
            updates["class_name"] = class_name
        if wire is not None:
            updates["wire"] = wire
        if wirings is not None:
            updates["wirings"] = wirings
        if requires is not None:
            updates["requires"] = requires
        if config is not None:
            # Normalize config
            if isinstance(config, str):
                updates["config"] = [ComponentConfigRef(model=config)]
            elif isinstance(config, dict):
                updates["config"] = [ComponentConfigRef(**config)]
            elif isinstance(config, list):
                updates["config"] = [
                    ComponentConfigRef(**c) if isinstance(c, dict)
                    else ComponentConfigRef(model=c)
                    for c in config
                ]

        if updates:
            # Create updated entry
            current_data = entry.model_dump(by_alias=False)
            current_data.update(updates)
            new_entry = ComponentEntry(**current_data)
            self._manifest.components[idx] = new_entry
            self._dirty = True
            logger.debug("Updated component '%s' in manifest", name)
            return new_entry

        return entry

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def save(self) -> None:
        """Save the manifest to disk.

        Writes the manifest to .awioc/manifest.yaml, creating the
        directory structure if necessary.
        """
        # Ensure .awioc directory exists
        awioc_dir = self._path / AWIOC_DIR
        awioc_dir.mkdir(exist_ok=True)

        # Convert manifest to dict for YAML serialization
        data = self._manifest.model_dump(
            by_alias=True,  # Use 'class' instead of 'class_name'
            exclude_none=True,
            exclude_defaults=False,
        )

        # Clean up empty lists and None values for cleaner YAML
        data = self._clean_manifest_data(data)

        # Write YAML
        manifest_path = self.manifest_path
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

        self._dirty = False
        logger.info("Saved manifest to %s", manifest_path)

    def reload(self) -> None:
        """Reload the manifest from disk, discarding unsaved changes."""
        self._manifest = _load_manifest(self._path)
        self._dirty = False
        logger.debug("Reloaded manifest from %s", self.manifest_path)

    def _clean_manifest_data(self, data: dict) -> dict:
        """Clean up manifest data for YAML serialization."""
        # Remove empty lists and None values from components
        if "components" in data:
            cleaned_components = []
            for comp in data["components"]:
                cleaned = {}
                for key, value in comp.items():
                    # Keep required fields and non-empty values
                    if key in ("name", "file"):
                        cleaned[key] = value
                    elif value is not None and value != [] and value != "":
                        # Special handling for defaults
                        if key == "version" and value == "0.0.0":
                            continue
                        if key == "wire" and value is False:
                            continue
                        cleaned[key] = value
                cleaned_components.append(cleaned)
            data["components"] = cleaned_components

        return data

    # -------------------------------------------------------------------------
    # Component compilation
    # -------------------------------------------------------------------------

    def compile_components(self) -> list:
        """Compile all components from the manifest.

        Loads and compiles all components defined in the manifest,
        returning them ready for registration with an IOC container.

        Returns:
            List of compiled component instances

        Raises:
            ImportError: If a component module cannot be loaded
            AttributeError: If a component class doesn't exist
        """
        from .loader.module_loader import compile_components_from_manifest

        return compile_components_from_manifest(self._path)

    def compile_component(self, name: str):
        """Compile a single component by name.

        Args:
            name: Name of the component to compile

        Returns:
            Compiled component instance

        Raises:
            ValueError: If component not found in manifest
            ImportError: If component module cannot be loaded
        """
        from .bootstrap import compile_component

        entry = self.get_component(name)
        if entry is None:
            raise ValueError(f"Component '{name}' not found in manifest")

        # Build component reference
        if entry.class_name:
            ref = f"{self._path / entry.file}:{entry.class_name}()"
        else:
            ref = str(self._path / entry.file)

        return compile_component(ref)

    # -------------------------------------------------------------------------
    # Utility methods
    # -------------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"AWIOCProject(path={self._path!r}, "
            f"name={self.name!r}, "
            f"components={len(self)})"
        )

    def __str__(self) -> str:
        return f"{self.name} v{self.version or '?'} ({len(self)} components)"
