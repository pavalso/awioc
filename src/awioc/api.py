"""
Public API for the IOC framework.

This module exports all public interfaces for consumers to use.
Import only from this module for stable API access.
"""

from dependency_injector.wiring import inject

from .bootstrap import (
    initialize_ioc_app,
    compile_ioc_app,
    reconfigure_ioc_app
)
from .components.events import (
    ComponentEvent,
    on_event,
    clear_handlers as clear_event_handlers,
)
from .components.lifecycle import (
    initialize_components,
    shutdown_components,
    wait_for_components,
    register_plugin,
    unregister_plugin,
)
from .components.metadata import (
    ComponentMetadata,
    AppMetadata,
    ComponentTypes,
    RegistrationInfo,
    metadata
)
from .components.protocols import (
    Component,
    AppComponent,
    PluginComponent,
    LibraryComponent,
)
from .components.registry import (
    as_component,
    component_required_by,
    component_requires,
    component_internals,
    component_str,
    component_registration,
)
from .config.base import Settings
from .config.loaders import load_file
from .config.models import IOCComponentsDefinition, IOCBaseConfig
from .config.registry import register_configuration, clear_configurations
from .config.setup import setup_logging
from .container import ContainerInterface, AppContainer
from .di.providers import (
    get_library,
    get_config,
    get_container_api,
    get_raw_container,
    get_app,
    get_logger,
    get_plugin,
    get_component,
)
from .di.wiring import wire
from .loader.module_loader import compile_component

__all__ = [
    # Container
    "ContainerInterface",
    "AppContainer",
    # Components
    "Component",
    "AppComponent",
    "PluginComponent",
    "LibraryComponent",
    "ComponentMetadata",
    "AppMetadata",
    "ComponentTypes",
    "RegistrationInfo",
    "metadata",
    "as_component",
    "component_required_by",
    "component_requires",
    "component_internals",
    "component_str",
    "component_registration",
    # Lifecycle
    "initialize_components",
    "shutdown_components",
    "wait_for_components",
    "register_plugin",
    "unregister_plugin",
    # Events
    "ComponentEvent",
    "on_event",
    "clear_event_handlers",
    # DI
    "get_library",
    "get_config",
    "get_container_api",
    "get_raw_container",
    "get_app",
    "get_logger",
    "get_plugin",
    "get_component",
    "wire",
    "inject",
    # Config
    "Settings",
    "register_configuration",
    "clear_configurations",
    "load_file",
    "IOCComponentsDefinition",
    "IOCBaseConfig",
    # Bootstrap
    "initialize_ioc_app",
    "compile_ioc_app",
    "reconfigure_ioc_app",
    # Loader
    "compile_component",
    # Logging
    "setup_logging",
]
