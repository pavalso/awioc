import sys

import pytest
import yaml

from src.awioc.components.protocols import Component
from src.awioc.loader.manifest import AWIOC_DIR, MANIFEST_FILENAME
from src.awioc.loader.module_loader import compile_component


def create_manifest(directory, components):
    """Helper to create .awioc/manifest.yaml in a directory."""
    awioc_dir = directory / AWIOC_DIR
    awioc_dir.mkdir(exist_ok=True)
    manifest = {
        "manifest_version": "1.0",
        "components": components,
    }
    (awioc_dir / MANIFEST_FILENAME).write_text(yaml.dump(manifest))


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
initialize = None
shutdown = None
wait = None
""")
        # Create manifest
        create_manifest(temp_dir, [
            {"name": "no_suffix", "version": "1.0.0", "description": "Test", "file": "no_suffix.py"}
        ])

        # Pass path without .py extension
        path_without_suffix = temp_dir / "no_suffix"
        result = compile_component(path_without_suffix)

        assert isinstance(result, Component)
        assert result.__metadata__["name"] == "no_suffix"

    def test_compile_nonexistent_raises(self, temp_dir):
        """Test compiling non-existent path raises error about manifest."""
        nonexistent = temp_dir / "does_not_exist"

        # With mandatory manifests, non-existent paths fail at manifest lookup
        with pytest.raises(RuntimeError, match="No manifest entry found"):
            compile_component(nonexistent)

    def test_compile_cached_module(self, sample_component_module, reset_sys_modules):
        """Test that already loaded modules are returned from cache."""
        # First compile loads the module
        result1 = compile_component(sample_component_module)

        # Second compile should return cached module
        result2 = compile_component(sample_component_module)

        assert result1 is result2

    def test_compile_adds_initialize_if_missing(self, temp_dir, reset_sys_modules):
        """Test that initialize is added if missing."""
        module_path = temp_dir / "no_init.py"
        module_path.write_text("""
# No initialize defined
""")
        create_manifest(temp_dir, [
            {"name": "no_init", "version": "1.0.0", "description": "", "file": "no_init.py"}
        ])
        result = compile_component(module_path)

        assert hasattr(result, "initialize")
        assert result.initialize is None

    def test_compile_adds_shutdown_if_missing(self, temp_dir, reset_sys_modules):
        """Test that shutdown is added if missing."""
        module_path = temp_dir / "no_shutdown.py"
        module_path.write_text("""
# No shutdown defined
""")
        create_manifest(temp_dir, [
            {"name": "no_shutdown", "version": "1.0.0", "description": "", "file": "no_shutdown.py"}
        ])
        result = compile_component(module_path)

        assert hasattr(result, "shutdown")
        assert result.shutdown is None

    def test_compile_adds_wait_if_missing(self, temp_dir, reset_sys_modules):
        """Test that wait is added if missing."""
        module_path = temp_dir / "no_wait.py"
        module_path.write_text("""
# No wait defined
""")
        create_manifest(temp_dir, [
            {"name": "no_wait", "version": "1.0.0", "description": "", "file": "no_wait.py"}
        ])
        result = compile_component(module_path)
        assert hasattr(result, "wait")
        assert result.wait is None

    def test_compile_preserves_module_attributes(self, temp_dir, reset_sys_modules):
        """Test that module attributes are preserved."""
        module_path = temp_dir / "with_attrs.py"
        module_path.write_text("""
CONSTANT = "test_value"

def helper():
    return 42
""")
        create_manifest(temp_dir, [
            {"name": "with_attrs", "version": "1.0.0", "description": "", "file": "with_attrs.py"}
        ])
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
        init_path.write_text("")

        sub_path = pkg_dir / "submodule.py"
        sub_path.write_text("""
