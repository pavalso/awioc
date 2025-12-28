"""Tests for the generate command."""

import pytest
import yaml

from src.awioc.commands.base import CommandContext
from src.awioc.commands.generate import (
    GenerateCommand,
    _extract_decorator_metadata,
    _extract_module_metadata,
    _scan_python_file,
    _generate_manifest,
    _ast_literal_eval,
)
from src.awioc.loader.manifest import AWIOC_DIR, MANIFEST_FILENAME


class TestAstLiteralEval:
    """Tests for _ast_literal_eval function."""

    def test_constant_value(self):
        """Test evaluating a constant."""
        import ast
        node = ast.parse("42").body[0].value
        result = _ast_literal_eval(node)
        assert result == 42

    def test_string_value(self):
        """Test evaluating a string."""
        import ast
        node = ast.parse('"hello"').body[0].value
        result = _ast_literal_eval(node)
        assert result == "hello"

    def test_list_value(self):
        """Test evaluating a list."""
        import ast
        node = ast.parse("[1, 2, 3]").body[0].value
        result = _ast_literal_eval(node)
        assert result == [1, 2, 3]

    def test_tuple_value(self):
        """Test evaluating a tuple."""
        import ast
        node = ast.parse("(1, 2)").body[0].value
        result = _ast_literal_eval(node)
        assert result == [1, 2]  # Returns as list

    def test_set_value(self):
        """Test evaluating a set."""
        import ast
        node = ast.parse("{1, 2, 3}").body[0].value
        result = _ast_literal_eval(node)
        assert result == {1, 2, 3}

    def test_dict_value(self):
        """Test evaluating a dict."""
        import ast
        node = ast.parse('{"a": 1, "b": 2}').body[0].value
        result = _ast_literal_eval(node)
        assert result == {"a": 1, "b": 2}

    def test_name_reference(self):
        """Test evaluating a name reference."""
        import ast
        node = ast.parse("MyClass").body[0].value
        result = _ast_literal_eval(node)
        assert result == ":MyClass"

    def test_attribute_reference(self):
        """Test evaluating an attribute reference."""
        import ast
        node = ast.parse("module.Class").body[0].value
        result = _ast_literal_eval(node)
        assert result == "module:Class"

    def test_nested_attribute_reference(self):
        """Test evaluating a nested attribute reference."""
        import ast
        node = ast.parse("pkg.module.Class").body[0].value
        result = _ast_literal_eval(node)
        assert result == "pkg:module:Class"

    def test_bool_value(self):
        """Test evaluating boolean values."""
        import ast
        true_node = ast.parse("True").body[0].value
        assert _ast_literal_eval(true_node) is True

        false_node = ast.parse("False").body[0].value
        assert _ast_literal_eval(false_node) is False

    def test_none_value(self):
        """Test evaluating None."""
        import ast
        node = ast.parse("None").body[0].value
        result = _ast_literal_eval(node)
        # None is a constant in Python 3.8+
        assert result is None


class TestExtractDecoratorMetadata:
    """Tests for _extract_decorator_metadata function."""

    def test_extract_simple_decorator(self, temp_dir):
        """Test extracting metadata from simple @as_component decorator."""
        code = '''
from awioc import as_component

@as_component
class MyComponent:
    pass
'''
        import ast
        tree = ast.parse(code)
        class_node = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)][0]

        result = _extract_decorator_metadata(class_node)

        assert result is not None
        assert result["name"] == "MyComponent"
        assert result["class"] == "MyComponent"

    def test_extract_decorator_with_args(self, temp_dir):
        """Test extracting metadata from @as_component with arguments."""
        code = '''
from awioc import as_component

@as_component(name="custom_name", version="1.0.0", description="Test", wire=True)
class MyComponent:
    pass
'''
        import ast
        tree = ast.parse(code)
        class_node = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)][0]

        result = _extract_decorator_metadata(class_node)

        assert result is not None
        assert result["name"] == "custom_name"
        assert result["version"] == "1.0.0"
        assert result["description"] == "Test"
        assert result["wire"] is True

    def test_no_as_component_decorator(self):
        """Test that no metadata is returned for non-as_component decorators."""
        code = '''
@other_decorator
class MyComponent:
    pass
'''
        import ast
        tree = ast.parse(code)
        class_node = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)][0]

        result = _extract_decorator_metadata(class_node)

        assert result is None


class TestExtractModuleMetadata:
    """Tests for _extract_module_metadata function."""

    def test_extract_module_metadata(self):
        """Test extracting __metadata__ dict from module."""
        code = '''
__metadata__ = {
    "name": "module_component",
    "version": "2.0.0",
    "description": "A module component",
    "wire": True,
}
'''
        import ast
        tree = ast.parse(code)

        result = _extract_module_metadata(tree)

        assert result is not None
        assert result["name"] == "module_component"
        assert result["version"] == "2.0.0"
        assert result["description"] == "A module component"
        assert result["wire"] is True

    def test_no_module_metadata(self):
        """Test that None is returned when no __metadata__ exists."""
        code = '''
def some_function():
    pass
'''
        import ast
        tree = ast.parse(code)

        result = _extract_module_metadata(tree)

        assert result is None


