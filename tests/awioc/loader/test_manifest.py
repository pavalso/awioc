"""Tests for the manifest loader module."""

import pytest
import yaml

from src.awioc.loader.manifest import (
    AWIOC_DIR,
    MANIFEST_FILENAME,
    ComponentConfigRef,
    ComponentEntry,
    PluginManifest,
    find_manifest,
    load_manifest,
    manifest_to_metadata,
)


class TestComponentConfigRef:
    """Tests for ComponentConfigRef model."""

    def test_create_with_model_only(self):
        """Test creating config ref with model only."""
        ref = ComponentConfigRef(model="module:ClassName")
        assert ref.model == "module:ClassName"
        assert ref.prefix is None

    def test_create_with_model_and_prefix(self):
        """Test creating config ref with model and prefix."""
        ref = ComponentConfigRef(model="module:ClassName", prefix="custom")
        assert ref.model == "module:ClassName"
        assert ref.prefix == "custom"

    def test_rejects_extra_fields(self):
        """Test that extra fields are rejected."""
        with pytest.raises(ValueError):
            ComponentConfigRef(model="module:Class", extra_field="value")


class TestComponentEntry:
    """Tests for ComponentEntry model."""

    def test_create_minimal_entry(self):
        """Test creating entry with minimal required fields."""
        entry = ComponentEntry(name="my_component", file="component.py")
        assert entry.name == "my_component"
        assert entry.file == "component.py"
        assert entry.version == "0.0.0"
        assert entry.description == ""
        assert entry.class_name is None
        assert entry.wire is False
        assert entry.wirings == []
        assert entry.requires == []
        assert entry.config is None

    def test_create_full_entry(self):
        """Test creating entry with all fields."""
        entry = ComponentEntry(
            name="full_component",
            version="1.2.3",
            description="A full component",
            file="full.py",
            **{"class": "FullComponent"},
            wire=True,
            wirings=["module1", "module2"],
            requires=["dep1", "dep2"],
            config=[{"model": "full:Config", "prefix": "fc"}],
        )
        assert entry.name == "full_component"
        assert entry.version == "1.2.3"
        assert entry.description == "A full component"
        assert entry.file == "full.py"
        assert entry.class_name == "FullComponent"
        assert entry.wire is True
        assert entry.wirings == ["module1", "module2"]
        assert entry.requires == ["dep1", "dep2"]
        assert len(entry.config) == 1
        assert entry.config[0].model == "full:Config"

    def test_class_alias(self):
        """Test that 'class' field works as alias for class_name."""
        data = {"name": "test", "file": "test.py", "class": "TestClass"}
        entry = ComponentEntry(**data)
        assert entry.class_name == "TestClass"

    def test_config_normalization_single_dict(self):
        """Test that single config dict is normalized to list."""
        entry = ComponentEntry(
            name="test",
            file="test.py",
            config={"model": "test:Config"},
        )
        assert isinstance(entry.config, list)
        assert len(entry.config) == 1
        assert entry.config[0].model == "test:Config"

    def test_config_normalization_string(self):
        """Test that string config is normalized to list with model."""
        entry = ComponentEntry(
            name="test",
            file="test.py",
            config="test:Config",
        )
        assert isinstance(entry.config, list)
        assert len(entry.config) == 1
        assert entry.config[0].model == "test:Config"

    def test_get_config_list_empty(self):
        """Test get_config_list with no config."""
        entry = ComponentEntry(name="test", file="test.py")
        assert entry.get_config_list() == []

    def test_get_config_list_with_config(self):
        """Test get_config_list with config."""
        entry = ComponentEntry(
            name="test",
            file="test.py",
            config=[{"model": "test:Config"}],
        )
        configs = entry.get_config_list()
        assert len(configs) == 1
        assert configs[0].model == "test:Config"


