import inspect
import logging
from datetime import datetime
from logging import Logger
from typing import TypeVar, Optional, overload, Union

import pydantic
from dependency_injector import containers, providers

from .components.metadata import ComponentTypes, Internals, RegistrationInfo
from .components.protocols import (
    Component,
    AppComponent,
    PluginComponent,
    LibraryComponent,
)
from .components.registry import (
    component_internals,
    component_initialized,
    clean_module_name,
)
from .config.base import Settings
from .config.models import IOCBaseConfig

_Lib_type = TypeVar("_Lib_type")
_Plugin_type = TypeVar("_Plugin_type")
_Model_type = TypeVar("_Model_type", bound=pydantic.BaseModel)

logger = logging.getLogger(__name__)


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
    def app_config_model(self) -> type[IOCBaseConfig]:
        app = self.provided_app()
        meta = app.__metadata__
        if "base_config" in meta and meta["base_config"] is not None:
            cfg_cls = meta["base_config"]
            assert issubclass(cfg_cls,
                              IOCBaseConfig), f"App base_config must be subclass of IOCBaseConfig, got: {cfg_cls}"
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

    @overload
    def provided_lib(self, type_: type[_Lib_type]) -> _Lib_type:  # pragma: no cover
        ...

    @overload
    def provided_lib(self, type_: str) -> _Lib_type:  # pragma: no cover
        ...

    def provided_lib(self, type_: Union[type[_Lib_type], str]) -> _Lib_type:  # TODO: add test coverage
        if isinstance(type_, str):
            return self._libs_map[type_]()
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

    @overload
    def provided_plugin(self, type_: type[_Plugin_type]) -> Optional[_Plugin_type]:  # pragma: no cover
        ...

    @overload
    def provided_plugin(self, type_: str) -> Optional[_Plugin_type]:  # pragma: no cover
        ...

    def provided_plugin(self, type_: Union[_Plugin_type, str]) -> Optional[_Plugin_type]:  # TODO: add test coverage
        if isinstance(type_, str):
            provider = self._plugins_map.get(type_)
        else:
            provider = self._plugins_map.get(type_.__metadata__["name"])  # TODO: add test coverage
        return provider() if provider is not None else None

    def provided_component(self, name: str) -> Optional[Component]:  # TODO: add test coverage
        """Get a component by its registered name/id."""
        provider = self._container.components().get(name)
        return provider() if provider is not None else None

    def provided_logger(self) -> Logger:
        return self._container.logger()

    @staticmethod
    def __capture_registration_info(stack_level: int = 2) -> RegistrationInfo:
        """Capture registration info from the call stack."""
        frame = inspect.stack()[stack_level]
        module_name = frame.frame.f_globals.get("__name__", "unknown")
        return RegistrationInfo(
            registered_by=clean_module_name(module_name),
            registered_at=datetime.now(),
            file=frame.filename,
            line=frame.lineno
        )

    def __init_component(
            self,
            component: Component,
            registration: RegistrationInfo
    ) -> Internals:
        assert hasattr(component, "__metadata__")
        assert not component_initialized(component)

        _internals = Internals()
        _internals.registration = registration
        component.__metadata__["_internals"] = _internals

        for req in self._compute_requirements(component):
            # Check if the required component has internals (is registered)
            req_internals = req.__metadata__.get("_internals")
            if req_internals is not None:
                req_internals.required_by.add(component)
                _internals.requires.add(req)

        return _internals

    def __deinit_component(self, component: Component):
        assert hasattr(component, "__metadata__")

        if "_internals" not in component.__metadata__ or component.__metadata__["_internals"] is None:
            return

        # component_requires returns component names (strings)
        for req in self._compute_requirements(component):
            req_internals = req.__metadata__.get("_internals")
            if req_internals is not None:
                req_internals.required_by.discard(component)

        component.__metadata__["_internals"] = None

    def register_libraries(
            self,
            *libs: tuple[str | type, LibraryComponent]
    ) -> None:
        logger.debug("Registering %d libraries", len(libs))
        registration = self.__capture_registration_info(stack_level=2)
        for key, lib in libs:
            lib_id = key if isinstance(key, str) else key.__qualname__

            self.__init_component(lib, registration)
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
            *plugins: PluginComponent,
            _registration: Optional[RegistrationInfo] = None
    ) -> None:
        logger.debug("Registering %d plugins", len(plugins))
        # Use provided registration info (from lifecycle helpers) or capture automatically
        registration = _registration or self.__capture_registration_info(stack_level=2)
        for plugin in plugins:
            plugin_id = plugin.__metadata__["name"]

            self.__init_component(plugin, registration)
            component_internals(plugin).type = ComponentTypes.PLUGIN

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

        registration = self.__capture_registration_info(stack_level=2)
        self.__init_component(app, registration)
        component_internals(app).type = ComponentTypes.APP

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

    def _compute_requirements(
            self,
            *components: Component,
            recursive: bool = False
    ) -> set[Component]:
        required = set()

        for component in components:
            if "requires" not in component.__metadata__:
                requires = set()
            elif not component.__metadata__["requires"]:
                requires = set()
            else:
                requires = component.__metadata__["requires"]

            for req in requires:
                if req in required:
                    continue
                req = self.provided_component(req)
                if req is None:
                    continue
                required.add(req)
                if recursive:
                    required.update(self._compute_requirements(req, recursive=True))

        return required
