"""Tests for the pot command."""

import shutil
from unittest.mock import patch

import pytest
import yaml

from src.awioc.commands.base import CommandContext
from src.awioc.commands.pot import (
    PotCommand,
    get_pot_dir,
    get_pot_path,
    load_pot_manifest,
    save_pot_manifest,
    extract_component_metadata,
    resolve_pot_component,
    POT_MANIFEST_FILENAME,
)


class TestPotHelperFunctions:
    """Tests for pot helper functions."""

    def test_get_pot_dir_creates_directory(self, tmp_path):
        """Test that get_pot_dir creates the pot directory."""
        with patch('src.awioc.commands.pot.DEFAULT_POT_DIR', tmp_path / "pots"):
            pot_dir = get_pot_dir()
            assert pot_dir.exists()
            assert pot_dir == tmp_path / "pots"

    def test_get_pot_path(self, tmp_path):
        """Test get_pot_path returns correct path."""
        with patch('src.awioc.commands.pot.DEFAULT_POT_DIR', tmp_path / "pots"):
            pot_path = get_pot_path("my-pot")
            assert pot_path == tmp_path / "pots" / "my-pot"

    def test_load_pot_manifest_missing_file(self, tmp_path):
        """Test load_pot_manifest returns default when file is missing."""
        pot_path = tmp_path / "my-pot"
        pot_path.mkdir()
        manifest = load_pot_manifest(pot_path)
        assert manifest["manifest_version"] == "1.0"
        assert manifest["name"] == "my-pot"
        assert manifest["components"] == {}

    def test_load_pot_manifest_existing_file(self, tmp_path):
        """Test load_pot_manifest reads existing file."""
        pot_path = tmp_path / "my-pot"
        pot_path.mkdir()
        manifest_path = pot_path / POT_MANIFEST_FILENAME
        manifest_data = {
            "manifest_version": "1.0",
            "name": "my-pot",
            "version": "2.0.0",
            "components": {"comp1": {"name": "Component 1", "version": "1.0.0"}}
        }
        manifest_path.write_text(yaml.dump(manifest_data), encoding="utf-8")

        manifest = load_pot_manifest(pot_path)
        assert manifest["version"] == "2.0.0"
        assert "comp1" in manifest["components"]

    def test_load_pot_manifest_adds_version_if_missing(self, tmp_path):
        """Test load_pot_manifest adds manifest_version if missing."""
        pot_path = tmp_path / "my-pot"
        pot_path.mkdir()
        manifest_path = pot_path / POT_MANIFEST_FILENAME
        manifest_data = {"name": "my-pot", "components": {}}
        manifest_path.write_text(yaml.dump(manifest_data), encoding="utf-8")

        manifest = load_pot_manifest(pot_path)
        assert manifest["manifest_version"] == "1.0"

    def test_save_pot_manifest(self, tmp_path):
        """Test save_pot_manifest writes file correctly."""
        pot_path = tmp_path / "my-pot"
        pot_path.mkdir()
        manifest = {
            "manifest_version": "1.0",
            "name": "my-pot",
            "components": {"comp1": {"name": "Test"}}
        }
        save_pot_manifest(pot_path, manifest)

        manifest_path = pot_path / POT_MANIFEST_FILENAME
        assert manifest_path.exists()
        loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        assert loaded["name"] == "my-pot"

    def test_extract_component_metadata_module_level(self, tmp_path):
        """Test extract_component_metadata for module with __metadata__."""
        component_file = tmp_path / "component.py"
        component_file.write_text('''
__metadata__ = {
    "name": "Test Component",
    "version": "1.0.0",
    "description": "A test component"
}
''', encoding="utf-8")

        metadata = extract_component_metadata(component_file)
        assert metadata is not None
        assert metadata["name"] == "Test Component"
        assert metadata["version"] == "1.0.0"

    def test_extract_component_metadata_class_based(self, tmp_path):
        """Test extract_component_metadata for class with __metadata__."""
        # Use unique filename to avoid module caching issues
        component_file = tmp_path / "class_component_test.py"
        component_file.write_text('''
class MyComponent:
    __metadata__ = {
        "name": "Class Component",
        "version": "2.0.0",
        "description": "A class component"
    }
''', encoding="utf-8")

        metadata = extract_component_metadata(component_file)
        assert metadata is not None
        assert metadata["name"] == "Class Component"
        assert metadata["class_name"] == "MyComponent"

    def test_extract_component_metadata_no_metadata(self, tmp_path):
        """Test extract_component_metadata returns None for no metadata."""
        # Use unique filename to avoid module caching issues
        component_file = tmp_path / "no_meta_component.py"
        component_file.write_text('x = 1', encoding="utf-8")

        metadata = extract_component_metadata(component_file)
        assert metadata is None

    def test_resolve_pot_component_invalid_format(self, tmp_path):
        """Test resolve_pot_component with invalid format."""
        result = resolve_pot_component("not-a-pot-ref")
        assert result is None

    def test_resolve_pot_component_missing_slash(self, tmp_path):
        """Test resolve_pot_component with missing slash."""
        result = resolve_pot_component("@potonly")
        assert result is None

    def test_resolve_pot_component_pot_not_found(self, tmp_path):
        """Test resolve_pot_component when pot doesn't exist."""
        with patch('src.awioc.commands.pot.DEFAULT_POT_DIR', tmp_path / "pots"):
            (tmp_path / "pots").mkdir()
            result = resolve_pot_component("@nonexistent/component")
            assert result is None

    def test_resolve_pot_component_component_not_found(self, tmp_path):
        """Test resolve_pot_component when component doesn't exist."""
        with patch('src.awioc.commands.pot.DEFAULT_POT_DIR', tmp_path / "pots"):
            pot_path = tmp_path / "pots" / "my-pot"
            pot_path.mkdir(parents=True)
            save_pot_manifest(pot_path, {"manifest_version": "1.0", "components": {}})

            result = resolve_pot_component("@my-pot/missing")
            assert result is None


