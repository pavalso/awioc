import sys

import pytest

from src.awioc.components.protocols import Component
from src.awioc.loader.module_loader import compile_component


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

        with pytest.raises(FileNotFoundError, match="Module not found"):
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


class TestCompileComponentWithReference:
    """Tests for compile_component with path:reference syntax."""

    def test_compile_with_class_reference(self, temp_dir, reset_sys_modules):
        """Test compiling a class from module using path:ClassName syntax."""
        module_path = temp_dir / "with_class.py"
        module_path.write_text("""
class MyComponent:
    __metadata__ = {
        "name": "my_component",
        "version": "1.0.0",
        "description": "A class-based component"
    }
    initialize = None
    shutdown = None
""")
        result = compile_component(f"{module_path}:MyComponent")

        assert result.__metadata__["name"] == "my_component"
        assert result.__metadata__["version"] == "1.0.0"

    def test_compile_with_instance_reference(self, temp_dir, reset_sys_modules):
        """Test compiling an instance from module using path:instance syntax."""
        module_path = temp_dir / "with_instance.py"
        module_path.write_text("""
class MyComponent:
    __metadata__ = {
        "name": "instance_component",
        "version": "2.0.0",
        "description": "An instance component"
    }
    initialize = None
    shutdown = None

my_instance = MyComponent()
""")
        result = compile_component(f"{module_path}:my_instance")

        assert result.__metadata__["name"] == "instance_component"
        assert result.__metadata__["version"] == "2.0.0"

    def test_compile_with_nested_attribute(self, temp_dir, reset_sys_modules):
        """Test compiling using nested attribute path:obj.attr syntax."""
        module_path = temp_dir / "with_nested.py"
        module_path.write_text("""
class Container:
    class NestedComponent:
        __metadata__ = {
            "name": "nested_component",
            "version": "3.0.0",
            "description": "A nested component"
        }
        initialize = None
        shutdown = None

container = Container()
""")
        result = compile_component(f"{module_path}:Container.NestedComponent")

        assert result.__metadata__["name"] == "nested_component"
        assert result.__metadata__["version"] == "3.0.0"

    def test_compile_with_factory_function(self, temp_dir, reset_sys_modules):
        """Test compiling using factory function path:factory() syntax."""
        module_path = temp_dir / "with_factory.py"
        module_path.write_text("""
class MyComponent:
    def __init__(self, name):
        self.__metadata__ = {
            "name": name,
            "version": "4.0.0",
            "description": "A factory-created component"
        }
        self.initialize = None
        self.shutdown = None

def create_component():
    return MyComponent("factory_component")
""")
        result = compile_component(f"{module_path}:create_component()")

        assert result.__metadata__["name"] == "factory_component"
        assert result.__metadata__["version"] == "4.0.0"

    def test_compile_with_class_instantiation(self, temp_dir, reset_sys_modules):
        """Test compiling using class instantiation path:MyClass() syntax."""
        module_path = temp_dir / "with_class_call.py"
        module_path.write_text("""
class MyComponent:
    def __init__(self):
        self.__metadata__ = {
            "name": "instantiated_component",
            "version": "5.0.0",
            "description": "An instantiated component"
        }
        self.initialize = None
        self.shutdown = None
""")
        result = compile_component(f"{module_path}:MyComponent()")

        assert result.__metadata__["name"] == "instantiated_component"
        assert result.__metadata__["version"] == "5.0.0"

    def test_compile_with_string_path(self, temp_dir, reset_sys_modules):
        """Test compiling using string path instead of Path object."""
        module_path = temp_dir / "string_path_test.py"
        module_path.write_text("""
__metadata__ = {
    "name": "string_path_component",
    "version": "1.0.0",
    "description": "Test"
}
initialize = None
shutdown = None
""")
        result = compile_component(str(module_path))

        assert result.__metadata__["name"] == "string_path_component"

    def test_compile_reference_missing_attribute_raises(self, temp_dir, reset_sys_modules):
        """Test that missing attribute raises AttributeError."""
        module_path = temp_dir / "missing_attr.py"
        module_path.write_text("""
# No NonExistent attribute
value = 42
""")
        with pytest.raises(AttributeError):
            compile_component(f"{module_path}:NonExistent")

    def test_compile_reference_non_callable_raises(self, temp_dir, reset_sys_modules):
        """Test that calling non-callable raises TypeError."""
        module_path = temp_dir / "non_callable.py"
        module_path.write_text("""
not_a_function = "just a string"
""")
        with pytest.raises(TypeError, match="is not callable"):
            compile_component(f"{module_path}:not_a_function()")

    def test_compile_reference_preserves_methods(self, temp_dir, reset_sys_modules):
        """Test that referenced class methods are preserved."""
        module_path = temp_dir / "with_methods.py"
        module_path.write_text("""
class MyComponent:
    __metadata__ = {
        "name": "method_component",
        "version": "1.0.0",
        "description": "Component with methods"
    }

    async def initialize(self):
        return True

    async def shutdown(self):
        pass

    def custom_method(self):
        return "custom_result"
""")
        result = compile_component(f"{module_path}:MyComponent")

        assert hasattr(result, "custom_method")
        # Class methods need to be called on instance
        instance = result()
        assert instance.custom_method() == "custom_result"

    def test_compile_path_without_reference_still_works(self, sample_component_module, reset_sys_modules):
        """Test that path without reference still loads the module."""
        result = compile_component(sample_component_module)

        assert isinstance(result, Component)
        assert result.__metadata__["name"] == "sample_component"

    def test_compile_with_reference_adds_metadata_if_missing(self, temp_dir, reset_sys_modules):
        """Test that metadata is added to referenced object if missing."""
        module_path = temp_dir / "no_meta_class.py"
        module_path.write_text("""
class PlainClass:
    '''A plain class without metadata.'''
    pass
""")
        result = compile_component(f"{module_path}:PlainClass")

        assert hasattr(result, "__metadata__")
        assert "name" in result.__metadata__


