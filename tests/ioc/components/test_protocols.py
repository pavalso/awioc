import pytest
from typing import runtime_checkable

from src.ioc.components.protocols import (
    Component,
    AppComponent,
    PluginComponent,
    LibraryComponent,
)


class TestComponentProtocol:
    """Tests for Component protocol."""

    def test_component_is_runtime_checkable(self):
        """Test Component protocol is runtime checkable."""
        assert hasattr(Component, "__protocol_attrs__") or runtime_checkable

    def test_valid_component(self):
        """Test that a valid class implements Component."""
        class ValidComponent:
            __metadata__ = {
                "name": "valid",
                "version": "1.0.0",
                "description": "Valid component"
            }
            initialize = None
            shutdown = None

        assert isinstance(ValidComponent(), Component)

    def test_component_with_coroutines(self):
        """Test component with async initialize/shutdown."""
        class AsyncComponent:
            __metadata__ = {"name": "async", "version": "1.0.0", "description": ""}

            async def initialize(self):
                return True

            async def shutdown(self):
                pass

        comp = AsyncComponent()
        assert isinstance(comp, Component)

    def test_missing_metadata_not_component(self):
        """Test class without __metadata__ is not a Component."""
        class NoMetadata:
            initialize = None
            shutdown = None

        assert not isinstance(NoMetadata(), Component)


class TestAppComponentProtocol:
    """Tests for AppComponent protocol."""

    def test_valid_app_component(self):
        """Test a valid AppComponent implementation."""
        class ValidApp:
            __metadata__ = {
                "name": "app",
                "version": "1.0.0",
                "description": "App",
                "base_config": None
            }

            async def initialize(self):
                return True

            async def shutdown(self):
                pass

        assert isinstance(ValidApp(), AppComponent)

    def test_app_component_is_component(self):
        """Test AppComponent is also a Component."""
        class App:
            __metadata__ = {"name": "app", "version": "1.0.0", "description": ""}

            async def initialize(self):
                pass

            async def shutdown(self):
                pass

        app = App()
        assert isinstance(app, Component)
        assert isinstance(app, AppComponent)


class TestPluginComponentProtocol:
    """Tests for PluginComponent protocol."""

    def test_valid_plugin_component(self):
        """Test a valid PluginComponent implementation."""
        class ValidPlugin:
            __metadata__ = {"name": "plugin", "version": "1.0.0", "description": ""}
            initialize = None
            shutdown = None

        assert isinstance(ValidPlugin(), PluginComponent)

    def test_plugin_is_component(self):
        """Test PluginComponent is also a Component."""
        class Plugin:
            __metadata__ = {"name": "plugin", "version": "1.0.0", "description": ""}
            initialize = None
            shutdown = None

        plugin = Plugin()
        assert isinstance(plugin, Component)
        assert isinstance(plugin, PluginComponent)


class TestLibraryComponentProtocol:
    """Tests for LibraryComponent protocol."""

    def test_valid_library_component(self):
        """Test a valid LibraryComponent implementation."""
        class ValidLibrary:
            __metadata__ = {"name": "lib", "version": "1.0.0", "description": ""}
            initialize = None
            shutdown = None

        assert isinstance(ValidLibrary(), LibraryComponent)

    def test_library_is_component(self):
        """Test LibraryComponent is also a Component."""
        class Library:
            __metadata__ = {"name": "lib", "version": "1.0.0", "description": ""}
            initialize = None
            shutdown = None

        lib = Library()
        assert isinstance(lib, Component)
        assert isinstance(lib, LibraryComponent)
