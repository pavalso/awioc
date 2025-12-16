import importlib
import importlib.util
import sys
from pathlib import Path

from src.ioc.components.protocols import Component
from src.ioc.components.registry import as_component


def compile_component(name: Path) -> Component:
    """
    Dynamically load a component from a file or directory path.

    :param name: Path to the component (file or directory).
    :return: The loaded component.
    :raises FileNotFoundError: If the component cannot be found.
    """
    # Determine module path and desired module name
    if name.is_file():
        module_path = name
        module_name = name.stem

    elif name.with_suffix(".py").is_file():
        module_path = name.with_suffix(".py")
        module_name = name.stem

    elif name.is_dir():
        module_path = name / "__init__.py"
        module_name = name.name

    else:
        raise FileNotFoundError(f"Component not found: {name}")

    if module_name in sys.modules:
        return as_component(sys.modules[module_name])

    # Create spec
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
    loader.exec_module(module)

    return as_component(module)
