from datetime import datetime

import pytest

from src.awioc.components.metadata import Internals, RegistrationInfo
from src.awioc.components.registry import (
    as_component,
    component_requires,
    component_internals,
    component_str,
    component_registration,
    clean_module_name,
)


class MockComponent:
    """Mock component for testing."""
    __metadata__ = {
        "name": "mock",
        "version": "1.0.0",
        "description": "Mock component",
        "requires": set()
    }
    initialize = None
    shutdown = None


class TestAsComponent:
    """Tests for as_component function."""

    def test_adds_metadata_to_plain_object(self):
        """Test as_component adds metadata to objects without it."""
        class PlainClass:
            pass

        obj = PlainClass()
        result = as_component(obj)

        assert hasattr(result, "__metadata__")
        # Name uses __qualname__ which includes the enclosing scope
        assert "PlainClass" in result.__metadata__["name"]
        assert result.__metadata__["version"] == "0.0.0"
        assert result.__metadata__["wire"] is True

    def test_preserves_existing_metadata(self):
        """Test as_component preserves existing metadata."""
        class WithMetadata:
            __metadata__ = {
                "name": "custom",
                "version": "2.0.0",
                "description": "Custom"
            }

        obj = WithMetadata()
        result = as_component(obj)

        assert result.__metadata__["name"] == "custom"
        assert result.__metadata__["version"] == "2.0.0"

    def test_adds_initialize_if_missing(self):
        """Test as_component adds initialize attribute if missing."""
        class NoInit:
            __metadata__ = {"name": "test", "version": "1.0.0", "description": ""}

        obj = NoInit()
        result = as_component(obj)

        assert hasattr(result, "initialize")
        assert result.initialize is None

    def test_adds_shutdown_if_missing(self):
        """Test as_component adds shutdown attribute if missing."""
        class NoShutdown:
            __metadata__ = {"name": "test", "version": "1.0.0", "description": ""}

        obj = NoShutdown()
        result = as_component(obj)

        assert hasattr(result, "shutdown")
        assert result.shutdown is None

    def test_preserves_existing_initialize(self):
        """Test as_component preserves existing initialize method."""
        class WithInit:
            __metadata__ = {"name": "test", "version": "1.0.0", "description": ""}

            async def initialize(self):
                return True

        obj = WithInit()
        result = as_component(obj)

        assert result.initialize is not None

    def test_uses_docstring_for_description(self):
        """Test as_component uses __doc__ for description."""
        class Documented:
            """This is a documented class."""
            pass

        obj = Documented()
        result = as_component(obj)

        assert result.__metadata__["description"] == "This is a documented class."

    def test_handles_none_docstring(self):
        """Test as_component handles None docstring."""
        class NoDoc:
            pass

        NoDoc.__doc__ = None
        obj = NoDoc()
        result = as_component(obj)

        assert result.__metadata__["description"] == ""


class TestComponentRequires:
    """Tests for component_requires function."""

    def test_empty_requires(self):
        """Test component with no requirements."""
        class NoRequires:
            __metadata__ = {"name": "test", "version": "1.0.0", "requires": set()}

        result = component_requires(NoRequires())
        assert result == set()

    def test_single_requirement(self):
        """Test component with single requirement."""
        dep = MockComponent()

        class WithRequires:
            __metadata__ = {
                "name": "test",
                "version": "1.0.0",
                "requires": {dep}
            }

        result = component_requires(WithRequires())
        assert dep in result

    def test_multiple_requirements(self):
        """Test component with multiple requirements."""
        dep1 = MockComponent()
        dep2 = MockComponent()
        dep2.__metadata__ = {"name": "dep2", "version": "1.0.0", "requires": set()}

        class MultiRequires:
            __metadata__ = {
                "name": "test",
                "version": "1.0.0",
                "requires": {dep1, dep2}
            }

        result = component_requires(MultiRequires())
        assert dep1 in result
        assert dep2 in result

    def test_recursive_requirements(self):
        """Test recursive requirement resolution."""
        dep2 = MockComponent()
        dep2.__metadata__ = {"name": "dep2", "version": "1.0.0", "requires": set()}

        dep1 = MockComponent()
        dep1.__metadata__ = {"name": "dep1", "version": "1.0.0", "requires": {dep2}}

        class Root:
            __metadata__ = {
                "name": "root",
                "version": "1.0.0",
                "requires": {dep1}
            }

        result = component_requires(Root(), recursive=True)
        assert dep1 in result
        assert dep2 in result

    def test_no_requires_key(self):
        """Test component without requires key in metadata."""
        class NoRequiresKey:
            __metadata__ = {"name": "test", "version": "1.0.0"}

        result = component_requires(NoRequiresKey())
        assert result == set()

    def test_multiple_components(self):
        """Test getting requirements from multiple components."""
        dep1 = MockComponent()
        dep2 = MockComponent()
        dep2.__metadata__ = {"name": "dep2", "version": "1.0.0", "requires": set()}

        class Comp1:
            __metadata__ = {"name": "c1", "version": "1.0.0", "requires": {dep1}}

        class Comp2:
            __metadata__ = {"name": "c2", "version": "1.0.0", "requires": {dep2}}

        result = component_requires(Comp1(), Comp2())
        assert dep1 in result
        assert dep2 in result


