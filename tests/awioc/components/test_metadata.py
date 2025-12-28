from datetime import datetime

from pydantic import BaseModel

from src.awioc.components.metadata import (
    ComponentTypes,
    Internals,
    ComponentMetadata,
    AppMetadata,
    RegistrationInfo,
    metadata,
)
from src.awioc.config.base import Settings


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
        from src.awioc.config.base import Settings

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


class TestRegistrationInfo:
    """Tests for RegistrationInfo dataclass."""

    def test_registration_info_str_minimal(self):
        """Test __str__ with minimal fields."""
        reg = RegistrationInfo(
            registered_by="test_module",
            registered_at=datetime(2024, 1, 15, 10, 30, 0)
        )
        result = str(reg)
        assert "by 'test_module'" in result
        assert "2024-01-15" in result

    def test_registration_info_str_with_file(self):
        """Test __str__ with file but no line number."""
        reg = RegistrationInfo(
            registered_by="test_module",
            registered_at=datetime(2024, 1, 15, 10, 30, 0),
            file="/path/to/file.py"
        )
        result = str(reg)
        assert "by 'test_module'" in result
        assert "from /path/to/file.py" in result

    def test_registration_info_str_with_file_and_line(self):
        """Test __str__ with file and line number."""
        reg = RegistrationInfo(
            registered_by="test_module",
            registered_at=datetime(2024, 1, 15, 10, 30, 0),
            file="/path/to/file.py",
            line=42
        )
        result = str(reg)
        assert "by 'test_module'" in result
        assert "from /path/to/file.py:42" in result

    def test_registration_info_str_format(self):
        """Test __str__ returns properly formatted string."""
        reg = RegistrationInfo(
            registered_by="my_component",
            registered_at=datetime(2024, 6, 20, 14, 0, 0),
            file="component.py",
            line=100
        )
        result = str(reg)
        assert result.startswith("RegistrationInfo(")
        assert result.endswith(")")


class TestMetadataFunction:
    """Tests for metadata() function."""

    def test_metadata_minimal(self):
        """Test metadata with minimal required fields."""
        meta = metadata(
            name="test",
            version="1.0.0",
            description="Test component"
        )
        assert meta["name"] == "test"
        assert meta["version"] == "1.0.0"
        assert meta["description"] == "Test component"
        assert meta["wire"] is True
        assert meta["wirings"] == set()
        assert meta["requires"] == set()
        assert meta["config"] == set()
        assert meta["_internals"] is None

    def test_metadata_with_wirings_list(self):
        """Test metadata with wirings as a list (converts to set)."""
        meta = metadata(
            name="test",
            version="1.0.0",
            description="Test",
            wirings=["module1", "module2"]
        )
        assert meta["wirings"] == {"module1", "module2"}
        assert isinstance(meta["wirings"], set)

    def test_metadata_with_requires_list(self):
        """Test metadata with requires as a list (converts to set)."""
        mock_component = type("MockComponent", (), {"__metadata__": {}})()

        meta = metadata(
            name="test",
            version="1.0.0",
            description="Test",
            requires=[mock_component]
        )
        assert mock_component in meta["requires"]
        assert isinstance(meta["requires"], set)

    def test_metadata_with_single_config_model(self):
        """Test metadata with a single config model (wraps in set)."""

        class MyConfig(BaseModel):
            value: str = "default"

        meta = metadata(
            name="test",
            version="1.0.0",
            description="Test",
            config=MyConfig
        )
        assert MyConfig in meta["config"]
        assert len(meta["config"]) == 1
        assert isinstance(meta["config"], set)

    def test_metadata_with_multiple_config_models(self):
        """Test metadata with multiple config models as list."""

        class Config1(BaseModel):
            a: str = ""

        class Config2(BaseModel):
            b: int = 0

        meta = metadata(
            name="test",
            version="1.0.0",
            description="Test",
            config=[Config1, Config2]
        )
        assert Config1 in meta["config"]
        assert Config2 in meta["config"]
        assert len(meta["config"]) == 2

    def test_metadata_with_base_config(self):
        """Test metadata with base_config (creates AppMetadata)."""
        meta = metadata(
            name="my_app",
            version="1.0.0",
            description="My App",
            base_config=Settings
        )
        assert "base_config" in meta
        assert meta["base_config"] == Settings

    def test_metadata_with_wire_false(self):
        """Test metadata with wire=False."""
        meta = metadata(
            name="test",
            version="1.0.0",
            description="Test",
            wire=False
        )
        assert meta["wire"] is False

    def test_metadata_with_extra_kwargs(self):
        """Test metadata with additional kwargs."""
        meta = metadata(
            name="test",
            version="1.0.0",
            description="Test",
            custom_field="custom_value"
        )
        assert meta["custom_field"] == "custom_value"

    def test_metadata_wirings_none_becomes_empty_set(self):
        """Test metadata with None wirings becomes empty set."""
        meta = metadata(
            name="test",
            version="1.0.0",
            description="Test",
            wirings=None
        )
        assert meta["wirings"] == set()

    def test_metadata_requires_none_becomes_empty_set(self):
        """Test metadata with None requires becomes empty set."""
        meta = metadata(
            name="test",
            version="1.0.0",
            description="Test",
            requires=None
        )
        assert meta["requires"] == set()

    def test_metadata_config_none_becomes_empty_set(self):
        """Test metadata with None config becomes empty set."""
        meta = metadata(
            name="test",
            version="1.0.0",
            description="Test",
            config=None
        )
        assert meta["config"] == set()
