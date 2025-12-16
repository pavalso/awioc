"""
Public API for the IOC framework.

This module exports all public interfaces for consumers to use.
Import only from this module for stable API access.
"""

from src.ioc.container import ContainerInterface, AppContainer
from src.ioc.components.lifecycle import (
    initialize_components,
    shutdown_components,
    register_plugin,
    unregister_plugin,
)
from src.ioc.components.protocols import (
    Component,
    AppComponent,
    PluginComponent,
    LibraryComponent,
)
from src.ioc.components.metadata import (
    ComponentMetadata,
    AppMetadata,
    ComponentTypes,
)
from src.ioc.components.registry import (
    as_component,
    component_requires,
    component_internals,
    component_str,
)
from src.ioc.di.providers import (
    get_library,
    get_config,
    get_container_api,
    get_raw_container,
    get_app,
    get_logger,
)
from src.ioc.di.wiring import wire
from src.ioc.config.base import Settings
from src.ioc.config.registry import register_configuration, clear_configurations
from src.ioc.config.loaders import load_file
from src.ioc.config.models import IOCComponentsDefinition, IOCBaseConfig
from src.ioc.bootstrap import (
    initialize_ioc_app,
    create_container,
    compile_ioc_app,
    reconfigure_ioc_app,
    reload_configuration,
)
from src.ioc.loader.module_loader import compile_component
from src.ioc.logging.setup import setup_logging

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