class TestComponentInternals:
    """Tests for component_internals function."""

    def test_returns_internals(self):
        """Test component_internals returns _Internals object."""
        class WithInternals:
            __metadata__ = {
                "name": "test",
                "_internals": Internals()
            }

        result = component_internals(WithInternals())
        assert isinstance(result, Internals)

    def test_raises_without_internals(self):
        """Test component_internals raises when no _internals."""
        class NoInternals:
            __metadata__ = {"name": "test"}

        with pytest.raises(AssertionError):
            component_internals(NoInternals())


class TestComponentStr:
    """Tests for component_str function."""

    def test_returns_formatted_string(self):
        """Test component_str returns formatted string."""
        class TestComp:
            __metadata__ = {"name": "my_component", "version": "1.2.3"}

        result = component_str(TestComp())
        assert result == "my_component v1.2.3"

    def test_different_versions(self):
        """Test component_str with different version formats."""
        class SemVer:
            __metadata__ = {"name": "semver", "version": "10.20.30"}

        result = component_str(SemVer())
        assert result == "semver v10.20.30"


class TestComponentRegistration:
    """Tests for component_registration function."""

    def test_returns_registration_info(self):
        """Test component_registration returns RegistrationInfo."""
        reg_info = RegistrationInfo(
            registered_by="test_module",
            registered_at=datetime.now(),
            file="test.py",
            line=10
        )

        class WithRegistration:
            __metadata__ = {
                "name": "test",
                "_internals": Internals(registration=reg_info)
            }

        result = component_registration(WithRegistration())
        assert result is reg_info

    def test_returns_none_without_internals(self):
        """Test component_registration returns None when no internals."""

        class NoInternals:
            __metadata__ = {"name": "test"}

        result = component_registration(NoInternals())
        assert result is None

    def test_returns_none_with_none_internals(self):
        """Test component_registration returns None when internals is None."""

        class NoneInternals:
            __metadata__ = {"name": "test", "_internals": None}

        result = component_registration(NoneInternals())
        assert result is None

    def test_returns_none_without_registration(self):
        """Test component_registration returns None when no registration."""

        class NoRegistration:
            __metadata__ = {
                "name": "test",
                "_internals": Internals()
            }

        result = component_registration(NoRegistration())
        assert result is None


class TestCleanModuleName:
    """Tests for clean_module_name function."""

    def test_removes_init(self):
        """Test clean_module_name removes __init__."""
        result = clean_module_name("__init__.dashboard")
        assert result == "dashboard"

    def test_removes_main(self):
        """Test clean_module_name removes __main__."""
        result = clean_module_name("__main__.app")
        assert result == "app"

    def test_removes_both(self):
        """Test clean_module_name removes both __init__ and __main__."""
        result = clean_module_name("__init__.__main__.module")
        assert result == "module"

    def test_preserves_normal_names(self):
        """Test clean_module_name preserves normal module names."""
        result = clean_module_name("my.package.module")
        assert result == "my.package.module"

    def test_empty_string_returns_unknown(self):
        """Test clean_module_name returns 'unknown' for empty string."""
        result = clean_module_name("")
        assert result == "unknown"

    def test_only_init_returns_original(self):
        """Test clean_module_name with only __init__ returns original."""
        result = clean_module_name("__init__")
        assert result == "__init__"
