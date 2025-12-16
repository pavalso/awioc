from typing import Any

from src.ioc.components.metadata import Internals
from src.ioc.components.protocols import Component


def as_component(obj: Any) -> Component:
    """
    Convert an object to a Component by adding metadata if missing.

    :param obj: The object to convert.
    :return: The object as a Component.
    """
    if not hasattr(obj, "__metadata__"):
        obj.__metadata__ = {
            "name": getattr(obj, "__qualname__", obj.__class__.__qualname__),
            "version": "0.0.0",
            "wire": False,
            "description": getattr(obj, "__doc__", "") or ""
        }

    if not hasattr(obj, "initialize"):
        obj.initialize = None

    if not hasattr(obj, "shutdown"):
        obj.shutdown = None

    return obj


def component_requires(*components: Component, recursive: bool = False) -> set[Component]:
    """
    Get the full set of components required by the given components.

    :param components: The initial components to analyze.
    :param recursive: Whether to include dependencies of dependencies.
    :return: A set of all required components.
    """
    required = set()

    for component in components:
        for req in component.__metadata__.get("requires", set()):
            if req in required:
                continue
            required.add(req)
            if recursive:
                required.update(component_requires(req, recursive=True))

    return required


def component_internals(component: Component) -> Internals:
    """
    Get the internal metadata of a component.

    :param component: The component to analyze.
    :return: The internal metadata of the component.
    """
    assert "_internals" in component.__metadata__
    return component.__metadata__["_internals"]


def component_str(comp: Component) -> str:
    """
    Get a string representation of a component.

    :param comp: The component.
    :return: String in format "name vversion".
    """
    meta = comp.__metadata__
    return f"{meta['name']} v{meta['version']}"
