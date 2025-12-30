import logging
from typing import Any, Optional, Callable, overload, Iterable, TypeVar, Union

from pydantic import BaseModel

from .metadata import Internals, RegistrationInfo, metadata
from .protocols import Component

logger = logging.getLogger(__name__)

C = TypeVar("C", bound=Any)


@overload
def as_component(ref: object) -> Component: ...


@overload
def as_component(
        *,
        name: Optional[str] = ...,
        version: Optional[str] = ...,
        description: Optional[str] = ...,
        wire: bool = ...,
        wirings: Optional[Iterable[str]] = ...,
        requires: Optional[Iterable[Union[Component, str]]] = ...,
        config: Optional[Iterable[type[BaseModel]] | type[BaseModel]] = ...,
        base_config: Optional[type[Any]] = ...
) -> Callable[[object], Component]: ...


def as_component(
        ref: Optional[object] = None,
        *,
        name: Optional[str] = None,
        version: Optional[str] = None,
        description: Optional[str] = "",
        wire: bool = True,
        wirings: Optional[Iterable[str]] = None,
        requires: Optional[Iterable[Union[Component, str]]] = None,
        config: Optional[Iterable[type[BaseModel]] | type[BaseModel]] = None,
        base_config: Optional[type[Any]] = None,
):
    def decorator(obj: C) -> C:
        """
        Decorator to convert an object to a Component by adding metadata.

        :param obj: The object to convert.
        :return: The object as a Component.
        """
        if hasattr(obj, "__metadata__"):
            obj_metadata = obj.__metadata__
        else:
            obj_metadata = {}

        updated_metadata = metadata(
            name=name or getattr(obj, "__qualname__", obj.__class__.__qualname__),
            version=version or "0.0.0",
            description=description or (getattr(obj, "__doc__", "") or ""),
            wire=wire,
            wirings=wirings,
            requires=requires,
            config=config,
            base_config=base_config
        )

        updated_metadata.update(obj_metadata)
        obj.__metadata__ = updated_metadata

        if not hasattr(obj, "initialize"):
            obj.initialize = None

        if not hasattr(obj, "shutdown"):
            obj.shutdown = None

        if not hasattr(obj, "wait"):
            obj.wait = None

        return obj

    return decorator if ref is None else decorator(ref)


def component_required_by(component: Component) -> set[Component]:
    """
    Get the components that require a given component.

    :param component: The component to analyze.
    """
    _internals = component_internals(component)
    assert _internals is not None
    assert _internals.required_by is not None
    return _internals.required_by


def component_requires(*components: Component, recursive: bool = False) -> set[Component]:
    """
    Get the components required by one or more components.

    :param components: The component(s) to analyze.
    :param recursive: If True, recursively resolve all dependencies.
    :return: Set of required components.
    """
    result: set[Component] = set()

    def get_requires(comp: Component) -> set[Component]:
        """Get direct requirements of a single component."""
        if not hasattr(comp, "__metadata__"):
            return set()

        metadata = comp.__metadata__

        # Try _internals.requires first (contains resolved component objects)
        if "_internals" in metadata and metadata["_internals"] is not None:
            internals = metadata["_internals"]
            if internals.requires:
                return internals.requires

        # Fallback to metadata requires (may contain strings or objects)
        return metadata.get("requires", set()) or set()

    def collect_recursive(comp: Component, visited: set[int]) -> None:
        """Recursively collect all dependencies."""
        comp_id = id(comp)
        if comp_id in visited:
            return
        visited.add(comp_id)

        for req in get_requires(comp):
            result.add(req)
            if recursive:
                collect_recursive(req, visited)

    visited: set[int] = set()
    for component in components:
        collect_recursive(component, visited)

    return result


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
    assert hasattr(component, "__metadata__")
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


def clean_module_name(name: str) -> str:
    """
    Clean up module name for display, removing __init__ and __main__ parts.

    :param name: The raw module name (e.g., "__init__.dashboard").
    :return: Cleaned module name (e.g., "dashboard").
    """
    if not name:
        return "unknown"
    parts = [p for p in name.split(".") if p not in ("__init__", "__main__")]
    return ".".join(parts) if parts else name
