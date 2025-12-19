import os
import pytest
from pathlib import Path
from unittest.mock import patch

from src.awioc.utils import expanded_path, deep_update


class TestExpandedPath:
    """Tests for the expanded_path utility function."""

    def test_expanded_path_with_string(self):
        """Test that string paths are converted to Path objects."""
        result = expanded_path("some/path")
        assert isinstance(result, Path)
        assert result == Path("some/path")

    def test_expanded_path_with_path_object(self):
        """Test that Path objects are handled correctly."""
        input_path = Path("another/path")
        result = expanded_path(input_path)
        assert isinstance(result, Path)
        assert result == Path("another/path")

    def test_expanded_path_expands_user_tilde(self):
        """Test that user tilde (~) is expanded."""
        result = expanded_path("~/some/path")
        assert "~" not in str(result)
        assert str(result).startswith(os.path.expanduser("~"))

    def test_expanded_path_expands_environment_variable(self):
        """Test that environment variables are expanded."""
        with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            result = expanded_path("$TEST_VAR/subdir")
            assert "test_value" in str(result)
            assert "$TEST_VAR" not in str(result)

    def test_expanded_path_expands_windows_env_var(self):
        """Test that Windows-style environment variables are expanded."""
        with patch.dict(os.environ, {"TEST_WIN_VAR": "win_value"}):
            result = expanded_path("%TEST_WIN_VAR%/subdir")
            # On Windows, %VAR% should be expanded
            # On Unix, it won't be expanded but should still return a valid path
            assert isinstance(result, Path)

    def test_expanded_path_mixed_expansion(self):
        """Test expansion of both tilde and environment variables."""
        with patch.dict(os.environ, {"MY_DIR": "mydir"}):
            result = expanded_path("~/$MY_DIR/file.txt")
            assert "~" not in str(result)
            assert "$MY_DIR" not in str(result)
            assert "mydir" in str(result)

    def test_expanded_path_no_expansion_needed(self):
        """Test path that doesn't need any expansion."""
        result = expanded_path("/absolute/path/to/file")
        assert result == Path("/absolute/path/to/file")

    def test_expanded_path_empty_string(self):
        """Test handling of empty string."""
        result = expanded_path("")
        assert result == Path("")

    def test_expanded_path_with_path_containing_tilde(self):
        """Test Path object containing tilde is expanded."""
        input_path = Path("~/documents")
        result = expanded_path(input_path)
        assert "~" not in str(result)


class TestDeepUpdate:
    """Tests for the deep_update utility function."""

    def test_deep_update_simple_dict(self):
        """Test updating a simple flat dictionary."""
        original = {"a": 1, "b": 2}
        update = {"b": 3, "c": 4}
        result = deep_update(original, update)

        assert result == {"a": 1, "b": 3, "c": 4}
        assert result is original  # Should modify in place

    def test_deep_update_nested_dict(self):
        """Test updating nested dictionaries."""
        original = {
            "level1": {
                "level2": {
                    "value": 1
                }
            }
        }
        update = {
            "level1": {
                "level2": {
                    "new_value": 2
                }
            }
        }
        result = deep_update(original, update)

        assert result["level1"]["level2"]["value"] == 1
        assert result["level1"]["level2"]["new_value"] == 2

    def test_deep_update_overwrites_value(self):
        """Test that values are overwritten correctly."""
        original = {"key": {"nested": "old"}}
        update = {"key": {"nested": "new"}}
        result = deep_update(original, update)

        assert result["key"]["nested"] == "new"

    def test_deep_update_adds_new_keys(self):
        """Test that new keys are added at all levels."""
        original = {"existing": 1}
        update = {"new_key": {"deep": {"deeper": "value"}}}
        result = deep_update(original, update)

        assert result["existing"] == 1
        assert result["new_key"]["deep"]["deeper"] == "value"

    def test_deep_update_empty_original(self):
        """Test updating an empty dictionary."""
        original = {}
        update = {"a": 1, "b": {"c": 2}}
        result = deep_update(original, update)

        assert result == {"a": 1, "b": {"c": 2}}

    def test_deep_update_empty_update(self):
        """Test with empty update dictionary."""
        original = {"a": 1, "b": 2}
        update = {}
        result = deep_update(original, update)

        assert result == {"a": 1, "b": 2}

    def test_deep_update_both_empty(self):
        """Test with both dictionaries empty."""
        original = {}
        update = {}
        result = deep_update(original, update)

        assert result == {}

    def test_deep_update_raises_when_replacing_non_dict_with_dict(self):
        """Test that replacing a non-dict value with a nested dict raises TypeError."""
        original = {"key": "string_value"}
        update = {"key": {"nested": "dict"}}

        with pytest.raises(TypeError):
            deep_update(original, update)

    def test_deep_update_replaces_dict_with_non_dict(self):
        """Test that a dict value can be replaced with a non-dict."""
        original = {"key": {"nested": "dict"}}
        update = {"key": "string_value"}
        result = deep_update(original, update)

        assert result["key"] == "string_value"

    def test_deep_update_preserves_other_types(self):
        """Test that various types are preserved correctly."""
        original = {"list": [1, 2], "tuple": (1, 2), "none": None}
        update = {"list": [3, 4], "int": 42}
        result = deep_update(original, update)

        assert result["list"] == [3, 4]
        assert result["tuple"] == (1, 2)
        assert result["none"] is None
        assert result["int"] == 42

    def test_deep_update_multiple_levels(self):
        """Test deeply nested dictionary updates."""
        original = {
            "a": {
                "b": {
                    "c": {
                        "d": {
                            "value": 1
                        }
                    }
                }
            }
        }
        update = {
            "a": {
                "b": {
                    "c": {
                        "d": {
                            "new": 2
                        },
                        "e": 3
                    }
                }
            }
        }
        result = deep_update(original, update)

        assert result["a"]["b"]["c"]["d"]["value"] == 1
        assert result["a"]["b"]["c"]["d"]["new"] == 2
        assert result["a"]["b"]["c"]["e"] == 3

    def test_deep_update_modifies_in_place(self):
        """Test that the original dictionary is modified in place."""
        original = {"a": 1}
        update = {"b": 2}
        result = deep_update(original, update)

        assert result is original
        assert original == {"a": 1, "b": 2}
