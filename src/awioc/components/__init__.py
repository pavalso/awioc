from .metadata import (
    ComponentTypes,
    Internals,
    ComponentMetadata,
    AppMetadata,
    ComponentMetadataType,
)
from .protocols import (
    Component,
    AppComponent,
    PluginComponent,
    LibraryComponent,
)
from .registry import (
    as_component,
    component_requires,
    component_internals,
    component_str,
)
from .lifecycle import (
    initialize_components,
    shutdown_components,
    register_plugin,
    unregister_plugin,
)

__all__ = [
    "ComponentTypes",
    "Internals",
    "ComponentMetadata",
    "AppMetadata",
    "ComponentMetadataType",
    "Component",
    "AppComponent",
    "PluginComponent",
    "LibraryComponent",
    "as_component",
    "component_requires",
    "component_internals",
    "component_str",
    "initialize_components",
    "shutdown_components",
    "register_plugin",
    "unregister_plugin",
]
