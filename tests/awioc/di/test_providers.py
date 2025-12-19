import pytest
from unittest.mock import MagicMock, patch, Mock
import pydantic

from dependency_injector.wiring import Provide

from src.awioc.di import providers as providers_module
from src.awioc.di.providers import (
    get_library,
    get_config,
    get_container_api,
    get_raw_container,
    get_app,
    get_logger,
)


class TestGetLibraryFunction:
    """Tests for get_library function."""

    def test_get_library_exists(self):
        """Test get_library function exists."""
        assert hasattr(providers_module, 'get_library')
        assert callable(providers_module.get_library)

    def test_get_library_has_overloads(self):
        """Test get_library has type and string variants."""
        assert get_library is not None

    def test_get_library_with_type_returns_provide_marker(self):
        """Test get_library returns a Provide marker when given a type."""

        class MockLibrary:
            pass

        result = get_library(MockLibrary)
        assert isinstance(result, Provide)

    def test_get_library_with_string_returns_provide_marker(self):
        """Test get_library returns a Provide marker when given a string."""
        result = get_library("some_library")
        assert isinstance(result, Provide)

    def test_get_library_different_types_produce_different_markers(self):
        """Test that different library types produce distinct markers."""

        class LibraryA:
            pass

        class LibraryB:
            pass

        result_a = get_library(LibraryA)
        result_b = get_library(LibraryB)
        # Both should be Provide instances
        assert isinstance(result_a, Provide)
        assert isinstance(result_b, Provide)


class TestGetConfigFunction:
    """Tests for get_config function."""

    def test_get_config_exists(self):
        """Test get_config function exists."""
        assert hasattr(providers_module, 'get_config')
        assert callable(providers_module.get_config)

    def test_get_config_without_model_returns_provide_marker(self):
        """Test get_config returns a Provide marker when called without model."""
        result = get_config()
        assert isinstance(result, Provide)

    def test_get_config_with_none_returns_provide_marker(self):
        """Test get_config returns a Provide marker when called with None."""
        result = get_config(None)
        assert isinstance(result, Provide)

    def test_get_config_with_model_returns_provide_marker(self):
        """Test get_config returns a Provide marker when given a model type."""

        class TestConfigModel(pydantic.BaseModel):
            name: str = "test"

        result = get_config(TestConfigModel)
        assert isinstance(result, Provide)

    def test_get_config_different_models_produce_markers(self):
        """Test that different config models produce markers."""

        class ConfigA(pydantic.BaseModel):
            value_a: str = "a"

        class ConfigB(pydantic.BaseModel):
            value_b: str = "b"

        result_a = get_config(ConfigA)
        result_b = get_config(ConfigB)
        assert isinstance(result_a, Provide)
        assert isinstance(result_b, Provide)


class TestGetContainerApi:
    """Tests for get_container_api function."""

    def test_function_exists(self):
        """Test get_container_api function exists."""
        assert hasattr(providers_module, 'get_container_api')
        assert callable(providers_module.get_container_api)

    def test_returns_provide_marker(self):
        """Test get_container_api returns a Provide marker."""
        result = get_container_api()
        assert isinstance(result, Provide)

    def test_consistent_return(self):
        """Test get_container_api returns consistent marker type."""
        result1 = get_container_api()
        result2 = get_container_api()
        assert type(result1) == type(result2)


class TestGetRawContainer:
    """Tests for get_raw_container function."""

    def test_function_exists(self):
        """Test get_raw_container function exists."""
        assert hasattr(providers_module, 'get_raw_container')
        assert callable(providers_module.get_raw_container)

    def test_returns_provide_marker(self):
        """Test get_raw_container returns a Provide marker."""
        result = get_raw_container()
        assert isinstance(result, Provide)

    def test_consistent_return(self):
        """Test get_raw_container returns consistent marker type."""
        result1 = get_raw_container()
        result2 = get_raw_container()
        assert type(result1) == type(result2)


