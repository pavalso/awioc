import importlib
import importlib.util
import logging
import sys
from pathlib import Path

from ..components.protocols import Component
from ..components.registry import as_component

logger = logging.getLogger(__name__)


def compile_component(name: Path) -> Component:
    """
    Dynamically load a component from a file or directory path.

    :param name: Path to the component (file or directory).
    :return: The loaded component.
    :raises FileNotFoundError: If the component cannot be found.
    """
    logger.debug("Compiling component from path: %s", name)

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
        logger.error("Component not found: %s", name)
        raise FileNotFoundError(f"Component not found: {name}")

    parent_dir = module_path.parent.as_posix()
    if parent_dir not in sys.path:
        logger.debug("Adding to sys.path: %s", parent_dir)
        sys.path.insert(0, parent_dir)

    if module_name in sys.modules:
        logger.debug("Module already loaded, reusing: %s", module_name)
        return as_component(sys.modules[module_name])

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

    logger.debug("Component compiled successfully: %s", module_name)
    return as_component(module)
