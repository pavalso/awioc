import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from types import ModuleType
from typing import Union, cast, Callable, Optional

from .manifest import (
    AWIOC_DIR,
    MANIFEST_FILENAME,
    find_manifest,
    load_manifest,
    manifest_to_metadata,
    resolve_config_models,
)
from ..components.protocols import Component

logger = logging.getLogger(__name__)


def _resolve_pot_reference(pot_ref: str) -> Optional[tuple[Path, Optional[str]]]:
    """Resolve a @pot-name/component reference to a file path.

    Handles references like:
    - @my-pot/component-name
    - @my-pot/component-name:ClassName()

    Args:
        pot_ref: Reference in format @pot-name/component-name[:class]

    Returns:
        Tuple of (component_path, class_reference) or None if not a pot reference.
    """
    if not pot_ref.startswith("@"):
        return None

    # Import pot utilities here to avoid circular imports
    from ..commands.pot import get_pot_path, load_pot_manifest

    # Parse @pot-name/component-name[:class]
    ref = pot_ref[1:]  # Remove @

    # Normalize path separators (handle Windows backslashes)
    ref = ref.replace("\\", "/")

    # Check for class reference
    class_ref = None
    if ":" in ref:
        ref, class_ref = ref.rsplit(":", 1)

    if "/" not in ref:
        logger.error(f"Invalid pot reference: {pot_ref} (expected @pot-name/component)")
        return None

    pot_name, component_name = ref.split("/", 1)
    pot_path = get_pot_path(pot_name)

    if not pot_path.exists():
        raise FileNotFoundError(f"Pot not found: {pot_name}")

    # Load manifest to find component
    manifest = load_pot_manifest(pot_path)
    components = manifest.get("components", {})

    if component_name not in components:
        available = list(components.keys())
        raise FileNotFoundError(
            f"Component '{component_name}' not found in pot '{pot_name}'. "
            f"Available: {available}"
        )

    component_info = components[component_name]
    component_file = pot_path / component_info.get("path", component_name)

    if not component_file.exists():
        raise FileNotFoundError(f"Component file not found: {component_file}")

    # If no explicit class reference but manifest has class_name, use it
    if not class_ref and component_info.get("class_name"):
        class_ref = f"{component_info['class_name']}()"

    return component_file, class_ref


def _parse_component_reference(component_ref: str) -> tuple[Path, str | None]:
    """
    Parse a component reference into path and attribute reference parts.

    Component references can be in the format:
    - "path/to/module" - just a path, component is the module itself
    - "path/to/module:attribute" - path with attribute reference
    - "path/to/module:obj.attr" - path with nested attribute reference

    Handles Windows paths (e.g., "C:\\path\\to\\module") correctly.

    :param component_ref: The component reference string.
    :return: Tuple of (path, reference) where reference is None if not specified.
    """
    # Count colons - Windows paths have one for drive letter (e.g., "C:")
    colon_count = component_ref.count(":")

    if colon_count == 0:
        # No colon, just a path
        return Path(component_ref), None

    if colon_count == 1:
        # One colon - check if it's a Windows drive letter
        colon_idx = component_ref.index(":")
        if colon_idx == 1 and component_ref[0].isalpha():
            # It's a Windows drive letter (e.g., "C:\path"), no reference
            return Path(component_ref), None
        # It's a reference separator (e.g., "path/module:attr")
        path_part, ref_part = component_ref.rsplit(":", 1)
        return Path(path_part), ref_part

    # Multiple colons - the last one is likely the reference separator
    # (e.g., "C:\path\module:attr")
    path_part, ref_part = component_ref.rsplit(":", 1)
    return Path(path_part), ref_part


