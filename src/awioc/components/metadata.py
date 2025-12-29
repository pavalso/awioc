from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import (
    TYPE_CHECKING,
    TypedDict,
    Optional,
    Union,
    overload,
    Iterable
)

import pydantic

if TYPE_CHECKING:
    from .protocols import Component
    from ..config.base import Settings


class ComponentTypes(Enum):
    APP = "app"
    PLUGIN = "plugin"
    LIBRARY = "library"
    COMPONENT = "component"


@dataclass
class RegistrationInfo:
    """Information about who/what registered a component."""
    registered_by: str  # Module/caller that registered the component
    registered_at: datetime  # Timestamp when registration occurred
    file: Optional[str] = None  # File path where registration occurred
    line: Optional[int] = None  # Line number where registration occurred

    def __str__(self) -> str:
        parts = [f"by '{self.registered_by}'", f"at {self.registered_at.isoformat()}"]
        if self.file:
            location = f"{self.file}:{self.line}" if self.line else self.file
            parts.append(f"from {location}")
        return f"RegistrationInfo({', '.join(parts)})"


@dataclass
class Internals:
    requires: set["Component"] = field(default_factory=set)
    required_by: set["Component"] = field(default_factory=set)
    initialized_by: set["Component"] = field(default_factory=set)
    is_initialized: bool = False
    is_initializing: bool = False
    is_shutting_down: bool = False
    ioc_config: Optional[type["Settings"]] = None
    type: ComponentTypes = ComponentTypes.COMPONENT
    registration: Optional[RegistrationInfo] = None
    source_ref: Optional[str] = None  # Original reference used to load component (e.g., @pot/name)


class ComponentMetadata(TypedDict):
    """
    Metadata for a component.
    Used for identification and configuration.

    Attributes:
        name (str): The name of the component.
        version (str): The version of the component.
        description (str): A brief description of the component.
        wire (Optional[bool]): Whether the component should be auto-wired.
        wirings (Optional[set[str]]): A set of module names to wire.
        requires (Optional[set[str]]): A set of component names this component depends on.
            Those components MUST be registered in the container for this component to work.
        config (Optional[type[BaseModel]]): An optional Pydantic model for configuration.
    """
    name: str
    version: str
    description: str
    wire: Optional[bool]
    wirings: Optional[set[str]]
    requires: Optional[set[str]]
    config: Optional[set[type[pydantic.BaseModel]]]

    _internals: Optional["Internals"]


class AppMetadata(ComponentMetadata):
    base_config: Optional[type["Settings"]]


# Type alias for flexibility
ComponentMetadataType = Union[ComponentMetadata, dict]


@overload
def metadata(
        *,
        name: str,
        version: str,
        description: str,
        wire: Optional[bool] = True,
        wirings: Optional[set[str]] = None,
        requires: Optional[set[Union["Component", str]]] = None,
        config: Optional[Union[set[type[pydantic.BaseModel]], type[pydantic.BaseModel]]] = None,
        **kwargs
) -> ComponentMetadata:
    ...


@overload
def metadata(
        *,
        name: str,
        version: str,
        description: str,
        wire: Optional[bool] = True,
        wirings: Optional[Iterable[str]] = None,
        requires: Optional[Iterable[Union["Component", str]]] = None,
        config: Optional[Union[Iterable[type[pydantic.BaseModel]], type[pydantic.BaseModel]]] = None,
        base_config: Optional[type["Settings"]],
        **kwargs
) -> AppMetadata:
    ...


def _get_component_name(component: Union["Component", str]) -> str:
    """Extract component name from a Component type or string."""
    if isinstance(component, str):
        return component
    if hasattr(component, "__metadata__") and "name" in component.__metadata__:
        return component.__metadata__["name"]
    return getattr(component, "__qualname__", component.__class__.__qualname__)


def metadata(
        *,
        name: str,
        version: str,
        description: str,
        wire: Optional[bool] = True,
        wirings: Optional[Iterable[str]] = None,
        requires: Optional[Iterable[Union["Component", str]]] = None,
        config: Optional[Union[Iterable[type[pydantic.BaseModel]], type[pydantic.BaseModel]]] = None,
        base_config: Optional[type["Settings"]] = None,
        **kwargs
) -> Union[ComponentMetadata, AppMetadata]:
    """
    Create metadata for a component.

    Args:
        name (str): The name of the component.
        version (str): The version of the component.
        description (str): A brief description of the component.
        wire (Optional[bool]): Whether the component should be auto-wired.
        wirings (Optional[Iterable[str]]): An iterable of module names to wire.
        requires (Optional[Iterable[Component | str]]): An iterable of other components (types or names) this component depends on.
            Those components MUST be registered in the container for this component to work.
            Component types are converted to their names for storage.
        config (Optional[Union[Iterable[type[BaseModel]], type[BaseModel]]]): An optional Pydantic model or iterable of models for configuration.
        base_config (Optional[type[Settings]]): An optional base configuration class for app components.
        **kwargs: Additional keyword arguments to include in the metadata.
    """
    if wirings is not None:
        wirings = set(wirings)
    if requires is not None:
        # Convert Component types to their names
        requires = set(_get_component_name(req) for req in requires)
    if config is not None:
        if isinstance(config, type) and issubclass(config, pydantic.BaseModel):
            config = {config}
        else:
            config = set(config)

    meta: ComponentMetadataType = {
        "name": name,
        "version": version,
        "description": description,
        "wire": wire,
        "wirings": wirings or set(),
        "requires": requires or set(),
        "config": config or set(),
        "_internals": None,
        **kwargs
    }
    if base_config is not None:
        meta["base_config"] = base_config
    return meta