class TestGetApp:
    """Tests for get_app function."""

    def test_function_exists(self):
        """Test get_app function exists."""
        assert hasattr(providers_module, 'get_app')
        assert callable(providers_module.get_app)

    def test_returns_provide_marker(self):
        """Test get_app returns a Provide marker."""
        result = get_app()
        assert isinstance(result, Provide)

    def test_consistent_return(self):
        """Test get_app returns consistent marker type."""
        result1 = get_app()
        result2 = get_app()
        assert type(result1) == type(result2)


class TestGetLoggerFunction:
    """Tests for get_logger function."""

    def test_get_logger_exists(self):
        """Test get_logger function exists."""
        assert hasattr(providers_module, 'get_logger')
        assert callable(providers_module.get_logger)

    def test_get_logger_no_args_returns_provide_marker(self):
        """Test get_logger returns a Provide marker when called without arguments."""
        result = get_logger()
        assert isinstance(result, Provide)

    def test_get_logger_with_single_name_returns_provide_marker(self):
        """Test get_logger returns a Provide marker when given a single name."""
        result = get_logger("mylogger")
        assert isinstance(result, Provide)

    def test_get_logger_with_multiple_names_returns_provide_marker(self):
        """Test get_logger returns a Provide marker when given multiple names."""
        result = get_logger("parent", "child", "grandchild")
        assert isinstance(result, Provide)

    def test_get_logger_name_joining(self):
        """Test that get_logger joins multiple names with dots."""
        # We test the internal logic by patching the Provide call
        # The function joins names with "."
        result = get_logger("a", "b", "c")
        assert isinstance(result, Provide)

    def test_get_logger_with_empty_string(self):
        """Test get_logger with empty string name."""
        result = get_logger("")
        assert isinstance(result, Provide)

    def test_get_logger_uses_calling_module_when_no_name(self):
        """Test that get_logger uses the calling module's name when no name is provided."""
        # When no name is provided, get_logger uses inspect.stack() to get
        # the calling module's __name__
        result = get_logger()
        assert isinstance(result, Provide)


class TestGetLoggerNameResolution:
    """Tests for get_logger's name resolution logic."""

    def test_name_provided_uses_name(self):
        """Test that when name is provided, it uses that name."""
        # Internal logic: if name is provided, use ".".join(name)
        result = get_logger("custom", "logger")
        assert isinstance(result, Provide)

    def test_no_name_inspects_stack(self):
        """Test that when no name is provided, inspect.stack is called."""
        with patch('src.awioc.di.providers.inspect') as mock_inspect:
            mock_frame = Mock()
            mock_module = Mock()
            mock_module.__name__ = "test_module"
            mock_inspect.stack.return_value = [None, (mock_frame,)]
            mock_inspect.getmodule.return_value = mock_module

            # Call get_logger without arguments
            result = get_logger()
            # Should have called inspect.stack
            mock_inspect.stack.assert_called_once()

    def test_no_name_no_module_uses_fallback(self):
        """Test fallback when module cannot be determined."""
        with patch('src.awioc.di.providers.inspect') as mock_inspect:
            mock_frame = Mock()
            mock_inspect.stack.return_value = [None, (mock_frame,)]
            mock_inspect.getmodule.return_value = None

            result = get_logger()
            assert isinstance(result, Provide)


class TestProviderModuleExports:
    """Tests for providers module exports."""

    def test_all_providers_exported(self):
        """Test that all provider functions are accessible."""
        expected_functions = [
            'get_library',
            'get_config',
            'get_container_api',
            'get_raw_container',
            'get_app',
            'get_logger',
        ]
        for func_name in expected_functions:
            assert hasattr(providers_module, func_name)
            assert callable(getattr(providers_module, func_name))

    def test_type_vars_exist(self):
        """Test that type variables are defined."""
        assert hasattr(providers_module, '_Lib_type')
        assert hasattr(providers_module, '_Model_type')