VALUE = "submodule_value"
""")

        # Create manifest inside the package
        create_manifest(pkg_dir, [
            {"name": "test_pkg", "version": "1.0.0", "description": "", "file": "__init__.py"}
        ])

        result = compile_component(pkg_dir)

        assert result.__metadata__["name"] == "test_pkg"
        # Package should be in sys.modules
        assert "test_pkg" in sys.modules


class TestCompileComponentEdgeCases:
    """Edge case tests for compile_component."""

    def test_compile_empty_file_raises_error(self, temp_dir, reset_sys_modules):
        """Test compiling an empty file without manifest raises error."""
        module_path = temp_dir / "empty_module.py"
        module_path.write_text("")

        with pytest.raises(RuntimeError, match="No manifest entry found"):
            compile_component(module_path)

    def test_compile_module_with_imports(self, temp_dir, reset_sys_modules):
        """Test compiling module with standard library imports."""
        module_path = temp_dir / "with_imports.py"
        module_path.write_text("""
import os
import sys
from pathlib import Path

current_dir = Path(__file__).parent
""")
        create_manifest(temp_dir, [
            {"name": "with_imports", "version": "1.0.0", "description": "", "file": "with_imports.py"}
        ])
        result = compile_component(module_path)

        assert result.__metadata__["name"] == "with_imports"
        assert hasattr(result, "current_dir")

    def test_compile_module_with_async_functions(self, temp_dir, reset_sys_modules):
        """Test compiling module with async functions."""
        import asyncio as asyncio_mod
        module_path = temp_dir / "async_module_test.py"
        module_path.write_text("""
import asyncio

async def initialize():
    await asyncio.sleep(0)
    return True

async def shutdown():
    await asyncio.sleep(0)
""")
        create_manifest(temp_dir, [
            {"name": "async_module_test", "version": "1.0.0", "description": "", "file": "async_module_test.py"}
        ])
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
    initialize = None
    shutdown = None
""")
        create_manifest(temp_dir, [
            {"name": "my_component", "version": "1.0.0", "description": "A class-based component",
             "file": "with_class.py", "class": "MyComponent"}
        ])
        result = compile_component(f"{module_path}:MyComponent")

        assert result.__metadata__["name"] == "my_component"
        assert result.__metadata__["version"] == "1.0.0"

    def test_compile_with_instance_reference(self, temp_dir, reset_sys_modules):
        """Test compiling an instance from module using path:instance syntax."""
        module_path = temp_dir / "with_instance.py"
        module_path.write_text("""
class MyComponent:
    initialize = None
    shutdown = None

my_instance = MyComponent()
""")
        create_manifest(temp_dir, [
            {"name": "instance_component", "version": "2.0.0", "description": "An instance component",
             "file": "with_instance.py", "class": "MyComponent"}
        ])
        result = compile_component(f"{module_path}:my_instance")

        assert result.__metadata__["name"] == "instance_component"
        assert result.__metadata__["version"] == "2.0.0"

    def test_compile_with_nested_attribute(self, temp_dir, reset_sys_modules):
        """Test compiling using nested attribute path:obj.attr syntax."""
        module_path = temp_dir / "with_nested.py"
        module_path.write_text("""
class Container:
    class NestedComponent:
        initialize = None
        shutdown = None

container = Container()
""")
        create_manifest(temp_dir, [
            {"name": "nested_component", "version": "3.0.0", "description": "A nested component",
             "file": "with_nested.py", "class": "NestedComponent"}
        ])
        result = compile_component(f"{module_path}:Container.NestedComponent")

        assert result.__metadata__["name"] == "nested_component"
        assert result.__metadata__["version"] == "3.0.0"

    def test_compile_with_factory_function(self, temp_dir, reset_sys_modules):
        """Test compiling using factory function path:factory() syntax."""
        module_path = temp_dir / "with_factory.py"
        module_path.write_text("""
class MyComponent:
    def __init__(self, name):
        self.initialize = None
        self.shutdown = None

def create_component():
    return MyComponent("factory_component")
""")
        create_manifest(temp_dir, [
            {"name": "factory_component", "version": "4.0.0", "description": "A factory-created component",
             "file": "with_factory.py", "class": "MyComponent"}
        ])
        result = compile_component(f"{module_path}:create_component()")

        assert result.__metadata__["name"] == "factory_component"
        assert result.__metadata__["version"] == "4.0.0"

    def test_compile_with_class_instantiation(self, temp_dir, reset_sys_modules):
        """Test compiling using class instantiation path:MyClass() syntax."""
        module_path = temp_dir / "with_class_call.py"
        module_path.write_text("""
class MyComponent:
    def __init__(self):
        self.initialize = None
        self.shutdown = None
""")
        create_manifest(temp_dir, [
            {"name": "instantiated_component", "version": "5.0.0", "description": "An instantiated component",
             "file": "with_class_call.py", "class": "MyComponent"}
        ])
        result = compile_component(f"{module_path}:MyComponent()")

        assert result.__metadata__["name"] == "instantiated_component"
        assert result.__metadata__["version"] == "5.0.0"

    def test_compile_with_string_path(self, temp_dir, reset_sys_modules):
        """Test compiling using string path instead of Path object."""
        module_path = temp_dir / "string_path_test.py"
        module_path.write_text("""
initialize = None
shutdown = None
""")
        create_manifest(temp_dir, [
            {"name": "string_path_component", "version": "1.0.0", "description": "Test", "file": "string_path_test.py"}
        ])
        result = compile_component(str(module_path))

        assert result.__metadata__["name"] == "string_path_component"

    def test_compile_reference_missing_attribute_raises(self, temp_dir, reset_sys_modules):
        """Test that missing attribute raises AttributeError."""
        module_path = temp_dir / "missing_attr.py"
        module_path.write_text("""
# No NonExistent attribute
value = 42
""")
        create_manifest(temp_dir, [
            {"name": "missing_attr", "version": "1.0.0", "file": "missing_attr.py", "class": "NonExistent"}
        ])
        with pytest.raises(AttributeError):
            compile_component(f"{module_path}:NonExistent")

    def test_compile_reference_non_callable_raises(self, temp_dir, reset_sys_modules):
        """Test that calling non-callable raises TypeError."""
        module_path = temp_dir / "non_callable.py"
        module_path.write_text("""
not_a_function = "just a string"
""")
        create_manifest(temp_dir, [
            {"name": "non_callable", "version": "1.0.0", "file": "non_callable.py"}
        ])
        with pytest.raises(TypeError, match="is not callable"):
            compile_component(f"{module_path}:not_a_function()")

    def test_compile_reference_preserves_methods(self, temp_dir, reset_sys_modules):
        """Test that referenced class methods are preserved."""
        module_path = temp_dir / "with_methods.py"
        module_path.write_text("""
class MyComponent:
    async def initialize(self):
        return True

    async def shutdown(self):
        pass

    def custom_method(self):
        return "custom_result"
""")
        create_manifest(temp_dir, [
            {"name": "method_component", "version": "1.0.0", "description": "Component with methods",
             "file": "with_methods.py", "class": "MyComponent"}
        ])
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

    def test_compile_with_reference_raises_error_if_no_metadata(self, temp_dir, reset_sys_modules):
        """Test that missing manifest entry raises error."""
        module_path = temp_dir / "no_metadata_ref.py"
        module_path.write_text("""
class MyComponent:
    pass
""")
        with pytest.raises(RuntimeError, match="No manifest entry found"):
            compile_component(f"{module_path}:MyComponent")


