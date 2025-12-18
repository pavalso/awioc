"""
Public API for the IOC framework.

This module exports all public interfaces for consumers to use.
Import only from this module for stable API access.
"""

from .container import ContainerInterface, AppContainer
from .components.lifecycle import (
    initialize_components,
    shutdown_components,
    wait_for_components,
    register_plugin,
    unregister_plugin,
)
from .components.protocols import (
    Component,
    AppComponent,
    PluginComponent,
    LibraryComponent,
)
from .components.metadata import (
    ComponentMetadata,
    AppMetadata,
    ComponentTypes,
)
from .components.registry import (
    as_component,
    component_requires,
    component_internals,
    component_str,
)
from .di.providers import (
    get_library,
    get_config,
    get_container_api,
    get_raw_container,
    get_app,
    get_logger,
)
from .di.wiring import wire
from .config.base import Settings
from .config.registry import register_configuration, clear_configurations
from .config.loaders import load_file
from .config.models import IOCComponentsDefinition, IOCBaseConfig
from .config.setup import setup_logging
from .bootstrap import (
    initialize_ioc_app,
    create_container,
    compile_ioc_app,
    reconfigure_ioc_app,
    reload_configuration,
)
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
    "as_component",
    "component_requires",
    "component_internals",
    "component_str",
    # Lifecycle
    "initialize_components",
    "shutdown_components",
    "wait_for_components",
    "register_plugin",
    "unregister_plugin",
    # DI
    "get_library",
    "get_config",
    "get_container_api",
    "get_raw_container",
    "get_app",
    "get_logger",
    "wire",
    # Config
    "Settings",
    "register_configuration",
    "clear_configurations",
    "load_file",
    "IOCComponentsDefinition",
    "IOCBaseConfig",
    # Bootstrap
    "initialize_ioc_app",
    "create_container",
    "compile_ioc_app",
    "reconfigure_ioc_app",
    "reload_configuration",
    # Loader
    "compile_component",
    # Logging
    "setup_logging",
]