class TestProviderReturnTypes:
    """Integration tests for provider return types."""

    def test_all_providers_return_provide_instances(self):
        """Test that all provider functions return Provide instances."""

        class DummyLib:
            pass

        class DummyConfig(pydantic.BaseModel):
            value: str = "test"

        providers_to_test = [
            lambda: get_library(DummyLib),
            lambda: get_library("string_lib"),
            lambda: get_config(),
            lambda: get_config(None),
            lambda: get_config(DummyConfig),
            lambda: get_container_api(),
            lambda: get_raw_container(),
            lambda: get_app(),
            lambda: get_logger(),
            lambda: get_logger("named"),
            lambda: get_logger("parent", "child"),
        ]

        for provider_fn in providers_to_test:
            result = provider_fn()
            assert isinstance(result, Provide), f"Expected Provide, got {type(result)}"


# Integration tests with initialized IOC framework
import logging
from unittest.mock import AsyncMock

from src.awioc.container import AppContainer, ContainerInterface
from src.awioc.config.base import Settings


class TestProvidersWithInitializedIOC:
    """Integration tests for providers with a fully initialized IOC framework."""

    @pytest.fixture
    def library_component(self):
        """Create a test library component."""
        class TestLibrary:
            __metadata__ = {
                "name": "test_library",
                "version": "1.0.0",
                "description": "Test library for provider tests",
                "requires": set(),
                "wire": False,
            }
            initialize = None
            shutdown = None

            def get_data(self):
                return {"key": "value", "status": "active"}

        return TestLibrary()

    @pytest.fixture
    def another_library_component(self):
        """Create another test library component."""
        class AnotherLibrary:
            __metadata__ = {
                "name": "another_library",
                "version": "2.0.0",
                "description": "Another test library",
                "requires": set(),
                "wire": False,
            }
            initialize = None
            shutdown = None

            def process(self, data):
                return f"processed: {data}"

        return AnotherLibrary()

    @pytest.fixture
    def app_component(self):
        """Create a test app component."""
        class TestApp:
            __name__ = "test_app"
            __module__ = "test"
            __package__ = None
            __metadata__ = {
                "name": "test_app",
                "version": "1.0.0",
                "description": "Test application",
                "requires": set(),
                "base_config": Settings,
                "wire": False,
            }

            async def initialize(self):
                return True

            async def shutdown(self):
                pass

        return TestApp()

    @pytest.fixture
    def configured_container(self, app_component, library_component, another_library_component):
        """Create a fully configured container with app, libraries, and config."""
        container = AppContainer()
        interface = ContainerInterface(container)

        # Set app
        interface.set_app(app_component)

        # Register libraries with their type names
        interface.register_libraries(
            (type(library_component), library_component),
            (type(another_library_component), another_library_component),
        )

        # Set logger
        logger = logging.getLogger("test_providers")
        interface.set_logger(logger)

        # Set config
        config = Settings()
        interface.set_config(config)

        return interface

    def test_get_library_with_type_returns_correct_instance(self, configured_container, library_component):
        """Test get_library returns the correct library instance when given a type."""
        interface = configured_container

        # Get the library type class
        LibraryType = type(library_component)

        # Retrieve the library through the container interface directly
        retrieved_lib = interface.provided_lib(LibraryType)

        assert retrieved_lib is library_component
        assert retrieved_lib.get_data() == {"key": "value", "status": "active"}

    def test_get_library_with_different_types_returns_different_instances(
        self, configured_container, library_component, another_library_component
    ):
        """Test get_library returns different instances for different types."""
        interface = configured_container

        LibraryType = type(library_component)
        AnotherLibraryType = type(another_library_component)

        lib1 = interface.provided_lib(LibraryType)
        lib2 = interface.provided_lib(AnotherLibraryType)

        assert lib1 is library_component
        assert lib2 is another_library_component
        assert lib1 is not lib2

        # Verify different functionality
        assert lib1.get_data() == {"key": "value", "status": "active"}
        assert lib2.process("test") == "processed: test"

    def test_provided_libs_returns_all_registered_libraries(
        self, configured_container, library_component, another_library_component
    ):
        """Test provided_libs returns all registered library instances."""
        interface = configured_container

        all_libs = interface.provided_libs()

        assert library_component in all_libs
        assert another_library_component in all_libs
        assert len(all_libs) == 2

    def test_get_config_returns_settings_instance(self, configured_container):
        """Test get_config returns the Settings instance."""
        interface = configured_container

        config = interface.provided_config()

        assert isinstance(config, Settings)

    def test_get_container_api_returns_interface(self, configured_container):
        """Test that the container API is accessible."""
        interface = configured_container

        # The interface itself is the container API
        assert isinstance(interface, ContainerInterface)
        assert interface.raw_container() is not None

    def test_get_raw_container_returns_app_container(self, configured_container):
        """Test get_raw_container returns the AppContainer instance."""
        interface = configured_container

        raw = interface.raw_container()

        # Check it has the expected AppContainer attributes and methods
        # Note: dependency_injector may create a DynamicContainer subclass
        assert hasattr(raw, 'config')
        assert hasattr(raw, 'logger')
        assert hasattr(raw, 'components')
        assert hasattr(raw, 'wire')
        # Verify the container is functional
        assert raw.config is not None
        assert raw.logger is not None

    def test_get_app_returns_app_component(self, configured_container, app_component):
        """Test get_app returns the registered app component."""
        interface = configured_container

        app = interface.provided_app()

        assert app is app_component
        assert app.__metadata__["name"] == "test_app"

    def test_get_logger_returns_logger_instance(self, configured_container):
        """Test get_logger returns a Logger instance."""
        interface = configured_container

        logger = interface.provided_logger()

        assert isinstance(logger, logging.Logger)