class TestScanPythonFile:
    """Tests for _scan_python_file function."""

    def test_scan_module_based_component(self, temp_dir):
        """Test scanning a module-based component."""
        file_path = temp_dir / "module_component.py"
        file_path.write_text('''
__metadata__ = {
    "name": "database_plugin",
    "version": "1.0.0",
    "description": "Database plugin",
    "wire": True,
}

async def initialize():
    pass
''')

        components = _scan_python_file(file_path)

        assert len(components) == 1
        assert components[0]["name"] == "database_plugin"
        assert components[0]["version"] == "1.0.0"
        assert components[0]["wire"] is True

    def test_scan_class_based_component(self, temp_dir):
        """Test scanning a class-based component."""
        file_path = temp_dir / "class_component.py"
        file_path.write_text('''
from awioc import as_component

@as_component(name="my_plugin", version="2.0.0", wire=True)
class MyPlugin:
    async def initialize(self):
        pass
''')

        components = _scan_python_file(file_path)

        assert len(components) == 1
        assert components[0]["name"] == "my_plugin"
        assert components[0]["version"] == "2.0.0"
        assert components[0]["class"] == "MyPlugin"
        assert components[0]["wire"] is True

    def test_scan_multiple_classes(self, temp_dir):
        """Test scanning file with multiple class components."""
        file_path = temp_dir / "multi_class.py"
        file_path.write_text('''
from awioc import as_component

@as_component(name="plugin1", version="1.0.0")
class Plugin1:
    pass

@as_component(name="plugin2", version="2.0.0")
class Plugin2:
    pass
''')

        components = _scan_python_file(file_path)

        assert len(components) == 2
        names = {c["name"] for c in components}
        assert names == {"plugin1", "plugin2"}

    def test_scan_empty_file(self, temp_dir):
        """Test scanning an empty file."""
        file_path = temp_dir / "empty.py"
        file_path.write_text("")

        components = _scan_python_file(file_path)

        assert components == []

    def test_scan_file_without_components(self, temp_dir):
        """Test scanning a file with no components."""
        file_path = temp_dir / "no_components.py"
        file_path.write_text('''
def helper_function():
    return 42

class RegularClass:
    pass
''')

        components = _scan_python_file(file_path)

        assert components == []

    def test_scan_invalid_python(self, temp_dir):
        """Test scanning invalid Python file."""
        file_path = temp_dir / "invalid.py"
        file_path.write_text("this is not valid { python")

        components = _scan_python_file(file_path)

        assert components == []


class TestGenerateManifest:
    """Tests for _generate_manifest function."""

    def test_generate_from_directory(self, temp_dir):
        """Test generating manifest from a directory."""
        # Create some component files
        (temp_dir / "plugin_a.py").write_text('''
__metadata__ = {
    "name": "plugin_a",
    "version": "1.0.0",
    "description": "Plugin A",
    "wire": True,
}
''')
        (temp_dir / "plugin_b.py").write_text('''
from awioc import as_component

@as_component(name="plugin_b", version="2.0.0")
class PluginB:
    pass
''')

        manifest = _generate_manifest(temp_dir)

        assert manifest["manifest_version"] == "1.0"
        assert manifest["name"] == temp_dir.name
        assert len(manifest["components"]) == 2

        names = {c["name"] for c in manifest["components"]}
        assert names == {"plugin_a", "plugin_b"}

    def test_generate_skips_private_files(self, temp_dir):
        """Test that private files (starting with _) are skipped."""
        (temp_dir / "_private.py").write_text('''
__metadata__ = {"name": "private", "version": "1.0.0"}
''')
        (temp_dir / "__init__.py").write_text('''
__metadata__ = {"name": "init", "version": "1.0.0"}
''')
        (temp_dir / "public.py").write_text('''
__metadata__ = {"name": "public", "version": "1.0.0"}
''')

        manifest = _generate_manifest(temp_dir)

        assert len(manifest["components"]) == 1
        assert manifest["components"][0]["name"] == "public"

    def test_generate_empty_directory(self, temp_dir):
        """Test generating manifest from empty directory."""
        manifest = _generate_manifest(temp_dir)

        assert manifest["components"] == []


