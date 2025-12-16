"""
IOC Framework - Inversion of Control Framework for Python applications.

This module provides a clean public surface for the IOC framework.
Consumers should import from here for stable API access.
"""

from src.ioc.api import (
    # Bootstrap
    initialize_ioc_app,
    create_container,
    compile_ioc_app,
    reconfigure_ioc_app,
    reload_configuration,
    # Lifecycle
    initialize_components,
    shutdown_components,
    register_plugin,
    unregister_plugin,
    # DI Providers
    get_library,
    get_config,
    get_container_api,
    get_raw_container,
    get_app,
    get_logger,
    wire,
    # Config
    Settings,
    register_configuration,
    clear_configurations,
    load_file,
    IOCComponentsDefinition,
    IOCBaseConfig,
    # Container
    ContainerInterface,
    AppContainer,
    # Components
    Component,
    AppComponent,
    PluginComponent,
    LibraryComponent,
    ComponentMetadata,
    AppMetadata,
    ComponentTypes,
    as_component,
    component_requires,
    component_internals,
    component_str,
    # Loader
    compile_component,
    # Logging
    setup_logging,
)

__all__ = [
    # Bootstrap
    "initialize_ioc_app",
    "create_container",
    "compile_ioc_app",
    "reconfigure_ioc_app",
    "reload_configuration",
    # Lifecycle
    "initialize_components",
    "shutdown_components",
    "register_plugin",
    "unregister_plugin",
    # DI Providers
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
    # Loader
    "compile_component",
    # Logging
    "setup_logging",
]