def _resolve_reference(module: ModuleType, reference: str) -> object:
    """
    Resolve a reference string to an object within a module.

    Supports:
    - Simple attributes: "MyClass"
    - Nested attributes: "obj.attr"
    - Callable expressions: "factory()" or "MyClass()"

    :param module: The loaded module.
    :param reference: The reference string to resolve.
    :return: The resolved object.
    :raises AttributeError: If the reference cannot be resolved.
    """
    # Check if it's a callable expression (ends with parentheses)
    if reference.endswith("()"):
        attr_name = reference[:-2]
        obj = _get_nested_attr(module, attr_name)
        if callable(obj):
            obj = cast(Callable, obj)
            logger.debug("Calling %s() to get component", attr_name)
            return obj()
        raise TypeError(f"'{attr_name}' is not callable")

    return _get_nested_attr(module, reference)


def _get_nested_attr(obj: object, attr_path: str) -> object:
    """
    Get a nested attribute from an object.

    :param obj: The object to get the attribute from.
    :param attr_path: Dot-separated attribute path (e.g., "obj.attr.subattr").
    :return: The resolved attribute.
    :raises AttributeError: If the attribute path cannot be resolved.
    """
    for attr in attr_path.split("."):
        obj = getattr(obj, attr)
    return obj


def _get_manifest_metadata(
        path: Path,
        reference: Optional[str],
) -> Optional[tuple[dict, Path, Path, Optional[str]]]:
    """
    Get component metadata from .awioc/manifest.yaml if available.

    Searches for a manifest.yaml in the component's .awioc directory and extracts
    the metadata for the specified component.

    For package components (directories): looks in path/.awioc/manifest.yaml
    For single-file components: looks in path.parent/.awioc/manifest.yaml

    :param path: Path to the component file or directory.
    :param reference: Optional class reference (e.g., "MyClass()").
    :return: Tuple of (metadata dict, manifest path, resolved file path, class reference)
             or None if no manifest found.
    """
    manifest_path = find_manifest(path)
    if manifest_path is None:
        return None

    try:
        # manifest_path is .awioc/manifest.yaml, so parent.parent is the component directory
        component_dir = manifest_path.parent.parent
        manifest = load_manifest(component_dir)
    except Exception as e:
        logger.warning("Failed to load manifest %s: %s", manifest_path, e)
        return None

    # Determine the file name(s) to search for
    file_names_to_try = []
    if path.is_file():
        file_names_to_try = [path.name]
    elif path.is_dir():
        # For package directories, try multiple common patterns:
        # 1. __init__.py (standard package)
        # 2. <dirname>.py (module named after directory)
        # 3. <dirname> (directory name without extension)
        file_names_to_try = ["__init__.py", f"{path.name}.py", path.name]
    else:
        # Path doesn't exist yet, try both with and without .py suffix
        file_names_to_try = [
            path.with_suffix(".py").name,
            path.name,
        ]

    # Extract class name from reference if provided
    class_name = None
    if reference:
        class_name = reference.rstrip("()")

    # Find the component entry in the manifest, trying each possible file name
    entry = None
    for file_name in file_names_to_try:
        entry = manifest.get_component_by_file(file_name, class_name)
        if entry is not None:
            break
        # Try without class filter if we have a reference
        if class_name:
            entry = manifest.get_component_by_file(file_name)
            if entry is not None:
                break

    # Fallback: for directories, if no file pattern matched and manifest has
    # exactly one component, use that component (handles cases like openai_gpt/
    # directory with open_ai.py file)
    if entry is None and path.is_dir() and len(manifest.components) == 1:
        entry = manifest.components[0]
        logger.debug(
            "Using single manifest entry '%s' for directory '%s'",
            entry.name,
            path.name,
        )

    if entry is None:
        logger.debug(
            "No manifest entry found for files %s (class: %s)",
            file_names_to_try,
            class_name,
        )
        return None

    # Convert entry to metadata dict
    metadata = manifest_to_metadata(entry, manifest_path)

    # Build resolved file path from manifest entry
    # For directories, the file is relative to the directory
    # For single files, the file is in the parent directory
    if path.is_dir():
        resolved_file_path = path / entry.file
    else:
        resolved_file_path = path.parent / entry.file

    # Get class reference from manifest entry if available
    resolved_class_ref = f"{entry.class_name}()" if entry.class_name else None

    return metadata, manifest_path, resolved_file_path, resolved_class_ref