class TestCompileComponentDotReference:
    """Tests for compile_component with .:<Reference> syntax (current directory)."""

    def test_compile_dot_reference_resolves_to_package_directory(self, temp_dir, reset_sys_modules, monkeypatch):
        """Test that .:Reference resolves . to the package directory."""
        # Create a package with __init__.py
        init_path = temp_dir / "__init__.py"
        init_path.write_text("""
class MyApp:
    initialize = None
    shutdown = None
""")
        # Create manifest
        create_manifest(temp_dir, [
            {"name": "dot_reference_app", "version": "1.0.0", "description": "App loaded via .:<Reference>",
             "file": "__init__.py", "class": "MyApp"}
        ])
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
        self.initialize = None
        self.shutdown = None

def create_app():
    return MyApp()
""")
        create_manifest(temp_dir, [
            {"name": "factory_dot_app", "version": "2.0.0", "description": "App loaded via .:factory()",
             "file": "__init__.py", "class": "MyApp"}
        ])
        monkeypatch.chdir(temp_dir)

        result = compile_component(".:create_app()")

        assert result.__metadata__["name"] == "factory_dot_app"
        assert result.__metadata__["version"] == "2.0.0"

    def test_compile_dot_without_reference_loads_package(self, temp_dir, reset_sys_modules, monkeypatch):
        """Test that . without reference loads the package __init__.py as module."""
        init_path = temp_dir / "__init__.py"
        init_path.write_text("""
