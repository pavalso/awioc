import logging
from typing import Any, Optional

from .metadata import Internals, RegistrationInfo
from .protocols import Component

logger = logging.getLogger(__name__)


def as_component(obj: Any) -> Component:
    """
    Convert an object to a Component by adding metadata if missing.

    :param obj: The object to convert.
    :return: The object as a Component.
    """
    if not hasattr(obj, "__metadata__"):
        name = getattr(obj, "__qualname__", obj.__class__.__qualname__)
        logger.debug("Converting object to component: %s", name)
        obj.__metadata__ = {
            "name": name,
            "version": "0.0.0",
            "wire": False,
            "description": getattr(obj, "__doc__", "") or ""
        }

    if not hasattr(obj, "initialize"):
        obj.initialize = None

    if not hasattr(obj, "shutdown"):
        obj.shutdown = None

    if not hasattr(obj, "wait"):
        obj.wait = None

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


def component_str(component: Component) -> str:
    """
    Get a string representation of a component.

    :param component: The component.
    :return: String in format "name version".
    """
    meta = component.__metadata__
    return f"{meta['name']} v{meta['version']}"


def component_initialized(component: Component) -> bool:
    assert hasattr(component, "__metadata__")
    if "_internals" not in component.__metadata__ or component.__metadata__["_internals"] is None:
        return False
    return component.__metadata__["_internals"].is_initialized


def component_registration(component: Component) -> Optional[RegistrationInfo]:
    """
    Get the registration information of a component.

    Returns information about who/what registered the component,
    including the source type, registrar identifier, and location.

    :param component: The component to analyze.
    :return: The registration info, or None if not available.
    """
    assert hasattr(component, "__metadata__")
    if "_internals" not in component.__metadata__ or component.__metadata__["_internals"] is None:
        return None
    return component.__metadata__["_internals"].registration