class TestCompileComponentDotReference:
    """Tests for compile_component with .:<Reference> syntax (current directory)."""

    def test_compile_dot_reference_resolves_to_package_directory(self, temp_dir, reset_sys_modules, monkeypatch):
        """Test that .:Reference resolves . to the package directory."""
        # Create a package with __init__.py
        init_path = temp_dir / "__init__.py"
        init_path.write_text("""
class MyApp:
    __metadata__ = {
        "name": "dot_reference_app",
        "version": "1.0.0",
        "description": "App loaded via .:<Reference>"
    }
    initialize = None
    shutdown = None
""")
        # Change to the temp directory
        monkeypatch.chdir(temp_dir)

        # Compile using .:Reference syntax
        result = compile_component(".:MyApp")

        assert result.__metadata__["name"] == "dot_reference_app"
        assert result.__metadata__["version"] == "1.0.0"

    def test_compile_dot_factory_resolves_to_package_directory(self, temp_dir, reset_sys_modules, monkeypatch):
        """Test that .:factory() resolves . to the package directory."""
        init_path = temp_dir / "__init__.py"
        init_path.write_text("""
class MyApp:
    def __init__(self):
        self.__metadata__ = {
            "name": "factory_dot_app",
            "version": "2.0.0",
            "description": "App loaded via .:factory()"
        }
        self.initialize = None
        self.shutdown = None

def create_app():
    return MyApp()
""")
        monkeypatch.chdir(temp_dir)

        result = compile_component(".:create_app()")

        assert result.__metadata__["name"] == "factory_dot_app"
        assert result.__metadata__["version"] == "2.0.0"

    def test_compile_dot_without_reference_loads_package(self, temp_dir, reset_sys_modules, monkeypatch):
        """Test that . without reference loads the package __init__.py as module."""
        init_path = temp_dir / "__init__.py"
        init_path.write_text("""
__metadata__ = {
    "name": "dot_package",
    "version": "3.0.0",
    "description": "Package loaded via ."
}
initialize = None
shutdown = None
""")
        monkeypatch.chdir(temp_dir)

        result = compile_component(".")

        assert result.__metadata__["name"] == "dot_package"
        assert result.__metadata__["version"] == "3.0.0"

    def test_compile_dot_module_name_uses_directory_name(self, temp_dir, reset_sys_modules, monkeypatch):
        """Test that . resolves to the actual directory name for module naming."""
        init_path = temp_dir / "__init__.py"
        init_path.write_text("""
__metadata__ = {
    "name": "dir_name_test",
    "version": "1.0.0",
    "description": "Test"
}
""")
        monkeypatch.chdir(temp_dir)

        compile_component(".")

        # The module should be registered with the actual directory name, not empty string
        dir_name = temp_dir.name
        assert dir_name in sys.modules
        assert dir_name != ""