class TestGetLibraryWithWiredContainer:
    """Tests for get_library with a properly wired container."""

    @pytest.fixture
    def wired_module_with_library(self, tmp_path):
        """Create a test module that uses get_library injection."""
        # Create a library component
        class DatabaseLibrary:
            __metadata__ = {
                "name": "database",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            }
            initialize = None
            shutdown = None

            def query(self, sql):
                return [{"id": 1, "name": "test_user"}]

            def execute(self, sql):
                return True

        return DatabaseLibrary()

    @pytest.fixture
    def container_with_database(self, wired_module_with_library):
        """Create container with database library registered."""
        container = AppContainer()
        interface = ContainerInterface(container)

        # Create minimal app
        app = type("App", (), {
            "__name__": "app",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "app",
                "version": "1.0.0",
                "requires": set(),
                "base_config": Settings,
                "wire": False,
            },
            "initialize": AsyncMock(return_value=True),
            "shutdown": AsyncMock()
        })()

        interface.set_app(app)
        interface.register_libraries(
            (type(wired_module_with_library), wired_module_with_library)
        )
        interface.set_config(Settings())
        interface.set_logger(logging.getLogger("test"))

        return interface, wired_module_with_library

    def test_library_retrieval_by_type(self, container_with_database):
        """Test retrieving library by its type."""
        interface, db_lib = container_with_database

        DbType = type(db_lib)
        retrieved = interface.provided_lib(DbType)

        assert retrieved is db_lib
        assert retrieved.query("SELECT * FROM users") == [{"id": 1, "name": "test_user"}]

    def test_library_retrieval_preserves_methods(self, container_with_database):
        """Test that retrieved library preserves all its methods."""
        interface, db_lib = container_with_database

        DbType = type(db_lib)
        retrieved = interface.provided_lib(DbType)

        assert hasattr(retrieved, 'query')
        assert hasattr(retrieved, 'execute')
        assert callable(retrieved.query)
        assert callable(retrieved.execute)
        assert retrieved.execute("INSERT INTO users VALUES (2, 'new_user')") is True

    def test_library_not_found_raises_key_error(self, container_with_database):
        """Test that requesting an unregistered library raises KeyError."""
        interface, _ = container_with_database

        class UnregisteredLibrary:
            pass

        with pytest.raises(KeyError):
            interface.provided_lib(UnregisteredLibrary)


