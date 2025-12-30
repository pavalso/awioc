"""Tests for the init command."""

import pytest
import yaml

from src.awioc.commands.base import CommandContext
from src.awioc.commands.init import (
    InitCommand,
    to_snake_case,
    to_pascal_case,
)
from src.awioc.loader.manifest import AWIOC_DIR, MANIFEST_FILENAME


class TestToSnakeCase:
    """Tests for to_snake_case function."""

    def test_simple_name(self):
        """Test simple lowercase name."""
        assert to_snake_case("myapp") == "myapp"

    def test_spaces_to_underscores(self):
        """Test spaces are converted to underscores."""
        assert to_snake_case("my app") == "my_app"

    def test_hyphens_to_underscores(self):
        """Test hyphens are converted to underscores."""
        assert to_snake_case("my-app") == "my_app"

    def test_camelcase_to_snake(self):
        """Test CamelCase is converted to snake_case."""
        assert to_snake_case("MyApp") == "my_app"
        assert to_snake_case("myApp") == "my_app"

    def test_mixed_input(self):
        """Test mixed input with spaces and capitals."""
        assert to_snake_case("My Cool App") == "my_cool_app"

    def test_removes_special_chars(self):
        """Test special characters are removed."""
        assert to_snake_case("my@app!") == "myapp"

    def test_already_snake_case(self):
        """Test already snake_case input."""
        assert to_snake_case("my_cool_app") == "my_cool_app"


class TestToPascalCase:
    """Tests for to_pascal_case function."""

    def test_simple_name(self):
        """Test simple lowercase name."""
        assert to_pascal_case("myapp") == "Myapp"

    def test_spaces_to_pascal(self):
        """Test spaces are handled correctly."""
        assert to_pascal_case("my app") == "MyApp"

    def test_hyphens_to_pascal(self):
        """Test hyphens are handled correctly."""
        assert to_pascal_case("my-app") == "MyApp"

    def test_underscores_to_pascal(self):
        """Test underscores are handled correctly."""
        assert to_pascal_case("my_app") == "MyApp"

    def test_mixed_input(self):
        """Test mixed input."""
        assert to_pascal_case("my cool app") == "MyCoolApp"

    def test_already_pascal(self):
        """Test already PascalCase input."""
        assert to_pascal_case("MyApp") == "Myapp"  # Each word is capitalized


