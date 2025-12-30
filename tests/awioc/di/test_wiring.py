from types import ModuleType
from unittest.mock import MagicMock

import pydantic
import pytest

from src.awioc.config.registry import _CONFIGURATIONS, clear_configurations
from src.awioc.container import AppContainer, ContainerInterface
from src.awioc.di.wiring import wire, inject_dependencies


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

    def test_inject_dependencies_uses_all_components_when_none(self, container_interface):
        """Test inject_dependencies uses all container components when components is None."""
        clear_configurations()

        class TestConfig(pydantic.BaseModel):
            value: str = "test"

        class AppComponent:
            __name__ = "app"
            __module__ = "test"
            __package__ = None
            __metadata__ = {
                "name": "test_app",
                "version": "1.0.0",
                "requires": set(),
                "config": {TestConfig}
            }

            async def initialize(self):
                pass

            async def shutdown(self):
                pass

        container_interface.set_app(AppComponent())

        # Call without specifying components - should use container.components
        inject_dependencies(container_interface, components=None)

        assert "test_app" in _CONFIGURATIONS


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
        import sys
        from types import ModuleType

        # Create fake modules
        fake_component = ModuleType("my_package.component")
        fake_submodule = ModuleType("my_package.submodule")
        fake_another = ModuleType("my_package.another")
        sys.modules["my_package.component"] = fake_component
        sys.modules["my_package.submodule"] = fake_submodule
        sys.modules["my_package.another"] = fake_another

        try:
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
            module_names = {m.__name__ for m in modules}
            assert "my_package.submodule" in module_names
            assert "my_package.another" in module_names
        finally:
            del sys.modules["my_package.component"]
            del sys.modules["my_package.submodule"]
            del sys.modules["my_package.another"]

    def test_wire_handles_string_wirings(self, container_interface):
        """Test wire with string wirings (not iterable check)."""
        import sys
        from types import ModuleType

        # Create fake modules
        fake_str_module = ModuleType("str_module")
        fake_single_module = ModuleType("pkg.single_module")
        sys.modules["str_module"] = fake_str_module
        sys.modules["pkg.single_module"] = fake_single_module

        try:
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
            module_names = {m.__name__ for m in modules}
            assert "pkg.single_module" in module_names
        finally:
            del sys.modules["str_module"]
            del sys.modules["pkg.single_module"]

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

    def test_wire_derives_package_from_module_for_package_components(self, container_interface):
        """Test wire derives package correctly when component is in a package (__init__.py)."""
        import sys
        from types import ModuleType

        # Create a fake module that is a package (has __path__)
        fake_package = ModuleType("myapp.components.mycomponent")
        fake_package.__path__ = ["/fake/path"]  # Makes it a package
        fake_logic = ModuleType("myapp.components.mycomponent.logic")
        fake_routes = ModuleType("myapp.components.mycomponent.routes")
        sys.modules["myapp.components.mycomponent"] = fake_package
        sys.modules["myapp.components.mycomponent.logic"] = fake_logic
        sys.modules["myapp.components.mycomponent.routes"] = fake_routes

        try:
            class PackageComponent:
                __name__ = "MyComponent"
                __module__ = "myapp.components.mycomponent"  # Component defined in __init__.py
                # No __package__ attribute set
                __metadata__ = {
                    "name": "mycomponent",
                    "version": "1.0.0",
                    "wire": True,
                    "wirings": {"logic", "routes"}  # Should resolve to myapp.components.mycomponent.logic
                }

            container_interface.raw_container().wire = MagicMock()

            wire(container_interface, components=[PackageComponent()])

            call_args = container_interface.raw_container().wire.call_args
            modules = call_args.kwargs.get('modules', set())
            module_names = {m.__name__ for m in modules}
            # Wirings should be relative to the package itself, not its parent
            assert "myapp.components.mycomponent.logic" in module_names
            assert "myapp.components.mycomponent.routes" in module_names
        finally:
            # Clean up
            del sys.modules["myapp.components.mycomponent"]
            del sys.modules["myapp.components.mycomponent.logic"]
            del sys.modules["myapp.components.mycomponent.routes"]

    def test_wire_derives_package_from_module_for_file_components(self, container_interface):
        """Test wire derives package correctly when component is in a regular file."""
        import sys
        from types import ModuleType

        # Create a fake module that is NOT a package (no __path__)
        fake_module = ModuleType("myapp.components.mycomponent")
        fake_logic = ModuleType("myapp.components.logic")
        fake_routes = ModuleType("myapp.components.routes")
        # No __path__ attribute - it's a regular .py file
        sys.modules["myapp.components.mycomponent"] = fake_module
        sys.modules["myapp.components.logic"] = fake_logic
        sys.modules["myapp.components.routes"] = fake_routes

        try:
            class FileComponent:
                __name__ = "MyComponent"
                __module__ = "myapp.components.mycomponent"  # Component defined in mycomponent.py
                # No __package__ attribute set
                __metadata__ = {
                    "name": "mycomponent",
                    "version": "1.0.0",
                    "wire": True,
                    "wirings": {"logic", "routes"}  # Should resolve to myapp.components.logic
                }

            container_interface.raw_container().wire = MagicMock()

            wire(container_interface, components=[FileComponent()])

            call_args = container_interface.raw_container().wire.call_args
            modules = call_args.kwargs.get('modules', set())
            module_names = {m.__name__ for m in modules}
            # Wirings should be relative to the parent package
            assert "myapp.components.logic" in module_names
            assert "myapp.components.routes" in module_names
        finally:
            # Clean up
            del sys.modules["myapp.components.mycomponent"]
            del sys.modules["myapp.components.logic"]
            del sys.modules["myapp.components.routes"]