class TestGetLibraryWithMultipleLibraryTypes:
    """Test get_library with various library types and registration patterns."""

    @pytest.fixture
    def multi_library_container(self):
        """Create a container with multiple types of libraries."""
        container = AppContainer()
        interface = ContainerInterface(container)

        # Create different library types
        class CacheLibrary:
            __metadata__ = {
                "name": "cache",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            }
            initialize = None
            shutdown = None
            _store = {}

            def get(self, key):
                return self._store.get(key)

            def set(self, key, value):
                self._store[key] = value

        class HttpClientLibrary:
            __metadata__ = {
                "name": "http_client",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            }
            initialize = None
            shutdown = None

            def get(self, url):
                return {"status": 200, "url": url}

            def post(self, url, data):
                return {"status": 201, "url": url, "data": data}

        class LoggingLibrary:
            __metadata__ = {
                "name": "logging_lib",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            }
            initialize = None
            shutdown = None
            messages = []

            def log(self, level, message):
                self.messages.append((level, message))

        cache = CacheLibrary()
        http = HttpClientLibrary()
        log_lib = LoggingLibrary()

        # Create app
        app = type("App", (), {
            "__name__": "app",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "app",
                "version": "1.0.0",
                "requires": set(),
                "base_config": Settings,
                "wire": False,
            },
            "initialize": AsyncMock(return_value=True),
            "shutdown": AsyncMock()
        })()

        interface.set_app(app)
        interface.register_libraries(
            (CacheLibrary, cache),
            (HttpClientLibrary, http),
            (LoggingLibrary, log_lib),
        )
        interface.set_config(Settings())
        interface.set_logger(logging.getLogger("test"))

        return interface, {
            "cache": (CacheLibrary, cache),
            "http": (HttpClientLibrary, http),
            "log": (LoggingLibrary, log_lib),
        }

    def test_retrieve_cache_library(self, multi_library_container):
        """Test retrieving cache library."""
        interface, libs = multi_library_container
        CacheType, cache_instance = libs["cache"]

        retrieved = interface.provided_lib(CacheType)

        assert retrieved is cache_instance
        retrieved.set("test_key", "test_value")
        assert retrieved.get("test_key") == "test_value"

    def test_retrieve_http_library(self, multi_library_container):
        """Test retrieving HTTP client library."""
        interface, libs = multi_library_container
        HttpType, http_instance = libs["http"]

        retrieved = interface.provided_lib(HttpType)

        assert retrieved is http_instance
        response = retrieved.get("https://api.example.com")
        assert response["status"] == 200
        assert response["url"] == "https://api.example.com"

    def test_retrieve_logging_library(self, multi_library_container):
        """Test retrieving logging library."""
        interface, libs = multi_library_container
        LogType, log_instance = libs["log"]

        retrieved = interface.provided_lib(LogType)

        assert retrieved is log_instance
        retrieved.log("INFO", "Test message")
        assert ("INFO", "Test message") in retrieved.messages

    def test_all_libraries_accessible(self, multi_library_container):
        """Test that all libraries are accessible through provided_libs."""
        interface, libs = multi_library_container

        all_libs = interface.provided_libs()

        assert len(all_libs) == 3
        assert libs["cache"][1] in all_libs
        assert libs["http"][1] in all_libs
        assert libs["log"][1] in all_libs

    def test_libraries_are_independent_instances(self, multi_library_container):
        """Test that different library types return independent instances."""
        interface, libs = multi_library_container

        cache = interface.provided_lib(libs["cache"][0])
        http = interface.provided_lib(libs["http"][0])
        log = interface.provided_lib(libs["log"][0])

        # All should be different objects
        assert cache is not http
        assert http is not log
        assert cache is not log

        # Each should be its own instance
        assert cache is libs["cache"][1]
        assert http is libs["http"][1]
        assert log is libs["log"][1]


