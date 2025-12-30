"""Extended tests for the manifest loader module to improve coverage."""

import yaml

from src.awioc.loader.manifest import (
    AWIOC_DIR,
    MANIFEST_FILENAME,
    ComponentConfigRef,
    ComponentEntry,
    PluginManifest,
    find_manifest,
    has_awioc_dir,
    load_manifest,
    manifest_to_metadata,
    resolve_config_models,
)


class TestHasAwiocDir:
    """Tests for has_awioc_dir function."""

    def test_returns_true_with_manifest(self, tmp_path):
        """Test returns True when .awioc/manifest.yaml exists."""
        awioc_dir = tmp_path / AWIOC_DIR
        awioc_dir.mkdir()
        (awioc_dir / MANIFEST_FILENAME).write_text("manifest_version: '1.0'")

        assert has_awioc_dir(tmp_path) is True

    def test_returns_false_without_manifest(self, tmp_path):
        """Test returns False when .awioc directory is empty."""
        awioc_dir = tmp_path / AWIOC_DIR
        awioc_dir.mkdir()

        assert has_awioc_dir(tmp_path) is False

    def test_returns_false_without_awioc_dir(self, tmp_path):
        """Test returns False when .awioc directory doesn't exist."""
        assert has_awioc_dir(tmp_path) is False


class TestResolveConfigModels:
    """Tests for resolve_config_models function."""

    def test_empty_list(self, tmp_path):
        """Test with empty list."""
        result = resolve_config_models([], tmp_path)
        assert result == set()

    def test_resolve_valid_model(self, tmp_path):
        """Test resolving valid Pydantic model."""
        module_file = tmp_path / "models.py"
        module_file.write_text('''
from pydantic import BaseModel

class ValidModel(BaseModel):
    name: str = "test"
''', encoding="utf-8")

        config_refs = [{"model": "models:ValidModel"}]
        result = resolve_config_models(config_refs, tmp_path)
        assert len(result) == 1

    def test_resolve_with_prefix_override(self, tmp_path):
        """Test resolving model with prefix override."""
        module_file = tmp_path / "prefixed.py"
        module_file.write_text('''
from pydantic import BaseModel

class PrefixedModel(BaseModel):
    __prefix__ = "default"
    value: str = ""
''', encoding="utf-8")

        config_refs = [{"model": "prefixed:PrefixedModel", "prefix": "custom"}]
        result = resolve_config_models(config_refs, tmp_path)
        assert len(result) == 1
        model = list(result)[0]
        assert model.__prefix__ == "custom"

    def test_skip_non_pydantic_model(self, tmp_path, caplog):
        """Test skipping non-Pydantic model with warning."""
        import logging

        module_file = tmp_path / "not_pydantic.py"
        module_file.write_text('''
class NotAModel:
    pass
''', encoding="utf-8")

        config_refs = [{"model": "not_pydantic:NotAModel"}]

        with caplog.at_level(logging.WARNING):
            result = resolve_config_models(config_refs, tmp_path)
            assert len(result) == 0
            assert "not a Pydantic BaseModel" in caplog.text

    def test_handle_resolve_error(self, tmp_path, caplog):
        """Test handling resolve errors gracefully."""
        import logging

        config_refs = [{"model": "nonexistent_module:Class"}]

        with caplog.at_level(logging.ERROR):
            result = resolve_config_models(config_refs, tmp_path)
            assert len(result) == 0
            assert "Failed to resolve config model" in caplog.text


class TestManifestToMetadata:
    """Extended tests for manifest_to_metadata function."""

    def test_with_config_models(self, tmp_path):
        """Test manifest to metadata with config models."""
        # Create config model
        config_file = tmp_path / "app_config.py"
        config_file.write_text('''
from pydantic import BaseModel

class AppConfig(BaseModel):
    __prefix__ = "app"
    host: str = "localhost"
    port: int = 8080
''', encoding="utf-8")

        # Create manifest
        manifest = PluginManifest(
            manifest_version="1.0",
            name="test_app",
            version="1.0.0",
            components=[
                ComponentEntry(
                    name="Test App",
                    version="1.0.0",
                    file="app.py",
                    config=[ComponentConfigRef(model="app_config:AppConfig")]
                )
            ]
        )

        metadata = manifest_to_metadata(manifest.components[0], tmp_path)
        assert metadata["name"] == "Test App"
        assert "_config_refs" in metadata
        assert len(metadata["_config_refs"]) == 1


class TestLoadManifest:
    """Extended tests for load_manifest function."""

    def test_load_manifest_with_all_fields(self, tmp_path):
        """Test loading manifest with all component fields."""
        awioc_dir = tmp_path / AWIOC_DIR
        awioc_dir.mkdir()

        manifest_content = {
            "manifest_version": "1.0",
            "name": "full_manifest",
            "version": "2.0.0",
            "description": "A complete manifest",
            "components": [
                {
                    "name": "Full Component",
                    "version": "1.5.0",
                    "description": "A component with all fields",
                    "file": "component.py",
                    "class": "FullComponent",
                    "wire": True,
                    "wirings": ["other_module"],
                    "requires": ["other_component"],
                    "config": [{"model": "config:Config"}]
                }
            ]
        }

        (awioc_dir / MANIFEST_FILENAME).write_text(
            yaml.dump(manifest_content), encoding="utf-8"
        )

        manifest = load_manifest(tmp_path)
        assert manifest is not None
        assert manifest.name == "full_manifest"
        assert len(manifest.components) == 1

        component = manifest.components[0]
        assert component.name == "Full Component"
        assert component.wire is True
        assert "other_module" in component.wirings
        assert "other_component" in component.requires


class TestFindManifest:
    """Tests for find_manifest function."""

    def test_find_manifest_in_current_dir(self, tmp_path):
        """Test finding manifest in current directory."""
        awioc_dir = tmp_path / AWIOC_DIR
        awioc_dir.mkdir()
        (awioc_dir / MANIFEST_FILENAME).write_text("manifest_version: '1.0'")

        path = find_manifest(tmp_path)
        assert path is not None
        assert path == awioc_dir / MANIFEST_FILENAME

    def test_find_manifest_not_found(self, tmp_path):
        """Test finding manifest when not present."""
        path = find_manifest(tmp_path)
        assert path is None

    def test_find_manifest_in_parent(self, tmp_path):
        """Test finding manifest in parent directory."""
        awioc_dir = tmp_path / AWIOC_DIR
        awioc_dir.mkdir()
        (awioc_dir / MANIFEST_FILENAME).write_text("manifest_version: '1.0'")

        # Create subdirectory
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        path = find_manifest(subdir)
        assert path is not None
        assert path == awioc_dir / MANIFEST_FILENAME
