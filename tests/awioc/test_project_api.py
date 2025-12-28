"""Tests for the AWIOC Project API."""

import shutil
import tempfile
from pathlib import Path

import pytest

from awioc import (
    AWIOCProject,
    is_awioc_project,
    open_project,
    create_project,
)
from awioc.loader.manifest import AWIOC_DIR, MANIFEST_FILENAME


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    tmp = tempfile.mkdtemp()
    yield Path(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def sample_project(temp_dir):
    """Create a sample AWIOC project for testing."""
    # Create project structure
    awioc_dir = temp_dir / AWIOC_DIR
    awioc_dir.mkdir()

    # Create manifest
    manifest_content = """
manifest_version: '1.0'
name: test_project
version: 1.0.0
description: A test project
components:
  - name: TestComponent
    file: test_component.py
    class: TestClass
    version: 1.0.0
    description: A test component
    wire: true
    config:
      - model: test_component:TestConfig
"""
    (awioc_dir / MANIFEST_FILENAME).write_text(manifest_content.strip())

    # Create component file
    component_content = '''
"""Test component module."""

import pydantic
from awioc import as_component, get_config


class TestConfig(pydantic.BaseModel):
    __prefix__ = "test"
    value: str = "default"


@as_component(
    name="TestComponent",
    version="1.0.0",
    description="A test component",
    wire=True,
    config=TestConfig,
)
class TestClass:
    """Test component class."""
    pass
'''
    (temp_dir / "test_component.py").write_text(component_content.strip())

    return temp_dir


class TestIsAwlocProject:
    """Tests for is_awioc_project function."""

    def test_returns_true_for_valid_project(self, sample_project):
        """Should return True for directory with .awioc/manifest.yaml."""
        assert is_awioc_project(sample_project) is True

    def test_returns_false_for_empty_directory(self, temp_dir):
        """Should return False for directory without .awioc."""
        assert is_awioc_project(temp_dir) is False

    def test_returns_false_for_awioc_without_manifest(self, temp_dir):
        """Should return False if .awioc exists but manifest.yaml doesn't."""
        (temp_dir / AWIOC_DIR).mkdir()
        assert is_awioc_project(temp_dir) is False

    def test_accepts_string_path(self, sample_project):
        """Should accept string paths."""
        assert is_awioc_project(str(sample_project)) is True

    def test_works_with_file_path(self, sample_project):
        """Should check parent directory when given a file path."""
        file_path = sample_project / "test_component.py"
        assert is_awioc_project(file_path) is True


class TestOpenProject:
    """Tests for open_project function."""

    def test_opens_existing_project(self, sample_project):
        """Should open and return AWIOCProject for valid project."""
        project = open_project(sample_project)

        assert isinstance(project, AWIOCProject)
        assert project.name == "test_project"
        assert project.version == "1.0.0"

    def test_raises_for_nonexistent_project(self, temp_dir):
        """Should raise FileNotFoundError for directory without manifest."""
        with pytest.raises(FileNotFoundError) as exc_info:
            open_project(temp_dir)

        assert "Not an AWIOC project" in str(exc_info.value)

    def test_accepts_string_path(self, sample_project):
        """Should accept string paths."""
        project = open_project(str(sample_project))
        assert project.name == "test_project"

    def test_works_with_file_path(self, sample_project):
        """Should find project from file within project directory."""
        file_path = sample_project / "test_component.py"
        project = open_project(file_path)
        assert project.name == "test_project"


class TestCreateProject:
    """Tests for create_project function."""

    def test_creates_new_project(self, temp_dir):
        """Should create a new project with manifest."""
        project_dir = temp_dir / "new_project"

        project = create_project(
            project_dir,
            name="My New Project",
            version="2.0.0",
            description="A new project",
        )

        assert project.name == "My New Project"
        assert project.version == "2.0.0"
        assert project.description == "A new project"
        assert is_awioc_project(project_dir)

    def test_creates_directory_if_not_exists(self, temp_dir):
        """Should create the project directory if it doesn't exist."""
        project_dir = temp_dir / "nested" / "new_project"

        project = create_project(project_dir)

        assert project_dir.exists()
        assert is_awioc_project(project_dir)

    def test_uses_directory_name_if_name_not_provided(self, temp_dir):
        """Should use directory name as project name if not specified."""
        project_dir = temp_dir / "my_plugin"

        project = create_project(project_dir)

        assert project.name == "my_plugin"

    def test_raises_if_project_exists(self, sample_project):
        """Should raise FileExistsError if project already exists."""
        with pytest.raises(FileExistsError) as exc_info:
            create_project(sample_project)

        assert "already exists" in str(exc_info.value)

    def test_overwrites_with_flag(self, sample_project):
        """Should overwrite existing project when overwrite=True."""
        project = create_project(
            sample_project,
            name="Overwritten",
            overwrite=True,
        )

        assert project.name == "Overwritten"
        assert len(project.components) == 0  # New empty manifest


class TestAWIOCProjectProperties:
    """Tests for AWIOCProject property access."""

    def test_path_property(self, sample_project):
        """Should return the project path."""
        project = open_project(sample_project)
        assert project.path == sample_project.resolve()

    def test_manifest_path_property(self, sample_project):
        """Should return the manifest path."""
        project = open_project(sample_project)
        expected = sample_project / AWIOC_DIR / MANIFEST_FILENAME
        assert project.manifest_path == expected

    def test_name_property(self, sample_project):
        """Should return project name."""
        project = open_project(sample_project)
        assert project.name == "test_project"

    def test_version_property(self, sample_project):
        """Should return project version."""
        project = open_project(sample_project)
        assert project.version == "1.0.0"

    def test_description_property(self, sample_project):
        """Should return project description."""
        project = open_project(sample_project)
        assert project.description == "A test project"

    def test_components_property(self, sample_project):
        """Should return list of components."""
        project = open_project(sample_project)
        assert len(project.components) == 1
        assert project.components[0].name == "TestComponent"

    def test_len(self, sample_project):
        """Should return number of components."""
        project = open_project(sample_project)
        assert len(project) == 1

    def test_iter(self, sample_project):
        """Should iterate over components."""
        project = open_project(sample_project)
        names = [c.name for c in project]
        assert names == ["TestComponent"]

    def test_contains(self, sample_project):
        """Should check if component exists by name."""
        project = open_project(sample_project)
        assert "TestComponent" in project
        assert "NonExistent" not in project


class TestAWIOCProjectComponentAccess:
    """Tests for AWIOCProject component access methods."""

    def test_get_component(self, sample_project):
        """Should get component by name."""
        project = open_project(sample_project)
        comp = project.get_component("TestComponent")

        assert comp is not None
        assert comp.name == "TestComponent"
        assert comp.class_name == "TestClass"

    def test_get_component_returns_none_for_nonexistent(self, sample_project):
        """Should return None for nonexistent component."""
        project = open_project(sample_project)
        assert project.get_component("NonExistent") is None

    def test_get_component_by_class(self, sample_project):
        """Should get component by class name."""
        project = open_project(sample_project)
        comp = project.get_component_by_class("TestClass")

        assert comp is not None
        assert comp.name == "TestComponent"


class TestAWIOCProjectModification:
    """Tests for AWIOCProject modification methods."""

    def test_add_component(self, sample_project):
        """Should add a new component."""
        project = open_project(sample_project)

        comp = project.add_component(
            name="NewComponent",
            file="new_component.py",
            class_name="NewClass",
            version="1.0.0",
            description="A new component",
        )

        assert comp.name == "NewComponent"
        assert len(project) == 2
        assert project.is_dirty is True

    def test_add_component_with_config(self, sample_project):
        """Should add component with config reference."""
        project = open_project(sample_project)

        comp = project.add_component(
            name="ConfiguredComponent",
            file="configured.py",
            class_name="ConfiguredClass",
            config="configured:MyConfig",
        )

        assert len(comp.get_config_list()) == 1
        assert comp.get_config_list()[0].model == "configured:MyConfig"

    def test_add_component_raises_for_duplicate(self, sample_project):
        """Should raise ValueError for duplicate component name."""
        project = open_project(sample_project)

        with pytest.raises(ValueError) as exc_info:
            project.add_component(
                name="TestComponent",  # Already exists
                file="duplicate.py",
            )

        assert "already exists" in str(exc_info.value)

    def test_remove_component(self, sample_project):
        """Should remove a component."""
        project = open_project(sample_project)

        result = project.remove_component("TestComponent")

        assert result is True
        assert len(project) == 0
        assert project.is_dirty is True

    def test_remove_component_returns_false_for_nonexistent(self, sample_project):
        """Should return False when removing nonexistent component."""
        project = open_project(sample_project)
        result = project.remove_component("NonExistent")
        assert result is False

    def test_update_component(self, sample_project):
        """Should update component properties."""
        project = open_project(sample_project)

        updated = project.update_component(
            "TestComponent",
            version="2.0.0",
            description="Updated description",
        )

        assert updated is not None
        assert updated.version == "2.0.0"
        assert updated.description == "Updated description"
        assert project.is_dirty is True

    def test_update_component_rename(self, sample_project):
        """Should rename a component."""
        project = open_project(sample_project)

        updated = project.update_component(
            "TestComponent",
            new_name="RenamedComponent",
        )

        assert updated.name == "RenamedComponent"
        assert project.get_component("TestComponent") is None
        assert project.get_component("RenamedComponent") is not None

    def test_update_component_returns_none_for_nonexistent(self, sample_project):
        """Should return None when updating nonexistent component."""
        project = open_project(sample_project)
        result = project.update_component("NonExistent", version="2.0.0")
        assert result is None

    def test_set_name(self, sample_project):
        """Should set project name."""
        project = open_project(sample_project)
        project.name = "new_name"

        assert project.name == "new_name"
        assert project.is_dirty is True

    def test_set_version(self, sample_project):
        """Should set project version."""
        project = open_project(sample_project)
        project.version = "2.0.0"

        assert project.version == "2.0.0"
        assert project.is_dirty is True

    def test_set_description(self, sample_project):
        """Should set project description."""
        project = open_project(sample_project)
        project.description = "New description"

        assert project.description == "New description"
        assert project.is_dirty is True


class TestAWIOCProjectPersistence:
    """Tests for AWIOCProject save/reload functionality."""

    def test_save_persists_changes(self, sample_project):
        """Should save changes to disk."""
        project = open_project(sample_project)
        project.add_component(
            name="NewComponent",
            file="new.py",
            class_name="NewClass",
        )
        project.save()

        # Reload and verify
        project2 = open_project(sample_project)
        assert len(project2) == 2
        assert project2.get_component("NewComponent") is not None

    def test_save_clears_dirty_flag(self, sample_project):
        """Should clear dirty flag after save."""
        project = open_project(sample_project)
        project.name = "Modified"

        assert project.is_dirty is True
        project.save()
        assert project.is_dirty is False

    def test_reload_discards_changes(self, sample_project):
        """Should discard unsaved changes on reload."""
        project = open_project(sample_project)
        project.add_component(
            name="UnsavedComponent",
            file="unsaved.py",
        )

        project.reload()

        assert len(project) == 1
        assert project.get_component("UnsavedComponent") is None
        assert project.is_dirty is False

    def test_save_creates_clean_yaml(self, sample_project):
        """Should save clean YAML without empty values."""
        project = open_project(sample_project)
        project.add_component(
            name="MinimalComponent",
            file="minimal.py",
            class_name="MinimalClass",
        )
        project.save()

        # Read raw YAML
        content = project.manifest_path.read_text()

        # Should not have empty wirings/requires lists
        assert "wirings: []" not in content
        assert "requires: []" not in content


class TestAWIOCProjectCompilation:
    """Tests for AWIOCProject component compilation."""

    def test_compile_component(self, sample_project):
        """Should compile a single component by name."""
        project = open_project(sample_project)
        component = project.compile_component("TestComponent")

        assert hasattr(component, "__metadata__")
        assert component.__metadata__["name"] == "TestComponent"

    def test_compile_component_raises_for_nonexistent(self, sample_project):
        """Should raise ValueError for nonexistent component."""
        project = open_project(sample_project)

        with pytest.raises(ValueError) as exc_info:
            project.compile_component("NonExistent")

        assert "not found" in str(exc_info.value)

    def test_compile_components(self, sample_project):
        """Should compile all components."""
        project = open_project(sample_project)
        components = project.compile_components()

        assert len(components) == 1
        assert components[0].__metadata__["name"] == "TestComponent"


class TestAWIOCProjectRepr:
    """Tests for AWIOCProject string representations."""

    def test_repr(self, sample_project):
        """Should return useful repr."""
        project = open_project(sample_project)
        r = repr(project)

        assert "AWIOCProject" in r
        assert "test_project" in r
        assert "components=1" in r

    def test_str(self, sample_project):
        """Should return human-readable string."""
        project = open_project(sample_project)
        s = str(project)

        assert "test_project" in s
        assert "1.0.0" in s
        assert "1 components" in s