initialize = None
shutdown = None
""")
        create_manifest(temp_dir, [
            {"name": "dot_package", "version": "3.0.0", "description": "Package loaded via .",
             "file": "__init__.py"}
        ])
        monkeypatch.chdir(temp_dir)

        result = compile_component(".")

        assert result.__metadata__["name"] == "dot_package"
        assert result.__metadata__["version"] == "3.0.0"

    def test_compile_dot_module_name_uses_directory_name(self, temp_dir, reset_sys_modules, monkeypatch):
        """Test that . resolves to the actual directory name for module naming."""
        init_path = temp_dir / "__init__.py"
        init_path.write_text("")
        create_manifest(temp_dir, [
            {"name": "dir_name_test", "version": "1.0.0", "description": "Test", "file": "__init__.py"}
        ])
        monkeypatch.chdir(temp_dir)

        compile_component(".")

        # The module should be registered with the actual directory name, not empty string
        dir_name = temp_dir.name
        assert dir_name in sys.modules
        assert dir_name != ""


class TestCompileComponentWithManifest:
    """Tests for compile_component with manifest.yaml support."""

    def test_compile_with_manifest_metadata(self, temp_dir, reset_sys_modules):
        """Test that manifest metadata is loaded correctly."""
        # Create component file without __metadata__
        module_path = temp_dir / "plugin.py"
        module_path.write_text("""
class MyPlugin:
    async def initialize(self):
        pass

    async def shutdown(self):
        pass
""")

        # Create manifest with metadata in .awioc directory
        create_manifest(temp_dir, [
            {
                "name": "manifest_plugin",
                "version": "2.0.0",
                "description": "From manifest",
                "file": "plugin.py",
                "class": "MyPlugin",
                "wire": True,
            }
        ])

        result = compile_component(f"{module_path}:MyPlugin()")

        assert result.__metadata__["name"] == "manifest_plugin"
        assert result.__metadata__["version"] == "2.0.0"
        assert result.__metadata__["description"] == "From manifest"
        assert result.__metadata__["wire"] is True

    def test_compile_without_manifest_raises_error(self, temp_dir, reset_sys_modules):
        """Test that missing manifest raises error (manifest is mandatory)."""
        module_path = temp_dir / "decorated.py"
        module_path.write_text("""
__metadata__ = {
    "name": "decorator_component",
    "version": "1.0.0",
    "description": "From decorator",
}
""")

        with pytest.raises(RuntimeError, match="No manifest entry found"):
            compile_component(module_path)

    def test_compile_require_manifest_raises_when_missing(self, temp_dir, reset_sys_modules):
        """Test that require_manifest=True raises error when no manifest."""
        module_path = temp_dir / "no_manifest.py"
        module_path.write_text("""
__metadata__ = {"name": "test", "version": "1.0.0"}
""")

        with pytest.raises(RuntimeError, match="No manifest entry found"):
            compile_component(module_path, require_manifest=True)

    def test_compile_require_manifest_succeeds_with_manifest(self, temp_dir, reset_sys_modules):
        """Test that require_manifest=True works with manifest."""
        module_path = temp_dir / "with_manifest.py"
        module_path.write_text("""
class Component:
    pass
""")

        create_manifest(temp_dir, [
            {"name": "required_component", "version": "1.0.0", "file": "with_manifest.py", "class": "Component"}
        ])

        result = compile_component(f"{module_path}:Component", require_manifest=True)

        assert result.__metadata__["name"] == "required_component"

    def test_manifest_metadata_stored_manifest_path(self, temp_dir, reset_sys_modules):
        """Test that manifest path is stored in metadata."""
        module_path = temp_dir / "test_plugin.py"
        module_path.write_text("class TestPlugin: pass")

        create_manifest(temp_dir, [
            {"name": "test", "version": "1.0.0", "file": "test_plugin.py", "class": "TestPlugin"}
        ])

        result = compile_component(f"{module_path}:TestPlugin")

        assert "_manifest_path" in result.__metadata__
        manifest_path = temp_dir / AWIOC_DIR / MANIFEST_FILENAME
        assert str(manifest_path) in result.__metadata__["_manifest_path"]

    def test_compile_directory_with_non_matching_file_name(self, temp_dir, reset_sys_modules):
        """Test loading a directory where the file name doesn't match directory name.

        This tests the case like:
        - Directory: openai_gpt/
        - Manifest file entry: open_ai.py (not openai_gpt.py or __init__.py)
        """
        # Create directory with non-matching file name
        pkg_dir = temp_dir / "openai_gpt"
        pkg_dir.mkdir()

        # Create component file with different name than directory
        (pkg_dir / "open_ai.py").write_text("""
