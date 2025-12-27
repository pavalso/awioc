import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from types import ModuleType
from typing import Union, cast, Callable, Optional

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


def compile_component(component_ref: Union[str, Path]) -> Component:
    """
    Dynamically load a component from a file or directory path.

    Component references can be in the format:
    - "path/to/module" - load module as component
    - "path/to/module:MyClass" - load MyClass from module
    - "path/to/module:obj.attr" - load nested attribute from module
    - "path/to/module:factory()" - call factory() to get component
    - "@pot-name/component" - load from pot repository
    - "@pot-name/component:ClassName()" - load specific class from pot

    :param component_ref: Path or reference string to the component.
    :return: The loaded component.
    :raises FileNotFoundError: If the component path cannot be found.
    :raises AttributeError: If the reference cannot be resolved.
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

    # Load the module
    module = _load_module(path)

    # Resolve the reference if provided
    if reference:
        logger.debug("Resolving reference '%s' in module", reference)
        component_obj = _resolve_reference(module, reference)
        logger.debug("Component resolved successfully: %s:%s", path, reference)
    else:
        component_obj = module
        logger.debug("Component compiled successfully: %s", path)

    if getattr(component_obj, "__metadata__", None) is None:
        raise RuntimeError(f"The loaded object from '{component_ref}' is not a valid component. ")

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