def _attach_manifest_metadata(
        component_obj: object,
        metadata: dict,
        manifest_path: Path,
) -> None:
    """
    Attach metadata from manifest to a component object.

    Resolves config model references and sets up the __metadata__ attribute.

    :param component_obj: The component object to attach metadata to.
    :param metadata: Metadata dict from manifest.
    :param manifest_path: Path to the manifest file.
    """
    # Resolve config model references
    # manifest_path is .awioc/manifest.yaml, so parent.parent is the component directory
    config_refs = metadata.pop("_config_refs", [])
    if config_refs:
        try:
            component_dir = manifest_path.parent.parent
            resolved_configs = resolve_config_models(
                config_refs, component_dir
            )
            metadata["config"] = resolved_configs if resolved_configs else None
        except Exception as e:
            logger.warning("Failed to resolve config models: %s", e)
            metadata["config"] = None

    # Set the metadata on the component
    component_obj.__metadata__ = metadata


def _load_module(name: Path) -> ModuleType:
    """
    Load a module from a file or directory path.

    :param name: Path to the module (file or directory).
    :return: The loaded module.
    :raises FileNotFoundError: If the module cannot be found.
    """
    logger.debug("Loading module from path: %s", name)

    # Resolve relative paths like "." to absolute paths to get proper directory names
    # This is needed because Path(".").name returns "" instead of the actual directory name
    if not name.is_absolute():
        name = name.resolve()
        logger.debug("Resolved relative path to: %s", name)

    # Determine module path and desired module name
    if name.is_file():
        module_path = name
        module_name = name.stem
        logger.debug("Path is a file: %s", module_path)

    elif name.with_suffix(".py").is_file():
        module_path = name.with_suffix(".py")
        module_name = name.stem
        logger.debug("Path resolved to .py file: %s", module_path)

    elif name.is_dir():
        module_path = name / "__init__.py"
        module_name = name.name
        logger.debug("Path is a directory, using __init__.py: %s", module_path)

    else:
        logger.error("Module not found: %s", name)
        raise FileNotFoundError(f"Module not found: {name}")

    parent_dir = module_path.parent.as_posix()
    if parent_dir not in sys.path:
        logger.debug("Adding to sys.path: %s", parent_dir)
        sys.path.insert(0, parent_dir)

    if module_name in sys.modules:
        logger.debug("Module already loaded, reusing: %s", module_name)
        return sys.modules[module_name]

    # Create spec
    logger.debug("Creating module spec for: %s", module_name)
    spec = importlib.util.spec_from_file_location(
        module_name,
        module_path.as_posix(),
        submodule_search_locations=[module_path.parent.as_posix()]
        if module_path.name == "__init__.py"
        else None
    )

    assert spec is not None
    loader = spec.loader
    assert loader is not None

    # Create module with the desired name
    module = importlib.util.module_from_spec(spec)

    # Guarantee module.__name__ == module_name
    sys.modules[module_name] = module

    # Execute module code
    logger.debug("Executing module: %s", module_name)
    loader.exec_module(module)

    return module


