from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, TypedDict, Optional, Union

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
        parts = [f"by '{self.registered_by}'"]
        parts.append(f"at {self.registered_at.isoformat()}")
        if self.file:
            location = f"{self.file}:{self.line}" if self.line else self.file
            parts.append(f"from {location}")
        return f"RegistrationInfo({', '.join(parts)})"


@dataclass
class Internals:
    required_by: set["Component"] = field(default_factory=set)
    initialized_by: set["Component"] = field(default_factory=set)
    is_initialized: bool = False
    is_initializing: bool = False
    is_shutting_down: bool = False
    ioc_config: Optional[type["Settings"]] = None
    type: ComponentTypes = ComponentTypes.COMPONENT
    registration: Optional[RegistrationInfo] = None


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
        requires (Optional[set[Component]]): A set of other components this component depends on.
            Those components MUST be registered in the container for this component to work.
        config (Optional[type[BaseModel]]): An optional Pydantic model for configuration.
    """
    name: str
    version: str
    description: str
    wire: Optional[bool]
    wirings: Optional[set[str]]
    requires: Optional[set["Component"]]
    config: Optional[set[type[pydantic.BaseModel]]]

    _internals: Optional["Internals"]


class AppMetadata(ComponentMetadata):
    base_config: Optional[type["Settings"]]


# Type alias for flexibility
ComponentMetadataType = Union[ComponentMetadata, dict]
