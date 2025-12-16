from src.ioc.components.metadata import (
    ComponentTypes,
    Internals,
    ComponentMetadata,
    AppMetadata,
    ComponentMetadataType,
)
from src.ioc.components.protocols import (
    Component,
    AppComponent,
    PluginComponent,
    LibraryComponent,
)
from src.ioc.components.registry import (
    as_component,
    component_requires,
    component_internals,
    component_str,
)
from src.ioc.components.lifecycle import (
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