class TestGenerateCommand:
    """Tests for GenerateCommand class."""

    @pytest.fixture
    def command(self):
        """Create GenerateCommand instance."""
        return GenerateCommand()

    def test_command_properties(self, command):
        """Test command properties."""
        assert command.name == "generate"
        assert "manifest" in command.description.lower()
        assert "manifest" in command.help_text.lower()

    @pytest.mark.asyncio
    async def test_execute_no_args(self, command):
        """Test execute with no arguments shows help."""
        ctx = CommandContext(command="generate", args=[])

        result = await command.execute(ctx)

        assert result == 1  # Error exit code

    @pytest.mark.asyncio
    async def test_execute_manifest_dry_run(self, command, temp_dir):
        """Test execute manifest with --dry-run."""
        # Create a component file
        (temp_dir / "plugin.py").write_text('''
__metadata__ = {
    "name": "test_plugin",
    "version": "1.0.0",
    "description": "Test",
    "wire": True,
}
''')

        ctx = CommandContext(
            command="generate",
            args=["manifest", str(temp_dir), "--dry-run"],
        )

        result = await command.execute(ctx)

        assert result == 0
        # .awioc/manifest.yaml should NOT be created in dry-run mode
        assert not (temp_dir / AWIOC_DIR / MANIFEST_FILENAME).exists()

    @pytest.mark.asyncio
    async def test_execute_manifest_creates_awioc_dir(self, command, temp_dir):
        """Test execute manifest creates .awioc directory and file."""
        (temp_dir / "plugin.py").write_text('''
__metadata__ = {
    "name": "test_plugin",
    "version": "1.0.0",
    "description": "Test",
}
''')

        ctx = CommandContext(
            command="generate",
            args=["manifest", str(temp_dir)],
        )

        result = await command.execute(ctx)

        assert result == 0
        assert (temp_dir / AWIOC_DIR).exists()
        assert (temp_dir / AWIOC_DIR / MANIFEST_FILENAME).exists()

        # Verify content
        manifest = yaml.safe_load((temp_dir / AWIOC_DIR / MANIFEST_FILENAME).read_text())
        assert len(manifest["components"]) == 1
        assert manifest["components"][0]["name"] == "test_plugin"

    @pytest.mark.asyncio
    async def test_execute_manifest_fails_if_exists(self, command, temp_dir):
        """Test execute fails if .awioc/manifest already exists."""
        awioc_dir = temp_dir / AWIOC_DIR
        awioc_dir.mkdir()
        (awioc_dir / MANIFEST_FILENAME).write_text("existing: true")
        (temp_dir / "plugin.py").write_text('''
__metadata__ = {"name": "test", "version": "1.0.0"}
''')

        ctx = CommandContext(
            command="generate",
            args=["manifest", str(temp_dir)],
        )

        result = await command.execute(ctx)

        assert result == 1  # Error exit code

    @pytest.mark.asyncio
    async def test_execute_manifest_force_overwrites(self, command, temp_dir):
        """Test execute with --force overwrites existing manifest."""
        awioc_dir = temp_dir / AWIOC_DIR
        awioc_dir.mkdir()
        (awioc_dir / MANIFEST_FILENAME).write_text("existing: true")
        (temp_dir / "plugin.py").write_text('''
__metadata__ = {"name": "test", "version": "1.0.0"}
''')

        ctx = CommandContext(
            command="generate",
            args=["manifest", str(temp_dir), "--force"],
        )

        result = await command.execute(ctx)

        assert result == 0
        manifest = yaml.safe_load((awioc_dir / MANIFEST_FILENAME).read_text())
        assert manifest["components"][0]["name"] == "test"

    @pytest.mark.asyncio
    async def test_execute_manifest_custom_output(self, command, temp_dir):
        """Test execute with custom output path."""
        (temp_dir / "plugin.py").write_text('''
__metadata__ = {"name": "test", "version": "1.0.0"}
''')
        output_path = temp_dir / "custom_manifest.yaml"

        ctx = CommandContext(
            command="generate",
            args=["manifest", str(temp_dir), "-o", str(output_path)],
        )

        result = await command.execute(ctx)

        assert result == 0
        assert output_path.exists()
        # Default .awioc path should not exist when custom output is used
        assert not (temp_dir / AWIOC_DIR / MANIFEST_FILENAME).exists()

    @pytest.mark.asyncio
    async def test_execute_manifest_nonexistent_directory(self, command, temp_dir):
        """Test execute with non-existent directory."""
        ctx = CommandContext(
            command="generate",
            args=["manifest", str(temp_dir / "nonexistent")],
        )

        result = await command.execute(ctx)

        assert result == 1  # Error exit code

    @pytest.mark.asyncio
    async def test_execute_manifest_no_components_found(self, command, temp_dir):
        """Test execute with directory containing no components."""
        (temp_dir / "not_a_component.py").write_text("x = 42")

        ctx = CommandContext(
            command="generate",
            args=["manifest", str(temp_dir)],
        )

        result = await command.execute(ctx)

        assert result == 0  # Success but warning
