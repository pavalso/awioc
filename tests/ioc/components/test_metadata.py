import pytest

from src.ioc.components.metadata import (
    ComponentTypes,
    Internals,
    ComponentMetadata,
    AppMetadata,
)


class TestComponentTypes:
    """Tests for ComponentTypes enum."""

    def test_app_type(self):
        """Test APP component type."""
        assert ComponentTypes.APP.value == "app"

    def test_plugin_type(self):
        """Test PLUGIN component type."""
        assert ComponentTypes.PLUGIN.value == "plugin"

    def test_library_type(self):
        """Test LIBRARY component type."""
        assert ComponentTypes.LIBRARY.value == "library"

    def test_component_type(self):
        """Test COMPONENT component type."""
        assert ComponentTypes.COMPONENT.value == "component"

    def test_all_types_defined(self):
        """Test all expected component types are defined."""
        types = [t.value for t in ComponentTypes]
        assert "app" in types
        assert "plugin" in types
        assert "library" in types
        assert "component" in types


class TestInternals:
    """Tests for _Internals dataclass."""

    def test_default_values(self):
        """Test default values for _Internals."""
        internals = Internals()
        assert internals.required_by == set()
        assert internals.initialized_by == set()
        assert internals.is_initialized is False
        assert internals.is_initializing is False
        assert internals.type == ComponentTypes.COMPONENT

    def test_custom_values(self):
        """Test _Internals with custom values."""
        internals = Internals(
            is_initialized=True,
            is_initializing=False,
            type=ComponentTypes.PLUGIN
        )
        assert internals.is_initialized is True
        assert internals.type == ComponentTypes.PLUGIN

    def test_required_by_modification(self):
        """Test modifying required_by set."""
        internals = Internals()
        mock_component = type("MockComponent", (), {"__metadata__": {}})()
        internals.required_by.add(mock_component)
        assert mock_component in internals.required_by

    def test_initialized_by_modification(self):
        """Test modifying initialized_by set."""
        internals = Internals()
        mock_component = type("MockComponent", (), {"__metadata__": {}})()
        internals.initialized_by.add(mock_component)
        assert mock_component in internals.initialized_by


class TestComponentMetadata:
    """Tests for ComponentMetadata TypedDict."""

    def test_component_metadata_structure(self):
        """Test ComponentMetadata can hold expected fields."""
        metadata: ComponentMetadata = {
            "name": "test_component",
            "version": "1.0.0",
            "description": "A test component",
            "wire": True,
            "wirings": {"module1", "module2"},
            "requires": set(),
            "config": None,
            "_internals": None
        }
        assert metadata["name"] == "test_component"
        assert metadata["version"] == "1.0.0"
        assert metadata["wire"] is True

    def test_component_metadata_minimal(self):
        """Test ComponentMetadata with minimal fields."""
        metadata: ComponentMetadata = {
            "name": "minimal",
            "version": "0.1.0",
            "description": "",
            "wire": None,
            "wirings": None,
            "requires": None,
            "config": None,
            "_internals": None
        }
        assert metadata["name"] == "minimal"


class TestAppMetadata:
    """Tests for AppMetadata TypedDict."""

    def test_app_metadata_with_base_config(self):
        """Test AppMetadata includes base_config field."""
        from src.ioc.config.base import Settings

        metadata: AppMetadata = {
            "name": "test_app",
            "version": "1.0.0",
            "description": "A test app",
            "wire": True,
            "wirings": None,
            "requires": None,
            "config": None,
            "_internals": None,
            "base_config": Settings
        }
        assert metadata["base_config"] == Settings

    def test_app_metadata_extends_component_metadata(self):
        """Test AppMetadata has all ComponentMetadata fields."""
        metadata: AppMetadata = {
            "name": "app",
            "version": "2.0.0",
            "description": "Main app",
            "wire": False,
            "wirings": set(),
            "requires": set(),
            "config": set(),
            "_internals": None,
            "base_config": None
        }
        # All ComponentMetadata fields should be present
        assert "name" in metadata
        assert "version" in metadata
        assert "description" in metadata
        assert "base_config" in metadata