class TestInitCommand:
    """Tests for InitCommand class."""

    @pytest.fixture
    def command(self):
        """Create InitCommand instance."""
        return InitCommand()

    def test_command_properties(self, command):
        """Test command properties."""
        assert command.name == "init"
        assert "initialize" in command.description.lower() or "project" in command.description.lower()
        assert "--name" in command.help_text
        assert "--force" in command.help_text

    @pytest.mark.asyncio
    async def test_execute_creates_all_files(self, command, temp_dir):
        """Test execute creates all expected files."""
        ctx = CommandContext(
            command="init",
            args=[str(temp_dir), "--name", "My App"],
        )

        result = await command.execute(ctx)

        assert result == 0
        # Check all files exist
        assert (temp_dir / "ioc.yaml").exists()
        assert (temp_dir / "my_app.py").exists()
        assert (temp_dir / "__init__.py").exists()
        assert (temp_dir / AWIOC_DIR / MANIFEST_FILENAME).exists()
        assert (temp_dir / ".env").exists()
        assert (temp_dir / "plugins").is_dir()

    @pytest.mark.asyncio
    async def test_execute_default_name(self, command, temp_dir):
        """Test execute with default app name."""
        ctx = CommandContext(
            command="init",
            args=[str(temp_dir)],
        )

        result = await command.execute(ctx)

        assert result == 0
        # Default name is "My App" -> my_app.py
        assert (temp_dir / "my_app.py").exists()

    @pytest.mark.asyncio
    async def test_execute_class_name_format(self, command, temp_dir):
        """Test that class names follow <Name>Component pattern."""
        ctx = CommandContext(
            command="init",
            args=[str(temp_dir), "--name", "Test Service"],
        )

        result = await command.execute(ctx)

        assert result == 0

        # Check app file content has correct class name
        app_content = (temp_dir / "test_service.py").read_text()
        assert "class TestServiceComponent:" in app_content

        # Check __init__.py exports the component
        init_content = (temp_dir / "__init__.py").read_text()
        assert "from .test_service import TestServiceComponent" in init_content
        assert '__all__ = ["TestServiceComponent"]' in init_content

    @pytest.mark.asyncio
    async def test_execute_ioc_yaml_content(self, command, temp_dir):
        """Test ioc.yaml has correct content."""
        ctx = CommandContext(
            command="init",
            args=[str(temp_dir), "--name", "My Service"],
        )

        result = await command.execute(ctx)

        assert result == 0
        config = yaml.safe_load((temp_dir / "ioc.yaml").read_text())
        assert "components" in config
        assert config["components"]["app"] == "my_service:MyServiceComponent()"

    @pytest.mark.asyncio
    async def test_execute_manifest_content(self, command, temp_dir):
        """Test .awioc/manifest.yaml has correct content."""
        ctx = CommandContext(
            command="init",
            args=[str(temp_dir), "--name", "Cool App"],
        )

        result = await command.execute(ctx)

        assert result == 0
        manifest = yaml.safe_load(
            (temp_dir / AWIOC_DIR / MANIFEST_FILENAME).read_text()
        )
        assert manifest["manifest_version"] == "1.0"
        assert manifest["name"] == "Cool App"
        assert len(manifest["components"]) == 1
        component = manifest["components"][0]
        assert component["name"] == "Cool App"
        assert component["file"] == "cool_app.py"
        assert component["class"] == "CoolAppComponent"
        assert component["wire"] is True

    @pytest.mark.asyncio
    async def test_execute_skips_existing_files(self, command, temp_dir):
        """Test execute skips existing files without --force."""
        # Create existing file
        (temp_dir / "ioc.yaml").write_text("existing: true")

        ctx = CommandContext(
            command="init",
            args=[str(temp_dir), "--name", "My App"],
        )

        result = await command.execute(ctx)

        assert result == 0
        # Original content should be preserved
        assert (temp_dir / "ioc.yaml").read_text() == "existing: true"
        # Other files should still be created
        assert (temp_dir / "my_app.py").exists()

    @pytest.mark.asyncio
    async def test_execute_force_overwrites(self, command, temp_dir):
        """Test execute with --force overwrites existing files."""
        # Create existing file
        (temp_dir / "ioc.yaml").write_text("existing: true")

        ctx = CommandContext(
            command="init",
            args=[str(temp_dir), "--name", "My App", "--force"],
        )

        result = await command.execute(ctx)

        assert result == 0
        # File should be overwritten
        content = (temp_dir / "ioc.yaml").read_text()
        assert "existing: true" not in content
        assert "components:" in content

    @pytest.mark.asyncio
    async def test_execute_creates_target_directory(self, command, temp_dir):
        """Test execute creates target directory if it doesn't exist."""
        new_dir = temp_dir / "new_project"

        ctx = CommandContext(
            command="init",
            args=[str(new_dir), "--name", "New Project"],
        )

        result = await command.execute(ctx)

        assert result == 0
        assert new_dir.exists()
        assert (new_dir / "ioc.yaml").exists()

    @pytest.mark.asyncio
    async def test_execute_in_current_dir(self, command, temp_dir, monkeypatch):
        """Test execute in current directory when no path specified."""
        monkeypatch.chdir(temp_dir)

        ctx = CommandContext(
            command="init",
            args=["--name", "Current App"],
        )

        result = await command.execute(ctx)

        assert result == 0
        assert (temp_dir / "ioc.yaml").exists()
        assert (temp_dir / "current_app.py").exists()

    @pytest.mark.asyncio
    async def test_execute_app_component_methods(self, command, temp_dir):
        """Test generated app component has required methods."""
        ctx = CommandContext(
            command="init",
            args=[str(temp_dir), "--name", "Test App"],
        )

        result = await command.execute(ctx)

        assert result == 0
        content = (temp_dir / "test_app.py").read_text()
        assert "async def initialize" in content
        assert "async def wait" in content
        assert "async def shutdown" in content
        assert "@inject" in content
        assert "_shutdown_event" in content

    @pytest.mark.asyncio
    async def test_execute_different_name_formats(self, command, temp_dir):
        """Test various app name formats produce correct output."""
        test_cases = [
            ("SimpleApp", "simple_app.py", "SimpleappComponent"),
            ("my-service", "my_service.py", "MyServiceComponent"),
            ("web_api", "web_api.py", "WebApiComponent"),
            ("Super Cool App", "super_cool_app.py", "SuperCoolAppComponent"),
        ]

        for idx, (name, expected_file, expected_class) in enumerate(test_cases):
            project_dir = temp_dir / f"project_{idx}"

            ctx = CommandContext(
                command="init",
                args=[str(project_dir), "--name", name],
            )

            result = await command.execute(ctx)

            assert result == 0, f"Failed for name: {name}"
            assert (project_dir / expected_file).exists(), f"Missing {expected_file} for name: {name}"

            content = (project_dir / expected_file).read_text()
            assert f"class {expected_class}:" in content, f"Missing class {expected_class} for name: {name}"

    @pytest.mark.asyncio
    async def test_execute_all_files_skipped_returns_success(self, command, temp_dir):
        """Test returns success even when all files already exist."""
        # Create all files that would be created
        (temp_dir / "ioc.yaml").write_text("existing")
        (temp_dir / "my_app.py").write_text("existing")
        (temp_dir / "__init__.py").write_text("existing")
        (temp_dir / ".env").write_text("existing")
        awioc_dir = temp_dir / AWIOC_DIR
        awioc_dir.mkdir()
        (awioc_dir / MANIFEST_FILENAME).write_text("existing")
        (temp_dir / "plugins").mkdir()

        ctx = CommandContext(
            command="init",
            args=[str(temp_dir), "--name", "My App"],
        )

        result = await command.execute(ctx)

        # Should return success (no error)
        assert result == 0