class OpenAIComponent:
    async def initialize(self):
        pass
""")

        # Create manifest with the actual file name
        create_manifest(pkg_dir, [
            {
                "name": "OpenAI AI Library",
                "version": "1.0.0",
                "description": "OpenAI API integration",
                "file": "open_ai.py",
                "class": "OpenAIComponent",
            }
        ])

        # Compile by directory path (no class reference)
        result = compile_component(pkg_dir)

        # Should load the component from the manifest
        assert result.__metadata__["name"] == "OpenAI AI Library"
        assert result.__class__.__name__ == "OpenAIComponent"

    def test_compile_directory_single_entry_fallback(self, temp_dir, reset_sys_modules):
        """Test that single manifest entry is used as fallback for directories."""
        pkg_dir = temp_dir / "my_component"
        pkg_dir.mkdir()

        # Create component file with completely different name
        (pkg_dir / "impl.py").write_text("""
class MyImpl:
    pass
""")

        # Single entry in manifest
        create_manifest(pkg_dir, [
            {"name": "my_impl", "version": "1.0.0", "file": "impl.py", "class": "MyImpl"}
        ])

        result = compile_component(pkg_dir)

        assert result.__metadata__["name"] == "my_impl"
        assert result.__class__.__name__ == "MyImpl"


class TestCompileComponentsFromManifest:
    """Tests for compile_components_from_manifest function."""

    def test_load_all_components(self, temp_dir, reset_sys_modules):
        """Test loading all components from manifest."""
        from src.awioc.loader.module_loader import compile_components_from_manifest

        # Create component files
        (temp_dir / "plugin_a.py").write_text("""
class PluginA:
    async def initialize(self): pass
""")
        (temp_dir / "plugin_b.py").write_text("""
class PluginB:
    async def initialize(self): pass
""")

        # Create manifest in .awioc directory
        create_manifest(temp_dir, [
            {"name": "plugin_a", "version": "1.0.0", "file": "plugin_a.py", "class": "PluginA"},
            {"name": "plugin_b", "version": "2.0.0", "file": "plugin_b.py", "class": "PluginB"},
        ])

        components = compile_components_from_manifest(temp_dir)

        assert len(components) == 2
        names = {c.__metadata__["name"] for c in components}
        assert names == {"plugin_a", "plugin_b"}

    def test_load_module_based_components(self, temp_dir, reset_sys_modules):
        """Test loading module-based components from manifest."""
        from src.awioc.loader.module_loader import compile_components_from_manifest

        (temp_dir / "module_plugin.py").write_text("""
async def initialize():
    pass
""")

        create_manifest(temp_dir, [
            {"name": "module_plugin", "version": "1.0.0", "file": "module_plugin.py"},
        ])

        components = compile_components_from_manifest(temp_dir)

        assert len(components) == 1
        assert components[0].__metadata__["name"] == "module_plugin"

    def test_missing_manifest_raises_error(self, temp_dir):
        """Test that missing manifest raises FileNotFoundError."""
        from src.awioc.loader.module_loader import compile_components_from_manifest

        with pytest.raises(FileNotFoundError, match="Manifest not found"):
            compile_components_from_manifest(temp_dir)

    def test_missing_component_file_raises_error(self, temp_dir, reset_sys_modules):
        """Test that missing component file raises error."""
        from src.awioc.loader.module_loader import compile_components_from_manifest

        create_manifest(temp_dir, [
            {"name": "missing", "version": "1.0.0", "file": "nonexistent.py"},
        ])

        with pytest.raises(FileNotFoundError):
            compile_components_from_manifest(temp_dir)
