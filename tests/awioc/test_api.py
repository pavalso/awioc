import pytest

from src.awioc import api


class TestApiExports:
    """Tests for API module exports."""

    def test_container_exports(self):
        """Test container-related exports."""
        assert hasattr(api, 'ContainerInterface')
        assert hasattr(api, 'AppContainer')

    def test_component_exports(self):
        """Test component-related exports."""
        assert hasattr(api, 'Component')
        assert hasattr(api, 'AppComponent')
        assert hasattr(api, 'PluginComponent')
        assert hasattr(api, 'LibraryComponent')
        assert hasattr(api, 'ComponentMetadata')
        assert hasattr(api, 'AppMetadata')
        assert hasattr(api, 'ComponentTypes')

    def test_component_registry_exports(self):
        """Test component registry exports."""
        assert hasattr(api, 'as_component')
        assert hasattr(api, 'component_requires')
        assert hasattr(api, 'component_internals')
        assert hasattr(api, 'component_str')

    def test_lifecycle_exports(self):
        """Test lifecycle exports."""
        assert hasattr(api, 'initialize_components')
        assert hasattr(api, 'shutdown_components')
        assert hasattr(api, 'register_plugin')
        assert hasattr(api, 'unregister_plugin')

    def test_di_exports(self):
        """Test DI-related exports."""
        assert hasattr(api, 'get_library')
        assert hasattr(api, 'get_config')
        assert hasattr(api, 'get_container_api')
        assert hasattr(api, 'get_raw_container')
        assert hasattr(api, 'get_app')
        assert hasattr(api, 'get_logger')
        assert hasattr(api, 'wire')

    def test_config_exports(self):
        """Test config-related exports."""
        assert hasattr(api, 'Settings')
        assert hasattr(api, 'register_configuration')
        assert hasattr(api, 'clear_configurations')
        assert hasattr(api, 'load_file')
        assert hasattr(api, 'IOCComponentsDefinition')
        assert hasattr(api, 'IOCBaseConfig')

    def test_bootstrap_exports(self):
        """Test bootstrap exports."""
        assert hasattr(api, 'initialize_ioc_app')
        assert hasattr(api, 'create_container')
        assert hasattr(api, 'compile_ioc_app')
        assert hasattr(api, 'reconfigure_ioc_app')
        assert hasattr(api, 'reload_configuration')

    def test_loader_exports(self):
        """Test loader exports."""
        assert hasattr(api, 'compile_component')

    def test_logging_exports(self):
        """Test logging exports."""
        assert hasattr(api, 'setup_logging')


class TestModuleInit:
    """Tests for package __init__ exports."""

    def test_imports_from_init(self):
        """Test that all exports are available from src.awioc."""
        import src.awioc as awioc

        # Bootstrap
        assert hasattr(awioc, 'initialize_ioc_app')
        assert hasattr(awioc, 'create_container')

        # Lifecycle
        assert hasattr(awioc, 'initialize_components')
        assert hasattr(awioc, 'shutdown_components')

        # DI
        assert hasattr(awioc, 'get_library')
        assert hasattr(awioc, 'get_config')
        assert hasattr(awioc, 'get_logger')

        # Config
        assert hasattr(awioc, 'Settings')
        assert hasattr(awioc, 'register_configuration')

        # Components
        assert hasattr(awioc, 'Component')
        assert hasattr(awioc, 'AppComponent')

    def test_all_list_complete(self):
        """Test that __all__ list matches actual exports."""
        import src.awioc as awioc

        for name in awioc.__all__:
            assert hasattr(awioc, name), f"Missing export: {name}"
