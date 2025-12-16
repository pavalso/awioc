from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, TypedDict, Optional, Union

import pydantic

if TYPE_CHECKING:
    from src.ioc.components.protocols import Component
    from src.ioc.config.base import Settings


class ComponentTypes(Enum):
    APP = "app"
    PLUGIN = "plugin"
    LIBRARY = "library"
    COMPONENT = "component"


@dataclass
class Internals:
    required_by: set["Component"] = field(default_factory=set)
    initialized_by: set["Component"] = field(default_factory=set)
    is_initialized: bool = False
    is_initializing: bool = False
    ioc_components_definition: Optional[type[pydantic.BaseModel]] = None
    ioc_config: Optional[type["Settings"]] = None
    type: ComponentTypes = ComponentTypes.COMPONENT


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