class TestPluginManifest:
    """Tests for PluginManifest model."""

    def test_create_empty_manifest(self):
        """Test creating empty manifest with defaults."""
        manifest = PluginManifest()
        assert manifest.manifest_version == "1.0"
        assert manifest.name is None
        assert manifest.version is None
        assert manifest.description is None
        assert manifest.components == []

    def test_create_full_manifest(self):
        """Test creating manifest with all fields."""
        manifest = PluginManifest(
            manifest_version="1.0",
            name="my-plugins",
            version="2.0.0",
            description="My plugin collection",
            components=[
                {"name": "plugin1", "file": "plugin1.py"},
                {"name": "plugin2", "file": "plugin2.py", "class": "Plugin2"},
            ],
        )
        assert manifest.manifest_version == "1.0"
        assert manifest.name == "my-plugins"
        assert manifest.version == "2.0.0"
        assert manifest.description == "My plugin collection"
        assert len(manifest.components) == 2
        assert manifest.components[0].name == "plugin1"
        assert manifest.components[1].class_name == "Plugin2"

    def test_get_component_found(self):
        """Test get_component when component exists."""
        manifest = PluginManifest(
            components=[
                {"name": "plugin1", "file": "plugin1.py"},
                {"name": "plugin2", "file": "plugin2.py"},
            ]
        )
        component = manifest.get_component("plugin2")
        assert component is not None
        assert component.name == "plugin2"

    def test_get_component_not_found(self):
        """Test get_component when component doesn't exist."""
        manifest = PluginManifest(
            components=[{"name": "plugin1", "file": "plugin1.py"}]
        )
        component = manifest.get_component("nonexistent")
        assert component is None

    def test_get_component_by_file_found(self):
        """Test get_component_by_file when file exists."""
        manifest = PluginManifest(
            components=[
                {"name": "plugin1", "file": "plugin1.py"},
                {"name": "plugin2", "file": "plugin2.py", "class": "Plugin2"},
            ]
        )
        component = manifest.get_component_by_file("plugin2.py")
        assert component is not None
        assert component.name == "plugin2"

    def test_get_component_by_file_with_class(self):
        """Test get_component_by_file with class filter."""
        manifest = PluginManifest(
            components=[
                {"name": "plugin1", "file": "multi.py", "class": "Plugin1"},
                {"name": "plugin2", "file": "multi.py", "class": "Plugin2"},
            ]
        )
        component = manifest.get_component_by_file("multi.py", "Plugin2")
        assert component is not None
        assert component.name == "plugin2"

    def test_get_component_by_file_not_found(self):
        """Test get_component_by_file when file doesn't exist."""
        manifest = PluginManifest(
            components=[{"name": "plugin1", "file": "plugin1.py"}]
        )
        component = manifest.get_component_by_file("nonexistent.py")
        assert component is None


class TestLoadManifest:
    """Tests for load_manifest function."""

    def test_load_valid_manifest(self, temp_dir):
        """Test loading a valid manifest file from .awioc directory."""
        awioc_dir = temp_dir / AWIOC_DIR
        awioc_dir.mkdir()
        manifest_content = {
            "manifest_version": "1.0",
            "name": "test-plugins",
            "version": "1.0.0",
            "components": [
                {"name": "plugin1", "file": "plugin1.py", "wire": True},
            ],
        }
        manifest_path = awioc_dir / MANIFEST_FILENAME
        manifest_path.write_text(yaml.dump(manifest_content))

        manifest = load_manifest(temp_dir)

        assert manifest.manifest_version == "1.0"
        assert manifest.name == "test-plugins"
        assert len(manifest.components) == 1
        assert manifest.components[0].name == "plugin1"
        assert manifest.components[0].wire is True

    def test_load_manifest_not_found(self, temp_dir):
        """Test that loading missing manifest raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Manifest not found"):
            load_manifest(temp_dir)

    def test_load_empty_manifest(self, temp_dir):
        """Test loading empty manifest file."""
        awioc_dir = temp_dir / AWIOC_DIR
        awioc_dir.mkdir()
        manifest_path = awioc_dir / MANIFEST_FILENAME
        manifest_path.write_text("")

        manifest = load_manifest(temp_dir)

        assert manifest.manifest_version == "1.0"
        assert manifest.components == []

    def test_load_manifest_with_config(self, temp_dir):
        """Test loading manifest with config references."""
        awioc_dir = temp_dir / AWIOC_DIR
        awioc_dir.mkdir()
        manifest_content = {
            "manifest_version": "1.0",
            "components": [
                {
                    "name": "db_plugin",
                    "file": "db.py",
                    "config": [
                        {"model": "db:DatabaseConfig", "prefix": "database"},
                    ],
                },
            ],
        }
        manifest_path = awioc_dir / MANIFEST_FILENAME
        manifest_path.write_text(yaml.dump(manifest_content))

        manifest = load_manifest(temp_dir)

        assert len(manifest.components) == 1
        configs = manifest.components[0].get_config_list()
        assert len(configs) == 1
        assert configs[0].model == "db:DatabaseConfig"
        assert configs[0].prefix == "database"


class TestFindManifest:
    """Tests for find_manifest function."""

    def test_find_manifest_in_directory(self, temp_dir):
        """Test finding manifest in a directory's .awioc folder."""
        awioc_dir = temp_dir / AWIOC_DIR
        awioc_dir.mkdir()
        manifest_path = awioc_dir / MANIFEST_FILENAME
        manifest_path.write_text("manifest_version: '1.0'")

        result = find_manifest(temp_dir)

        assert result is not None
        assert result == manifest_path

    def test_find_manifest_for_file(self, temp_dir):
        """Test finding manifest for a file (in parent's .awioc directory)."""
        awioc_dir = temp_dir / AWIOC_DIR
        awioc_dir.mkdir()
        manifest_path = awioc_dir / MANIFEST_FILENAME
        manifest_path.write_text("manifest_version: '1.0'")

        file_path = temp_dir / "component.py"
        file_path.write_text("# component")

        result = find_manifest(file_path)

        assert result is not None
        assert result == manifest_path

    def test_find_manifest_not_found(self, temp_dir):
        """Test that find_manifest returns None when no manifest exists."""
        result = find_manifest(temp_dir)
        assert result is None

    def test_find_manifest_in_subdirectory(self, temp_dir):
        """Test finding manifest in subdirectory's .awioc folder."""
        subdir = temp_dir / "plugins"
        subdir.mkdir()
        awioc_dir = subdir / AWIOC_DIR
        awioc_dir.mkdir()
        manifest_path = awioc_dir / MANIFEST_FILENAME
        manifest_path.write_text("manifest_version: '1.0'")

        result = find_manifest(subdir)

        assert result is not None
        assert result == manifest_path


