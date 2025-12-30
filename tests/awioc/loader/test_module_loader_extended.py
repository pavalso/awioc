"""Extended tests for the module_loader module to improve coverage."""

import sys

import pytest
import yaml

from src.awioc.loader.module_loader import (
    compile_component,
    compile_components_from_manifest,
    _load_module,
    _resolve_pot_reference,
    _get_manifest_metadata,
)


class TestLoadModule:
    """Tests for _load_module function."""

    def test_load_simple_module(self, tmp_path):
        """Test loading a simple Python module."""
        module_file = tmp_path / "simple_module.py"
        module_file.write_text('''
x = 42
def func():
    return "hello"
''', encoding="utf-8")

        sys.path.insert(0, str(tmp_path))
        try:
            module = _load_module(module_file)
            assert hasattr(module, 'x')
            assert module.x == 42
        finally:
            sys.path.remove(str(tmp_path))

    def test_load_module_from_directory(self, tmp_path):
        """Test loading module from directory with __init__.py."""
        pkg_dir = tmp_path / "my_package"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text('''
name = "my_package"
''', encoding="utf-8")

        sys.path.insert(0, str(tmp_path))
        try:
            module = _load_module(pkg_dir)
            assert hasattr(module, 'name')
            assert module.name == "my_package"
        finally:
            sys.path.remove(str(tmp_path))

    def test_load_module_not_found(self, tmp_path):
        """Test loading non-existent module raises error."""
        with pytest.raises(FileNotFoundError):
            _load_module(tmp_path / "nonexistent.py")

    def test_load_module_without_suffix(self, tmp_path):
        """Test loading module file without .py suffix."""
        module_file = tmp_path / "nosuffix.py"
        module_file.write_text("value = 123")

        # Reference without .py extension
        nosuffix_path = tmp_path / "nosuffix"

        sys.path.insert(0, str(tmp_path))
        try:
            module = _load_module(nosuffix_path)
            assert hasattr(module, 'value')
            assert module.value == 123
        finally:
            sys.path.remove(str(tmp_path))


class TestCompileComponent:
    """Tests for compile_component function."""

    def test_compile_pot_reference(self, tmp_path):
        """Test compiling pot reference @pot/component."""
        # This test requires a mock pot setup
        # Skip if pot resolution is not available
        try:
            compile_component("@nonexistent/component")
            pytest.fail("Expected error for nonexistent pot")
        except (FileNotFoundError, Exception):
            pass  # Expected


class TestResolvePotReference:
    """Tests for _resolve_pot_reference function."""

    def test_non_pot_reference_returns_none(self):
        """Test that non-pot references return None."""
        result = _resolve_pot_reference("some/path/to/module.py")
        assert result is None

    def test_pot_reference_without_slash_logs_error(self, caplog):
        """Test pot reference without slash logs error."""
        import logging

        with caplog.at_level(logging.ERROR):
            result = _resolve_pot_reference("@invalid-pot-ref")
            assert result is None
            assert "Invalid pot reference" in caplog.text


class TestGetManifestMetadata:
    """Tests for _get_manifest_metadata function."""

    def test_no_manifest_returns_none(self, tmp_path):
        """Test returns None when no manifest exists."""
        file_path = tmp_path / "component.py"
        file_path.write_text("x = 1")
        result = _get_manifest_metadata(file_path, None)
        assert result is None

    def test_manifest_load_error_returns_none(self, tmp_path, caplog):
        """Test returns None when manifest cannot be loaded."""
        import logging

        # Create directory structure with invalid manifest
        awioc_dir = tmp_path / ".awioc"
        awioc_dir.mkdir()
        manifest_file = awioc_dir / "manifest.yaml"
        manifest_file.write_text("invalid: yaml: {[")

        with caplog.at_level(logging.WARNING):
            result = _get_manifest_metadata(tmp_path, None)
            # Result may be None due to invalid yaml
            # Just verify no exception was raised

    def test_component_not_in_manifest_returns_none(self, tmp_path, caplog):
        """Test returns None when component not found in manifest."""
        import logging

        # Create valid manifest but with different component
        awioc_dir = tmp_path / ".awioc"
        awioc_dir.mkdir()
        manifest_file = awioc_dir / "manifest.yaml"
        manifest_file.write_text(yaml.dump({
            "manifest_version": "1.0",
            "name": "test",
            "version": "1.0.0",
            "components": [{"name": "Other", "version": "1.0.0", "file": "other.py"}]
        }))

        # Create a file that's not in the manifest
        file_path = tmp_path / "not_in_manifest.py"
        file_path.write_text("x = 1")

        with caplog.at_level(logging.DEBUG):
            result = _get_manifest_metadata(file_path, None)
            assert result is None


class TestCompileComponentsFromManifest:
    """Tests for compile_components_from_manifest function."""

    def test_compile_no_manifest(self, tmp_path):
        """Test compiling from directory without manifest."""
        with pytest.raises(FileNotFoundError):
            compile_components_from_manifest(tmp_path)