def compile_component(
        component_ref: Union[str, Path],
        require_manifest: bool = True,
) -> Component:
    """
    Dynamically load a component from a file or directory path.

    IMPORTANT: All components MUST have a manifest entry in .awioc/manifest.yaml.
    - Package components: my_package/.awioc/manifest.yaml
    - Single-file components: parent_dir/.awioc/manifest.yaml

    Component references can be in the format:
    - "path/to/module" - load module as component
    - "path/to/module:MyClass" - load MyClass from module
    - "path/to/module:obj.attr" - load nested attribute from module
    - "path/to/module:factory()" - call factory() to get component
    - "@pot-name/component" - load from pot repository
    - "@pot-name/component:ClassName()" - load specific class from pot

    :param component_ref: Path or reference string to the component.
    :param require_manifest: If True (default), raise error if no manifest found.
    :return: The loaded component.
    :raises FileNotFoundError: If the component path cannot be found.
    :raises AttributeError: If the reference cannot be resolved.
    :raises RuntimeError: If no manifest entry exists for the component.
    """
    # Convert to string if Path
    if isinstance(component_ref, Path):
        component_ref = str(component_ref)

    logger.debug("Compiling component from reference: %s", component_ref)

    # Check for pot reference (@pot-name/component)
    if component_ref.startswith("@"):
        pot_result = _resolve_pot_reference(component_ref)
        if pot_result is None:
            raise ValueError(f"Invalid pot reference: {component_ref}")
        path, reference = pot_result
        logger.debug("Resolved pot reference to: %s (class: %s)", path, reference)
    else:
        # Parse the reference
        path, reference = _parse_component_reference(component_ref)

    # Resolve path for manifest lookup
    resolved_path = path.resolve() if not path.is_absolute() else path

    # Try to get metadata from manifest BEFORE loading Python
    manifest_result = _get_manifest_metadata(resolved_path, reference)
    use_manifest = manifest_result is not None

    if require_manifest and not use_manifest:
        raise RuntimeError(
            f"No manifest entry found for component '{component_ref}'. "
            f"Expected manifest at: {resolved_path / AWIOC_DIR / MANIFEST_FILENAME} "
            f"or {resolved_path.parent / AWIOC_DIR / MANIFEST_FILENAME}. "
            f"Create a manifest with: awioc generate manifest <path>"
        )

    # Use resolved paths from manifest if available
    if use_manifest:
        metadata, manifest_path, resolved_file_path, resolved_class_ref = manifest_result
        # Use manifest's file path and class reference if not explicitly provided
        # But if the file is __init__.py, keep loading the directory as a package
        if resolved_file_path.exists() and resolved_file_path.name != "__init__.py":
            path = resolved_file_path
            logger.debug("Using manifest file path: %s", path)
        if resolved_class_ref and not reference:
            reference = resolved_class_ref
            logger.debug("Using manifest class reference: %s", reference)

    # Load the module (executes Python code)
    module = _load_module(path)

    # Resolve the reference if provided
    if reference:
        logger.debug("Resolving reference '%s' in module", reference)
        component_obj = _resolve_reference(module, reference)
        logger.debug("Component resolved successfully: %s:%s", path, reference)
    else:
        component_obj = module
        logger.debug("Component compiled successfully: %s", path)

    # Apply metadata from manifest (manifest is required)
    if use_manifest:
        _attach_manifest_metadata(component_obj, metadata, manifest_path)
        logger.debug("Applied metadata from manifest: %s", manifest_path)

    # Store the original source reference for serialization
    # For pot references, keep the @pot/component format
    # For file paths, store the original reference string
    component_obj.__metadata__["_source_ref"] = component_ref

    # Ensure the returned object has, at least, the Optionals of Component protocol
    if not hasattr(component_obj, "initialize"):
        component_obj.initialize = None
    if not hasattr(component_obj, "shutdown"):
        component_obj.shutdown = None
    if not hasattr(component_obj, "wait"):
        component_obj.wait = None

    return cast(Component, component_obj)


def compile_components_from_manifest(
        directory: Path,
) -> list[Component]:
    """
    Load all components defined in a directory's .awioc/manifest.yaml.

    This function loads the manifest and compiles each component defined in it.

    :param directory: Path to the directory containing .awioc/manifest.yaml.
    :return: List of loaded components.
    :raises FileNotFoundError: If .awioc/manifest.yaml doesn't exist.
    """
    manifest = load_manifest(directory)
    components = []

    for entry in manifest.components:
        # Build component reference
        file_path = directory / entry.file
        if entry.class_name:
            component_ref = f"{file_path}:{entry.class_name}()"
        else:
            component_ref = str(file_path)

        try:
            component = compile_component(component_ref, require_manifest=False)
            components.append(component)
            logger.debug("Loaded component: %s", entry.name)
        except Exception as e:
            logger.error("Failed to load component '%s': %s", entry.name, e)
            raise

    return components