class TestManifestToMetadata:
    """Tests for manifest_to_metadata function."""

    def test_basic_metadata_conversion(self, temp_dir):
        """Test converting basic entry to metadata."""
        entry = ComponentEntry(
            name="test_component",
            version="1.0.0",
            description="Test description",
            file="test.py",
            wire=True,
        )
        manifest_path = temp_dir / MANIFEST_FILENAME

        metadata = manifest_to_metadata(entry, manifest_path)

        assert metadata["name"] == "test_component"
        assert metadata["version"] == "1.0.0"
        assert metadata["description"] == "Test description"
        assert metadata["wire"] is True
        assert metadata["_manifest_path"] == str(manifest_path)

    def test_metadata_with_wirings(self, temp_dir):
        """Test converting entry with wirings."""
        entry = ComponentEntry(
            name="test",
            file="test.py",
            wirings=["module1", "module2"],
        )
        manifest_path = temp_dir / MANIFEST_FILENAME

        metadata = manifest_to_metadata(entry, manifest_path)

        assert metadata["wirings"] == {"module1", "module2"}

    def test_metadata_with_requires(self, temp_dir):
        """Test converting entry with requires."""
        entry = ComponentEntry(
            name="test",
            file="test.py",
            requires=["dep1", "dep2"],
        )
        manifest_path = temp_dir / MANIFEST_FILENAME

        metadata = manifest_to_metadata(entry, manifest_path)

        assert metadata["_requires_names"] == ["dep1", "dep2"]

    def test_metadata_with_config_refs(self, temp_dir):
        """Test converting entry with config refs."""
        entry = ComponentEntry(
            name="test",
            file="test.py",
            config=[{"model": "test:Config", "prefix": "tc"}],
        )
        manifest_path = temp_dir / MANIFEST_FILENAME

        metadata = manifest_to_metadata(entry, manifest_path)

        assert len(metadata["_config_refs"]) == 1
        assert metadata["_config_refs"][0]["model"] == "test:Config"
        assert metadata["_config_refs"][0]["prefix"] == "tc"

    def test_metadata_empty_wirings_is_empty_set(self, temp_dir):
        """Test that empty wirings results in empty set."""
        entry = ComponentEntry(name="test", file="test.py", wirings=[])
        manifest_path = temp_dir / MANIFEST_FILENAME

        metadata = manifest_to_metadata(entry, manifest_path)

        assert metadata["wirings"] == set()
