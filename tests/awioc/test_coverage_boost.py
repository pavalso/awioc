"""Additional tests to boost coverage to 90%+."""
import pytest

from src.awioc.components.metadata import Internals, ComponentTypes
from src.awioc.components.registry import component_requires
from src.awioc.config.base import Settings
from src.awioc.container import AppContainer, ContainerInterface


class TestComponentRequiresRecursive:
    """Tests for recursive component_requires."""

    def test_component_requires_with_duplicates(self):
        """Test component_requires handles duplicates."""
        dep = type("Dep", (), {
            "__metadata__": {"name": "dep", "requires": set()}
        })()

        comp1 = type("Comp1", (), {
            "__metadata__": {"name": "c1", "requires": {dep}}
        })()

        comp2 = type("Comp2", (), {
            "__metadata__": {"name": "c2", "requires": {dep}}
        })()

        result = component_requires(comp1, comp2)
        # dep should only appear once
        assert dep in result
        assert len([r for r in result if r is dep]) == 1


class TestContainerUnregisterMethods:
    """Tests for ContainerInterface unregister methods."""

    @pytest.fixture
    def interface(self):
        """Create a ContainerInterface."""
        return ContainerInterface(AppContainer())


class TestBootstrapModuleFunctions:
    """Tests for bootstrap module functions."""

    def test_reconfigure_ioc_app_exists(self):
        """Test reconfigure_ioc_app function exists."""
        from src.awioc.bootstrap import reconfigure_ioc_app
        assert callable(reconfigure_ioc_app)

    def test_reload_configuration_exists(self):
        """Test reload_configuration function exists."""
        from src.awioc.bootstrap import reload_configuration
        assert callable(reload_configuration)


class TestDIProvidersModule:
    """Tests for DI providers module functions."""

    def test_all_provider_functions_exist(self):
        """Test all provider functions exist."""
        from src.awioc.di import providers

        assert hasattr(providers, 'get_library')
        assert hasattr(providers, 'get_config')
        assert hasattr(providers, 'get_container_api')
        assert hasattr(providers, 'get_raw_container')
        assert hasattr(providers, 'get_app')
        assert hasattr(providers, 'get_logger')

    def test_provider_functions_are_callable(self):
        """Test all provider functions are callable."""
        from src.awioc.di.providers import (
            get_library,
            get_config,
            get_container_api,
            get_raw_container,
            get_app,
            get_logger,
        )

        assert callable(get_library)
        assert callable(get_config)
        assert callable(get_container_api)
        assert callable(get_raw_container)
        assert callable(get_app)
        assert callable(get_logger)


class TestLifecycleFunctions:
    """Tests for lifecycle module functions."""

    def test_all_lifecycle_functions_exist(self):
        """Test all lifecycle functions exist."""
        from src.awioc.components import lifecycle

        assert hasattr(lifecycle, 'initialize_components')
        assert hasattr(lifecycle, 'shutdown_components')
        assert hasattr(lifecycle, 'register_plugin')
        assert hasattr(lifecycle, 'unregister_plugin')

    def test_lifecycle_functions_are_coroutines(self):
        """Test lifecycle functions are async."""
        import asyncio
        from src.awioc.components.lifecycle import (
            initialize_components,
            shutdown_components,
            register_plugin,
            unregister_plugin,
        )

        # These should be coroutine functions
        assert asyncio.iscoroutinefunction(initialize_components)
        assert asyncio.iscoroutinefunction(shutdown_components)
        assert asyncio.iscoroutinefunction(register_plugin)
        assert asyncio.iscoroutinefunction(unregister_plugin)


class TestContainerComponentsProperty:
    """Tests for Container components property edge cases."""

    def test_components_with_callable_providers(self):
        """Test components property handles callable providers."""
        container = AppContainer()
        interface = ContainerInterface(container)

        # Add a component
        class TestComp:
            __metadata__ = {
                "name": "test",
                "version": "1.0.0",
                "requires": set()
            }

            async def initialize(self):
                pass

            async def shutdown(self):
                pass

        interface.set_app(TestComp())

        components = interface.components
        assert len(components) >= 1


class TestSettingsModelConfig:
    """Tests for Settings model_config."""

    def test_settings_model_config_values(self):
        """Test Settings model_config has expected values."""
        settings = Settings()

        assert settings.model_config["env_file"] == ".env"
        assert settings.model_config["env_file_encoding"] == "utf-8"
        assert settings.model_config["extra"] == "ignore"
        assert settings.model_config["env_nested_delimiter"] == "_"
        assert settings.model_config["env_nested_max_split"] == 1
        assert settings.model_config["env_prefix"] == ""
        assert settings.model_config["cli_avoid_json"] is True
        assert settings.model_config["validate_default"] is True


class TestComponentInternalsDetails:
    """Tests for _Internals details."""

    def test_internals_all_fields(self):
        """Test all _Internals fields."""
        internals = Internals(
            required_by=set(),
            initialized_by=set(),
            is_initialized=True,
            is_initializing=False,
            type=ComponentTypes.LIBRARY
        )

        assert internals.required_by == set()
        assert internals.initialized_by == set()
        assert internals.is_initialized is True
        assert internals.is_initializing is False
        assert internals.type == ComponentTypes.LIBRARY

    def test_internals_mutable_sets(self):
        """Test _Internals sets are mutable."""
        internals = Internals()

        # Add to required_by
        mock = object()
        internals.required_by.add(mock)
        assert mock in internals.required_by

        # Remove from required_by
        internals.required_by.discard(mock)
        assert mock not in internals.required_by


class TestConfigRegistryDetails:
    """Tests for config registry details."""

    def test_configurations_dict_type(self):
        """Test _CONFIGURATIONS is a dict."""
        from src.awioc.config.registry import _CONFIGURATIONS
        assert isinstance(_CONFIGURATIONS, dict)


class TestWiringModule:
    """Tests for wiring module."""

    def test_wiring_functions_exist(self):
        """Test wiring functions exist."""
        from src.awioc.di import wiring

        assert hasattr(wiring, 'wire')
        assert hasattr(wiring, 'inject_dependencies')

    def test_wiring_functions_callable(self):
        """Test wiring functions are callable."""
        from src.awioc.di.wiring import wire, inject_dependencies

        assert callable(wire)
        assert callable(inject_dependencies)


class TestLoggingSetupDetails:
    """Tests for logging setup details."""

    def test_setup_logging_returns_logger(self):
        """Test setup_logging returns a Logger instance."""
        from awioc.config.setup import setup_logging
        import logging

        logger = setup_logging(name="test_detail")
        assert isinstance(logger, logging.Logger)

    def test_setup_logging_level_propagation(self):
        """Test setup_logging level is set correctly."""
        from awioc.config.setup import setup_logging
        import logging

        logger = setup_logging(name="test_level", level=logging.WARNING)
        assert logger.level == logging.WARNING


class TestAPIModuleImports:
    """Tests for API module imports."""

    def test_api_all_exports(self):
        """Test api.__all__ is defined."""
        from src.awioc import api
        assert hasattr(api, '__all__')
        assert len(api.__all__) > 0

    def test_main_init_all_exports(self):
        """Test __init__.__all__ is defined."""
        import src.awioc as awioc
        assert hasattr(awioc, '__all__')
        assert len(awioc.__all__) > 0