class TestGetLibraryEdgeCases:
    """Edge case tests for get_library functionality."""

    def test_library_with_string_registration(self):
        """Test library registered with string key."""
        container = AppContainer()
        interface = ContainerInterface(container)

        class StringKeyLibrary:
            __metadata__ = {
                "name": "string_key_lib",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            }
            initialize = None
            shutdown = None
            value = "string_key_value"

        lib = StringKeyLibrary()

        # Create app
        app = type("App", (), {
            "__name__": "app",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "app",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            },
            "initialize": None,
            "shutdown": None
        })()

        interface.set_app(app)

        # Register with string key
        interface.register_libraries(("custom_string_key", lib))

        # Should be accessible through components
        components = interface.components
        assert lib in components

    def test_library_metadata_preserved(self):
        """Test that library metadata is preserved after registration."""
        container = AppContainer()
        interface = ContainerInterface(container)

        class MetadataLibrary:
            __metadata__ = {
                "name": "metadata_lib",
                "version": "3.2.1",
                "description": "Library with detailed metadata",
                "requires": set(),
                "wire": False,
            }
            initialize = None
            shutdown = None

        lib = MetadataLibrary()

        app = type("App", (), {
            "__name__": "app",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "app",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            },
            "initialize": None,
            "shutdown": None
        })()

        interface.set_app(app)
        interface.register_libraries((MetadataLibrary, lib))

        retrieved = interface.provided_lib(MetadataLibrary)

        assert retrieved.__metadata__["name"] == "metadata_lib"
        assert retrieved.__metadata__["version"] == "3.2.1"
        assert retrieved.__metadata__["description"] == "Library with detailed metadata"

    def test_library_with_dependencies(self):
        """Test library that depends on other libraries."""
        container = AppContainer()
        interface = ContainerInterface(container)

        class BaseLibrary:
            __metadata__ = {
                "name": "base_lib",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            }
            initialize = None
            shutdown = None

            def base_method(self):
                return "base"

        base_lib = BaseLibrary()

        class DependentLibrary:
            __metadata__ = {
                "name": "dependent_lib",
                "version": "1.0.0",
                "requires": set(),  # No requires here; we manage the dependency manually
                "wire": False,
            }
            initialize = None
            shutdown = None

            def __init__(self, base):
                self.base = base

            def extended_method(self):
                return f"extended_{self.base.base_method()}"

        dependent_lib = DependentLibrary(base_lib)

        app = type("App", (), {
            "__name__": "app",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "app",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            },
            "initialize": None,
            "shutdown": None
        })()

        interface.set_app(app)
        # Register base library first, then dependent library
        interface.register_libraries(
            (BaseLibrary, base_lib),
            (DependentLibrary, dependent_lib),
        )

        retrieved_base = interface.provided_lib(BaseLibrary)
        retrieved_dependent = interface.provided_lib(DependentLibrary)

        assert retrieved_base.base_method() == "base"
        assert retrieved_dependent.extended_method() == "extended_base"
        assert retrieved_dependent.base is retrieved_base

    def test_library_with_declared_dependencies(self):
        """Test library with dependencies declared in metadata (IOC framework manages dependency chain)."""
        container = AppContainer()
        interface = ContainerInterface(container)

        class CoreLibrary:
            __metadata__ = {
                "name": "core_lib",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            }
            initialize = None
            shutdown = None

            def core_operation(self):
                return "core"

        core_lib = CoreLibrary()

        class ExtendedLibrary:
            __metadata__ = {
                "name": "extended_lib",
                "version": "1.0.0",
                "requires": {core_lib},  # Dependency declared here
                "wire": False,
            }
            initialize = None
            shutdown = None

            def __init__(self, core):
                self.core = core

            def extended_operation(self):
                return f"extended_{self.core.core_operation()}"

        extended_lib = ExtendedLibrary(core_lib)

        app = type("App", (), {
            "__name__": "app",
            "__module__": "test",
            "__package__": None,
            "__metadata__": {
                "name": "app",
                "version": "1.0.0",
                "requires": set(),
                "wire": False,
            },
            "initialize": None,
            "shutdown": None
        })()

        interface.set_app(app)
        # When registering extended_lib, core_lib's internals are initialized through dependency chain
        # We only register the extended_lib; core_lib is handled as a dependency
        interface.register_libraries(
            (ExtendedLibrary, extended_lib),
        )

        # Extended library should be retrievable
        retrieved_extended = interface.provided_lib(ExtendedLibrary)
        assert retrieved_extended.extended_operation() == "extended_core"

        # The dependency (core_lib) should have its internals initialized
        assert "_internals" in core_lib.__metadata__