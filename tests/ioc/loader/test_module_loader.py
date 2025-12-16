import pytest
import sys
from pathlib import Path

from src.ioc.loader.module_loader import compile_component
from src.ioc.components.protocols import Component


class TestCompileComponent:
    """Tests for compile_component function."""

    def test_compile_py_file(self, sample_component_module, reset_sys_modules):
        """Test compiling a .py file component."""
        result = compile_component(sample_component_module)

        assert isinstance(result, Component)
        assert result.__metadata__["name"] == "sample_component"
        assert result.__metadata__["version"] == "1.0.0"

    def test_compile_package_directory(self, sample_component_package, reset_sys_modules):
        """Test compiling a package directory."""
        result = compile_component(sample_component_package)

        assert isinstance(result, Component)
        assert result.__metadata__["name"] == "sample_package"
        assert result.__metadata__["version"] == "2.0.0"

    def test_compile_path_without_suffix(self, temp_dir, reset_sys_modules):
        """Test compiling path without .py suffix."""
        module_path = temp_dir / "no_suffix.py"
        module_path.write_text("""
__metadata__ = {
    "name": "no_suffix",
    "version": "1.0.0",
    "description": "Test"
}
initialize = None
shutdown = None
""")
        # Pass path without .py extension
        path_without_suffix = temp_dir / "no_suffix"
        result = compile_component(path_without_suffix)

        assert isinstance(result, Component)
        assert result.__metadata__["name"] == "no_suffix"

    def test_compile_nonexistent_raises(self, temp_dir):
        """Test compiling non-existent path raises FileNotFoundError."""
        nonexistent = temp_dir / "does_not_exist"

        with pytest.raises(FileNotFoundError, match="Component not found"):
            compile_component(nonexistent)

    def test_compile_cached_module(self, sample_component_module, reset_sys_modules):
        """Test that already loaded modules are returned from cache."""
        # First compile loads the module
        result1 = compile_component(sample_component_module)

        # Second compile should return cached module
        result2 = compile_component(sample_component_module)

        assert result1 is result2

    def test_compile_adds_metadata_if_missing(self, temp_dir, reset_sys_modules):
        """Test that metadata is added if missing."""
        module_path = temp_dir / "no_metadata_test.py"
        module_path.write_text("""
# Module without __metadata__
value = 42
""")
        result = compile_component(module_path)

        assert hasattr(result, "__metadata__")
        # Name is derived from __qualname__ or class qualname
        assert "name" in result.__metadata__
        assert result.__metadata__["version"] == "0.0.0"

    def test_compile_adds_initialize_if_missing(self, temp_dir, reset_sys_modules):
        """Test that initialize is added if missing."""
        module_path = temp_dir / "no_init.py"
        module_path.write_text("""
__metadata__ = {"name": "no_init", "version": "1.0.0", "description": ""}
# No initialize defined
""")
        result = compile_component(module_path)

        assert hasattr(result, "initialize")
        assert result.initialize is None

    def test_compile_adds_shutdown_if_missing(self, temp_dir, reset_sys_modules):
        """Test that shutdown is added if missing."""
        module_path = temp_dir / "no_shutdown.py"
        module_path.write_text("""
__metadata__ = {"name": "no_shutdown", "version": "1.0.0", "description": ""}
# No shutdown defined
""")
        result = compile_component(module_path)

        assert hasattr(result, "shutdown")
        assert result.shutdown is None

    def test_compile_preserves_module_attributes(self, temp_dir, reset_sys_modules):
        """Test that module attributes are preserved."""
        module_path = temp_dir / "with_attrs.py"
        module_path.write_text("""
__metadata__ = {"name": "with_attrs", "version": "1.0.0", "description": ""}

CONSTANT = "test_value"

def helper():
    return 42
""")
        result = compile_component(module_path)

        assert result.CONSTANT == "test_value"
        assert result.helper() == 42

    def test_compile_module_in_sys_modules(self, sample_component_module, reset_sys_modules):
        """Test that compiled module is added to sys.modules."""
        module_name = sample_component_module.stem
        assert module_name not in sys.modules

        compile_component(sample_component_module)

        assert module_name in sys.modules

    def test_compile_package_has_submodule_search(self, temp_dir, reset_sys_modules):
        """Test package compilation sets up submodule search paths."""
        pkg_dir = temp_dir / "test_pkg"
        pkg_dir.mkdir()

        init_path = pkg_dir / "__init__.py"
        init_path.write_text("""
__metadata__ = {"name": "test_pkg", "version": "1.0.0", "description": ""}
""")

        sub_path = pkg_dir / "submodule.py"
        sub_path.write_text("""
VALUE = "submodule_value"
""")

        result = compile_component(pkg_dir)

        assert result.__metadata__["name"] == "test_pkg"
        # Package should be in sys.modules
        assert "test_pkg" in sys.modules


class TestCompileComponentEdgeCases:
    """Edge case tests for compile_component."""

    def test_compile_empty_file(self, temp_dir, reset_sys_modules):
        """Test compiling an empty file."""
        module_path = temp_dir / "empty_module.py"
        module_path.write_text("")

        result = compile_component(module_path)

        assert hasattr(result, "__metadata__")

    def test_compile_module_with_imports(self, temp_dir, reset_sys_modules):
        """Test compiling module with standard library imports."""
        module_path = temp_dir / "with_imports.py"
        module_path.write_text("""
import os
import sys
from pathlib import Path

__metadata__ = {"name": "with_imports", "version": "1.0.0", "description": ""}

current_dir = Path(__file__).parent
""")
        result = compile_component(module_path)

        assert result.__metadata__["name"] == "with_imports"
        assert hasattr(result, "current_dir")

    def test_compile_module_with_async_functions(self, temp_dir, reset_sys_modules):
        """Test compiling module with async functions."""
        import asyncio as asyncio_mod
        module_path = temp_dir / "async_module_test.py"
        module_path.write_text("""
import asyncio

__metadata__ = {"name": "async_module_test", "version": "1.0.0", "description": ""}

async def initialize():
    await asyncio.sleep(0)
    return True

async def shutdown():
    await asyncio.sleep(0)
""")
        result = compile_component(module_path)

        assert result.__metadata__["name"] == "async_module_test"
        assert asyncio_mod.iscoroutinefunction(result.initialize)
        assert asyncio_mod.iscoroutinefunction(result.shutdown)