class TestPotCommand:
    """Tests for PotCommand class."""

    @pytest.fixture
    def command(self):
        """Create a PotCommand instance."""
        return PotCommand()

    @pytest.fixture
    def temp_pot_dir(self, tmp_path):
        """Create a temporary pot directory."""
        pot_dir = tmp_path / "pots"
        pot_dir.mkdir()
        with patch('src.awioc.commands.pot.DEFAULT_POT_DIR', pot_dir):
            yield pot_dir

    def test_command_properties(self, command):
        """Test command properties."""
        assert command.name == "pot"
        assert "component repositories" in command.description
        assert "pot" in command.help_text

    @pytest.mark.asyncio
    async def test_execute_no_args_shows_help(self, command, capsys):
        """Test execute with no args shows help."""
        ctx = CommandContext(command="pot", args=[])
        result = await command.execute(ctx)
        assert result == 0
        captured = capsys.readouterr()
        assert "Manage component repositories" in captured.out

    @pytest.mark.asyncio
    async def test_execute_help_subcommand(self, command, capsys):
        """Test execute with help subcommand."""
        ctx = CommandContext(command="pot", args=["help"])
        result = await command.execute(ctx)
        assert result == 0
        captured = capsys.readouterr()
        assert "awioc pot" in captured.out

    @pytest.mark.asyncio
    async def test_execute_unknown_subcommand(self, command, capsys):
        """Test execute with unknown subcommand."""
        ctx = CommandContext(command="pot", args=["unknown"])
        result = await command.execute(ctx)
        assert result == 0  # Shows help

    @pytest.mark.asyncio
    async def test_pot_init_no_name(self, command, temp_pot_dir, capsys):
        """Test pot init without name."""
        ctx = CommandContext(command="pot", args=["init"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_init_invalid_name(self, command, temp_pot_dir, capsys):
        """Test pot init with invalid name."""
        ctx = CommandContext(command="pot", args=["init", "invalid@name!"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_init_success(self, command, temp_pot_dir, capsys):
        """Test pot init creates pot successfully."""
        ctx = CommandContext(command="pot", args=["init", "test-pot"])
        result = await command.execute(ctx)
        assert result == 0
        assert (temp_pot_dir / "test-pot").exists()
        assert (temp_pot_dir / "test-pot" / POT_MANIFEST_FILENAME).exists()

    @pytest.mark.asyncio
    async def test_pot_init_already_exists(self, command, temp_pot_dir, capsys):
        """Test pot init when pot already exists."""
        (temp_pot_dir / "existing-pot").mkdir()
        ctx = CommandContext(command="pot", args=["init", "existing-pot"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_list_no_pots(self, command, temp_pot_dir, capsys):
        """Test pot list when no pots exist."""
        # Remove the pots directory to test empty state
        shutil.rmtree(temp_pot_dir)
        ctx = CommandContext(command="pot", args=["list"])
        result = await command.execute(ctx)
        assert result == 0
        captured = capsys.readouterr()
        assert "No pots" in captured.out

    @pytest.mark.asyncio
    async def test_pot_list_shows_pots(self, command, temp_pot_dir, capsys):
        """Test pot list shows available pots."""
        pot_path = temp_pot_dir / "my-pot"
        pot_path.mkdir()
        save_pot_manifest(pot_path, {
            "manifest_version": "1.0",
            "name": "my-pot",
            "version": "1.0.0",
            "description": "Test pot",
            "components": {}
        })

        ctx = CommandContext(command="pot", args=["list"])
        result = await command.execute(ctx)
        assert result == 0
        captured = capsys.readouterr()
        assert "my-pot" in captured.out

    @pytest.mark.asyncio
    async def test_pot_list_specific_pot(self, command, temp_pot_dir, capsys):
        """Test pot list for specific pot shows components."""
        pot_path = temp_pot_dir / "my-pot"
        pot_path.mkdir()
        save_pot_manifest(pot_path, {
            "manifest_version": "1.0",
            "name": "my-pot",
            "version": "1.0.0",
            "components": {
                "comp1": {"name": "Component 1", "version": "1.0.0", "description": "Test"}
            }
        })

        ctx = CommandContext(command="pot", args=["list", "my-pot"])
        result = await command.execute(ctx)
        assert result == 0
        captured = capsys.readouterr()
        # Check for component key name in output
        assert "comp1" in captured.out

    @pytest.mark.asyncio
    async def test_pot_list_nonexistent_pot(self, command, temp_pot_dir, capsys):
        """Test pot list for nonexistent pot."""
        ctx = CommandContext(command="pot", args=["list", "nonexistent"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_push_no_args(self, command, temp_pot_dir, capsys):
        """Test pot push without arguments."""
        ctx = CommandContext(command="pot", args=["push"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_push_file_not_found(self, command, temp_pot_dir, capsys):
        """Test pot push with nonexistent file."""
        pot_path = temp_pot_dir / "my-pot"
        pot_path.mkdir()
        save_pot_manifest(pot_path, {"manifest_version": "1.0", "components": {}})

        ctx = CommandContext(command="pot", args=["push", "/nonexistent/file.py", "--pot", "my-pot"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_push_no_pot_available(self, command, temp_pot_dir, capsys, tmp_path):
        """Test pot push when no pots are available."""
        component_file = tmp_path / "component.py"
        component_file.write_text('__metadata__ = {"name": "Test", "version": "1.0.0"}')

        ctx = CommandContext(command="pot", args=["push", str(component_file)])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_push_single_file(self, command, temp_pot_dir, tmp_path, capsys):
        """Test pot push for single file component."""
        # Create pot
        pot_path = temp_pot_dir / "my-pot"
        pot_path.mkdir()
        save_pot_manifest(pot_path, {"manifest_version": "1.0", "components": {}})

        # Create component
        component_file = tmp_path / "my_component.py"
        component_file.write_text('''
__metadata__ = {
    "name": "My Component",
    "version": "1.0.0",
    "description": "Test component"
}
''', encoding="utf-8")

        ctx = CommandContext(command="pot", args=["push", str(component_file), "--pot", "my-pot"])
        result = await command.execute(ctx)
        assert result == 0

        # Verify component was pushed
        manifest = load_pot_manifest(pot_path)
        assert "my-component" in manifest["components"]

    @pytest.mark.asyncio
    async def test_pot_push_directory(self, command, temp_pot_dir, tmp_path, capsys):
        """Test pot push for directory component."""
        # Create pot
        pot_path = temp_pot_dir / "my-pot"
        pot_path.mkdir()
        save_pot_manifest(pot_path, {"manifest_version": "1.0", "components": {}})

        # Create component directory
        component_dir = tmp_path / "my_component"
        component_dir.mkdir()
        (component_dir / "__init__.py").write_text('''
class MyComponent:
    __metadata__ = {
        "name": "Dir Component",
        "version": "2.0.0",
        "description": "Directory component"
    }
''', encoding="utf-8")

        ctx = CommandContext(command="pot", args=["push", str(component_dir), "--pot", "my-pot"])
        result = await command.execute(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_pot_push_no_metadata(self, command, temp_pot_dir, tmp_path, capsys):
        """Test pot push for component without metadata."""
        pot_path = temp_pot_dir / "my-pot"
        pot_path.mkdir()
        save_pot_manifest(pot_path, {"manifest_version": "1.0", "components": {}})

        component_file = tmp_path / "no_meta.py"
        component_file.write_text('x = 1', encoding="utf-8")

        ctx = CommandContext(command="pot", args=["push", str(component_file), "--pot", "my-pot"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_push_auto_select_single_pot(self, command, temp_pot_dir, tmp_path, capsys):
        """Test pot push auto-selects when only one pot exists."""
        pot_path = temp_pot_dir / "only-pot"
        pot_path.mkdir()
        save_pot_manifest(pot_path, {"manifest_version": "1.0", "components": {}})

        component_file = tmp_path / "comp.py"
        component_file.write_text('__metadata__ = {"name": "Test", "version": "1.0.0"}')

        ctx = CommandContext(command="pot", args=["push", str(component_file)])
        result = await command.execute(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_pot_push_multiple_pots_no_selection(self, command, temp_pot_dir, tmp_path, capsys):
        """Test pot push fails when multiple pots exist without selection."""
        (temp_pot_dir / "pot1").mkdir()
        (temp_pot_dir / "pot2").mkdir()
        save_pot_manifest(temp_pot_dir / "pot1", {"manifest_version": "1.0", "components": {}})
        save_pot_manifest(temp_pot_dir / "pot2", {"manifest_version": "1.0", "components": {}})

        component_file = tmp_path / "comp.py"
        component_file.write_text('__metadata__ = {"name": "Test", "version": "1.0.0"}')

        ctx = CommandContext(command="pot", args=["push", str(component_file)])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_update_no_args(self, command, temp_pot_dir, capsys):
        """Test pot update without arguments."""
        ctx = CommandContext(command="pot", args=["update"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_update_invalid_format(self, command, temp_pot_dir, capsys):
        """Test pot update with invalid format."""
        ctx = CommandContext(command="pot", args=["update", "invalid"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_update_pot_not_found(self, command, temp_pot_dir, capsys):
        """Test pot update when pot doesn't exist."""
        ctx = CommandContext(command="pot", args=["update", "nonexistent/comp"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_update_component_not_found(self, command, temp_pot_dir, capsys):
        """Test pot update when component doesn't exist."""
        pot_path = temp_pot_dir / "my-pot"
        pot_path.mkdir()
        save_pot_manifest(pot_path, {"manifest_version": "1.0", "components": {}})

        ctx = CommandContext(command="pot", args=["update", "my-pot/missing"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_update_from_source(self, command, temp_pot_dir, tmp_path, capsys):
        """Test pot update from source path."""
        # Create pot with component
        pot_path = temp_pot_dir / "my-pot"
        pot_path.mkdir()
        (pot_path / "comp.py").write_text('__metadata__ = {"name": "Old", "version": "1.0.0"}')
        save_pot_manifest(pot_path, {
            "manifest_version": "1.0",
            "components": {"comp": {"name": "Old", "version": "1.0.0", "path": "comp.py"}}
        })

        # Create updated source
        source_file = tmp_path / "updated.py"
        source_file.write_text('__metadata__ = {"name": "Updated", "version": "2.0.0"}')

        ctx = CommandContext(command="pot", args=["update", "my-pot/comp", str(source_file)])
        result = await command.execute(ctx)
        assert result == 0
        captured = capsys.readouterr()
        assert "2.0.0" in captured.out

    @pytest.mark.asyncio
    async def test_pot_update_refresh_metadata(self, command, temp_pot_dir, capsys):
        """Test pot update refreshes metadata from existing files."""
        import uuid
        unique_name = f"comp_{uuid.uuid4().hex[:8]}"

        pot_path = temp_pot_dir / "my-pot"
        pot_path.mkdir()
        comp_file = pot_path / f"{unique_name}.py"
        comp_file.write_text(f'__metadata__ = {{"name": "Refreshed", "version": "3.0.0"}}')
        save_pot_manifest(pot_path, {
            "manifest_version": "1.0",
            "components": {unique_name: {"name": "Old", "version": "1.0.0", "path": f"{unique_name}.py"}}
        })

        ctx = CommandContext(command="pot", args=["update", f"my-pot/{unique_name}"])
        result = await command.execute(ctx)
        assert result == 0
        captured = capsys.readouterr()
        assert "Refreshed" in captured.out  # Check name was updated

    @pytest.mark.asyncio
    async def test_pot_update_with_at_syntax(self, command, temp_pot_dir, capsys):
        """Test pot update with @pot/component syntax."""
        pot_path = temp_pot_dir / "my-pot"
        pot_path.mkdir()
        (pot_path / "comp.py").write_text('__metadata__ = {"name": "Test", "version": "1.0.0"}')
        save_pot_manifest(pot_path, {
            "manifest_version": "1.0",
            "components": {"comp": {"name": "Test", "version": "1.0.0", "path": "comp.py"}}
        })

        ctx = CommandContext(command="pot", args=["update", "@my-pot/comp"])
        result = await command.execute(ctx)
        assert result == 0

    @pytest.mark.asyncio
    async def test_pot_remove_no_args(self, command, temp_pot_dir, capsys):
        """Test pot remove without arguments."""
        ctx = CommandContext(command="pot", args=["remove"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_remove_invalid_format(self, command, temp_pot_dir, capsys):
        """Test pot remove with invalid format."""
        ctx = CommandContext(command="pot", args=["remove", "invalid"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_remove_pot_not_found(self, command, temp_pot_dir, capsys):
        """Test pot remove when pot doesn't exist."""
        ctx = CommandContext(command="pot", args=["remove", "nonexistent/comp"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_remove_component_not_found(self, command, temp_pot_dir, capsys):
        """Test pot remove when component doesn't exist."""
        pot_path = temp_pot_dir / "my-pot"
        pot_path.mkdir()
        save_pot_manifest(pot_path, {"manifest_version": "1.0", "components": {}})

        ctx = CommandContext(command="pot", args=["remove", "my-pot/missing"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_remove_success(self, command, temp_pot_dir, capsys):
        """Test pot remove succeeds."""
        pot_path = temp_pot_dir / "my-pot"
        pot_path.mkdir()
        comp_file = pot_path / "comp.py"
        comp_file.write_text('x = 1')
        save_pot_manifest(pot_path, {
            "manifest_version": "1.0",
            "components": {"comp": {"name": "Test", "path": "comp.py"}}
        })

        ctx = CommandContext(command="pot", args=["remove", "my-pot/comp"])
        result = await command.execute(ctx)
        assert result == 0
        assert not comp_file.exists()

    @pytest.mark.asyncio
    async def test_pot_remove_directory(self, command, temp_pot_dir, capsys):
        """Test pot remove for directory component."""
        pot_path = temp_pot_dir / "my-pot"
        pot_path.mkdir()
        comp_dir = pot_path / "comp"
        comp_dir.mkdir()
        (comp_dir / "__init__.py").write_text('x = 1')
        save_pot_manifest(pot_path, {
            "manifest_version": "1.0",
            "components": {"comp": {"name": "Test", "path": "comp"}}
        })

        ctx = CommandContext(command="pot", args=["remove", "my-pot/comp"])
        result = await command.execute(ctx)
        assert result == 0
        assert not comp_dir.exists()

    @pytest.mark.asyncio
    async def test_pot_info_no_args(self, command, temp_pot_dir, capsys):
        """Test pot info without arguments."""
        ctx = CommandContext(command="pot", args=["info"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_info_invalid_format(self, command, temp_pot_dir, capsys):
        """Test pot info with invalid format."""
        ctx = CommandContext(command="pot", args=["info", "invalid"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_info_pot_not_found(self, command, temp_pot_dir, capsys):
        """Test pot info when pot doesn't exist."""
        ctx = CommandContext(command="pot", args=["info", "nonexistent/comp"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_info_component_not_found(self, command, temp_pot_dir, capsys):
        """Test pot info when component doesn't exist."""
        pot_path = temp_pot_dir / "my-pot"
        pot_path.mkdir()
        save_pot_manifest(pot_path, {"manifest_version": "1.0", "components": {}})

        ctx = CommandContext(command="pot", args=["info", "my-pot/missing"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_info_success(self, command, temp_pot_dir, capsys):
        """Test pot info shows component details."""
        pot_path = temp_pot_dir / "my-pot"
        pot_path.mkdir()
        save_pot_manifest(pot_path, {
            "manifest_version": "1.0",
            "components": {
                "comp": {
                    "name": "Test Component",
                    "version": "1.5.0",
                    "description": "A test component",
                    "path": "comp.py",
                    "class_name": "TestClass"
                }
            }
        })

        ctx = CommandContext(command="pot", args=["info", "my-pot/comp"])
        result = await command.execute(ctx)
        assert result == 0
        captured = capsys.readouterr()
        assert "Test Component" in captured.out
        assert "1.5.0" in captured.out

    @pytest.mark.asyncio
    async def test_pot_delete_no_args(self, command, temp_pot_dir, capsys):
        """Test pot delete without arguments."""
        ctx = CommandContext(command="pot", args=["delete"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_delete_pot_not_found(self, command, temp_pot_dir, capsys):
        """Test pot delete when pot doesn't exist."""
        ctx = CommandContext(command="pot", args=["delete", "nonexistent"])
        result = await command.execute(ctx)
        assert result == 1

    @pytest.mark.asyncio
    async def test_pot_delete_success(self, command, temp_pot_dir, capsys):
        """Test pot delete succeeds."""
        pot_path = temp_pot_dir / "my-pot"
        pot_path.mkdir()
        save_pot_manifest(pot_path, {"manifest_version": "1.0", "components": {}})

        ctx = CommandContext(command="pot", args=["delete", "my-pot"])
        result = await command.execute(ctx)
        assert result == 0
        assert not pot_path.exists()

    @pytest.mark.asyncio
    async def test_pot_delete_with_components(self, command, temp_pot_dir, capsys):
        """Test pot delete warns about components."""
        pot_path = temp_pot_dir / "my-pot"
        pot_path.mkdir()
        save_pot_manifest(pot_path, {
            "manifest_version": "1.0",
            "components": {"comp1": {}, "comp2": {}}
        })

        ctx = CommandContext(command="pot", args=["delete", "my-pot"])
        result = await command.execute(ctx)
        assert result == 0
        assert not pot_path.exists()


class TestResolvePotComponent:
    """Tests for resolve_pot_component function."""

    def test_non_pot_reference_returns_none(self):
        """Test that non-pot references return None."""
        result = resolve_pot_component("some/path/to/module.py")
        assert result is None

    def test_invalid_pot_reference_without_slash(self):
        """Test invalid pot reference without slash returns None."""
        result = resolve_pot_component("@invalid-ref")
        assert result is None

    def test_pot_not_found_returns_none(self, tmp_path):
        """Test that non-existent pot returns None."""
        with patch('src.awioc.commands.pot.get_pot_path') as mock_get_pot:
            mock_get_pot.return_value = tmp_path / "nonexistent"
            result = resolve_pot_component("@nonexistent/component")
            assert result is None

    def test_component_not_in_pot_returns_none(self, tmp_path):
        """Test component not found in pot returns None."""
        pot_path = tmp_path / "test-pot"
        pot_path.mkdir()
        save_pot_manifest(pot_path, {
            "manifest_version": "1.0",
            "components": {"other": {"path": "other.py"}}
        })

        with patch('src.awioc.commands.pot.get_pot_path') as mock_get_pot:
            mock_get_pot.return_value = pot_path
            result = resolve_pot_component("@test-pot/missing")
            assert result is None

    def test_component_file_not_found_returns_none(self, tmp_path):
        """Test component file not found returns None."""
        pot_path = tmp_path / "test-pot"
        pot_path.mkdir()
        save_pot_manifest(pot_path, {
            "manifest_version": "1.0",
            "components": {"comp": {"path": "comp.py"}}
        })

        with patch('src.awioc.commands.pot.get_pot_path') as mock_get_pot:
            mock_get_pot.return_value = pot_path
            result = resolve_pot_component("@test-pot/comp")
            assert result is None

    def test_resolve_valid_component(self, tmp_path):
        """Test resolving a valid component."""
        pot_path = tmp_path / "test-pot"
        pot_path.mkdir()
        component_file = pot_path / "comp.py"
        component_file.write_text("class MyComp: pass")
        save_pot_manifest(pot_path, {
            "manifest_version": "1.0",
            "components": {"comp": {"path": "comp.py"}}
        })

        with patch('src.awioc.commands.pot.get_pot_path') as mock_get_pot:
            mock_get_pot.return_value = pot_path
            result = resolve_pot_component("@test-pot/comp")
            assert result is not None
            assert result == component_file


class TestExtractComponentMetadataEdgeCases:
    """Additional edge case tests for extract_component_metadata."""

    def test_extract_class_based_metadata(self, tmp_path):
        """Test extracting metadata from class-based component with __metadata__."""
        component_file = tmp_path / "class_comp.py"
        component_file.write_text('''
class MyComponent:
    __metadata__ = {
        "name": "Class Component",
        "version": "2.0.0",
        "description": "A class-based component",
    }
''')
        metadata = extract_component_metadata(component_file)
        assert metadata is not None
        assert metadata["name"] == "Class Component"
        assert metadata["class_name"] == "MyComponent"

    def test_extract_returns_none_for_dict_without_metadata(self, tmp_path):
        """Test that empty file returns None."""
        component_file = tmp_path / "empty.py"
        component_file.write_text("x = 1")
        metadata = extract_component_metadata(component_file)
        assert metadata is None

    def test_extract_raises_for_syntax_error(self, tmp_path):
        """Test that syntax error in file raises exception."""
        component_file = tmp_path / "broken.py"
        component_file.write_text("def broken(: pass")
        with pytest.raises(SyntaxError):
            extract_component_metadata(component_file)
