import pytest
from types import ModuleType
from unittest.mock import MagicMock, patch

import pydantic

from src.ioc.di.wiring import wire, inject_dependencies
from src.ioc.container import AppContainer, ContainerInterface
from src.ioc.config.registry import _CONFIGURATIONS, register_configuration, clear_configurations


class TestInjectDependencies:
    """Tests for _inject_dependencies function."""

    @pytest.fixture
    def container_interface(self):
        """Create a container interface for testing."""
        return ContainerInterface(AppContainer())

    def test_inject_registers_component_configs(self, container_interface):
        """Test that component configs are registered."""
        clear_configurations()

        class ComponentConfig(pydantic.BaseModel):
            setting: str = "default"

        class MockComponent:
            __metadata__ = {
                "name": "test_comp",
                "version": "1.0.0",
                "config": {ComponentConfig}
            }

        inject_dependencies(container_interface, components=[MockComponent()])

        assert "test_comp" in _CONFIGURATIONS

    def test_inject_uses_prefix_from_config(self, container_interface):
        """Test that __prefix__ attribute is used if present."""
        clear_configurations()

        class PrefixedConfig(pydantic.BaseModel):
            __prefix__ = "custom_prefix"
            value: int = 42

        class MockComponent:
            __metadata__ = {
                "name": "comp",
                "version": "1.0.0",
                "config": {PrefixedConfig}
            }

        inject_dependencies(container_interface, components=[MockComponent()])

        assert "custom_prefix" in _CONFIGURATIONS

    def test_inject_handles_single_config(self, container_interface):
        """Test handling single config (not iterable)."""
        clear_configurations()

        class SingleConfig(pydantic.BaseModel):
            pass

        class MockComponent:
            __metadata__ = {
                "name": "single_comp",
                "version": "1.0.0",
                "config": SingleConfig  # Not a set
            }

        inject_dependencies(container_interface, components=[MockComponent()])

        assert "single_comp" in _CONFIGURATIONS

    def test_inject_handles_no_config(self, container_interface):
        """Test component without config."""
        clear_configurations()

        class NoConfigComponent:
            __metadata__ = {
                "name": "no_config",
                "version": "1.0.0"
            }

        # Should not raise
        inject_dependencies(container_interface, components=[NoConfigComponent()])

    def test_inject_with_empty_config_set(self, container_interface):
        """Test component with empty config set."""
        clear_configurations()

        class EmptyConfigComponent:
            __metadata__ = {
                "name": "empty",
                "version": "1.0.0",
                "config": set()
            }

        # Should not raise
        inject_dependencies(container_interface, components=[EmptyConfigComponent()])


class TestWire:
    """Tests for wire function."""

    @pytest.fixture
    def container_interface(self):
        """Create a container interface for testing."""
        return ContainerInterface(AppContainer())

    def test_wire_collects_module_wirings(self, container_interface):
        """Test that wire collects module names for wiring."""
        class MockComponent:
            __name__ = "mock_module"
            __module__ = "test_module"
            __package__ = None
            __metadata__ = {
                "name": "mock",
                "version": "1.0.0",
                "wire": True,
                "wirings": set()
            }

        # Mock the container's wire method
        container_interface.raw_container().wire = MagicMock()

        wire(container_interface, components=[MockComponent()])

        container_interface.raw_container().wire.assert_called_once()

    def test_wire_respects_wire_false(self, container_interface):
        """Test that wire=False skips the component."""
        class NoWireComponent:
            __name__ = "no_wire"
            __module__ = "no_wire_module"
            __package__ = None
            __metadata__ = {
                "name": "no_wire",
                "version": "1.0.0",
                "wire": False
            }

        container_interface.raw_container().wire = MagicMock()

        wire(container_interface, components=[NoWireComponent()])

        # Should still be called but without the no_wire module
        call_args = container_interface.raw_container().wire.call_args
        modules = call_args.kwargs.get('modules', set())
        assert "no_wire_module" not in modules

    def test_wire_handles_module_type_components(self, container_interface):
        """Test wiring ModuleType components."""
        mock_module = ModuleType("test_module")
        mock_module.__metadata__ = {
            "name": "test",
            "version": "1.0.0",
            "wire": True,
            "wirings": set()
        }
        mock_module.__package__ = None

        container_interface.raw_container().wire = MagicMock()

        wire(container_interface, components=[mock_module])

        container_interface.raw_container().wire.assert_called_once()

    def test_wire_with_relative_wirings(self, container_interface):
        """Test wire with relative wirings."""
        class ComponentWithWirings:
            __name__ = "comp"
            __module__ = "my_package.component"
            __package__ = "my_package"
            __metadata__ = {
                "name": "comp",
                "version": "1.0.0",
                "wire": True,
                "wirings": {"submodule", "another"}
            }

        container_interface.raw_container().wire = MagicMock()

        wire(container_interface, components=[ComponentWithWirings()])

        call_args = container_interface.raw_container().wire.call_args
        modules = call_args.kwargs.get('modules', set())
        assert "my_package.submodule" in modules
        assert "my_package.another" in modules

    def test_wire_handles_string_wirings(self, container_interface):
        """Test wire with string wirings (not iterable check)."""
        class StringWiring:
            __name__ = "str_wire"
            __module__ = "str_module"
            __package__ = "pkg"
            __metadata__ = {
                "name": "str",
                "version": "1.0.0",
                "wire": True,
                "wirings": "single_module"  # String, not set
            }

        container_interface.raw_container().wire = MagicMock()

        wire(container_interface, components=[StringWiring()])

        call_args = container_interface.raw_container().wire.call_args
        modules = call_args.kwargs.get('modules', set())
        assert "pkg.single_module" in modules

    def test_wire_uses_all_components_when_none_specified(self, container_interface):
        """Test wire uses all components when none specified."""
        # Set up a component in the interface
        class AppComponent:
            __name__ = "app"
            __module__ = "test_app"
            __package__ = None
            __metadata__ = {
                "name": "app",
                "version": "1.0.0",
                "requires": set(),
                "wire": True,
                "wirings": set()
            }

            async def initialize(self):
                pass

            async def shutdown(self):
                pass

        container_interface.set_app(AppComponent())
        container_interface.raw_container().wire = MagicMock()

        wire(container_interface, components=None)

        container_interface.raw_container().wire.assert_called_once()
