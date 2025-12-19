import logging
from logging import Logger
from typing import TypeVar, Optional, overload

logger = logging.getLogger(__name__)

import pydantic
from dependency_injector import containers, providers

from .components.metadata import ComponentTypes, Internals
from .components.protocols import (
    Component,
    AppComponent,
    PluginComponent,
    LibraryComponent,
)
from .components.registry import component_requires, component_internals
from .config.base import Settings
from .config.models import IOCBaseConfig

_Lib_type = TypeVar("_Lib_type")
_Model_type = TypeVar("_Model_type", bound=pydantic.BaseModel)


class AppContainer(containers.DeclarativeContainer):
    __self__ = providers.Self()
    api = providers.Object(None)

    config = providers.Object(None)
    logger = providers.Object(None)

    components = providers.Singleton(dict)


class ContainerInterface:
    """Interface for interacting with the AppContainer."""

    def __init__(self, container: AppContainer) -> None:
        self._container = container

        self._app_component: Optional[Component] = None
        self._libs_map: dict[str, providers.Provider[LibraryComponent]] = {}
        self._plugins_map: dict[str, providers.Provider[PluginComponent]] = {}

        self._monotonic_id = 0

        container.api.override(
            providers.Object(self)
        )

    @property
    def app_config_model(self):
        app = self.provided_app()
        meta = app.__metadata__
        if "base_config" in meta and meta["base_config"] is not None:
            cfg_cls = meta["base_config"]
            assert issubclass(cfg_cls, Settings)
            return cfg_cls
        return IOCBaseConfig

    @property
    def ioc_config_model(self):
        app = self.provided_app()
        internals = component_internals(app)
        if internals.ioc_config is not None:
            assert isinstance(internals.ioc_config, IOCBaseConfig)
            return internals.ioc_config
        raise ValueError("IOC configuration model is not defined in the app metadata.")

    @property
    def components(self) -> list[Component]:
        return list(
            component()
            for component in self._container.components().values()
        )

    def raw_container(self) -> AppContainer:
        return self._container

    def provided_libs(self) -> set[LibraryComponent]:
        return set(lib() for lib in self._libs_map.values())

    def provided_lib(self, type_: type[_Lib_type]) -> _Lib_type:
        return self._libs_map[type_.__qualname__]()

    @overload
    def provided_config(self, model: type[_Model_type]) -> _Model_type: # pragma: no cover
        ...

    @overload
    def provided_config(self, model: None = None) -> Settings: # pragma: no cover
        ...

    def provided_config(self, model: Optional[type[_Model_type]] = None):
        cfg = self._container.config()
        if model is None:
            return cfg
        return getattr(cfg, model.__name__)

    def provided_app(self) -> AppComponent:
        if self._app_component is None:
            raise RuntimeError("App component not set")
        return self._app_component

    def provided_plugins(self) -> set[PluginComponent]:
        return set(plugin() for plugin in self._plugins_map.values())

    def provided_logger(self) -> Logger:
        return self._container.logger()

    @classmethod
    def __init_component(cls, component: Component) -> Internals:
        assert hasattr(component, "__metadata__")
        assert "_internals" not in component.__metadata__

        _internals = Internals()
        component.__metadata__["_internals"] = _internals

        for req in component_requires(component):
            if not cls.__component_initialized(req):
                cls.__init_component(req)
            req.__metadata__["_internals"].required_by.add(component)

        return _internals

    @staticmethod
    def __deinit_component(component: Component):
        assert hasattr(component, "__metadata__")
        assert "_internals" in component.__metadata__

        for req in component_requires(component):
            req.__metadata__["_internals"].required_by.discard(component)

        component.__metadata__["_internals"] = None

    @staticmethod
    def __component_initialized(component: Component) -> bool:
        assert hasattr(component, "__metadata__")
        return "_internals" in component.__metadata__

    def register_libraries(
            self,
            *libs: tuple[str | type, LibraryComponent]
    ) -> None:
        logger.debug("Registering %d libraries", len(libs))
        for key, lib in libs:
            lib_id = key if isinstance(key, str) else key.__qualname__

            self.__init_component(lib)
            component_internals(lib).type = ComponentTypes.LIBRARY

            provider = providers.Object(lib)
            self._libs_map[lib_id] = provider
            self._container.components()[lib_id] = provider
            logger.debug("Registered library: %s", lib_id)

    def unregister_libraries(  # pragma: no cover
            self,
            *types: type[_Lib_type]
    ) -> None:
        assert self._container.libs().keys() >= {type_.__qualname__ for type_ in types}
        for type_ in types:
            self.__deinit_component(self._container.libs()[type_.__qualname__]())
            del self._container.libs()[type_.__qualname__]

    def register_plugins(
            self,
            *plugins: PluginComponent
    ) -> None:
        logger.debug("Registering %d plugins", len(plugins))
        for plugin in plugins:
            plugin_id = plugin.__metadata__["name"]
            self.__init_component(plugin)
            provider = providers.Object(plugin)
            self._plugins_map[plugin_id] = provider
            self._container.components()[plugin_id] = provider
            logger.debug("Registered plugin: %s", plugin_id)

    def unregister_plugins(
            self,
            *plugins: PluginComponent
    ) -> None:
        logger.debug("Unregistering %d plugins", len(plugins))
        for plugin in plugins:
            plugin_id = plugin.__metadata__["name"]
            if plugin_id in self._plugins_map:
                self.__deinit_component(plugin)
                del self._plugins_map[plugin_id]
                if plugin_id in self._container.components():
                    del self._container.components()[plugin_id]
                logger.debug("Unregistered plugin: %s", plugin_id)

    def set_app(self, app: AppComponent) -> None:
        app_name = app.__metadata__["name"]
        logger.debug("Setting app component: %s", app_name)
        self.__init_component(app)
        self._app_component = app
        self._container.components()[app_name] = providers.Object(app)

    def set_logger(self, new_logger: Logger) -> None:
        logger.debug("Setting container logger: %s", new_logger.name if new_logger else None)
        self._container.logger.override(
            providers.Object(new_logger)
        )

    def set_config(self, config: Settings) -> None:
        logger.debug("Setting container configuration: %s", type(config).__name__)
        self._container.config.override(
            providers.Object(config)
        )
