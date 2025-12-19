import pytest
from pathlib import Path

from src.awioc.config.loaders import load_file


class TestLoadFile:
    """Tests for file loading functionality."""

    def test_load_yaml_file(self, sample_yaml_config):
        """Test loading a YAML configuration file."""
        result = load_file(sample_yaml_config)

        assert result["app"] == "./app"
        assert "db" in result["libraries"]
        assert len(result["plugins"]) == 2

    def test_load_json_file(self, sample_json_config):
        """Test loading a JSON configuration file."""
        result = load_file(sample_json_config)

        assert result["app"] == "./app"
        assert "db" in result["libraries"]
        assert "./plugins/auth" in result["plugins"]

    def test_load_empty_file(self, empty_config_file):
        """Test loading an empty file returns empty dict."""
        result = load_file(empty_config_file)
        assert result == {}

    def test_load_nonexistent_file_raises(self, temp_dir):
        """Test loading non-existent file raises FileNotFoundError."""
        nonexistent = temp_dir / "nonexistent.yaml"

        with pytest.raises(FileNotFoundError, match="Config file not found"):
            load_file(nonexistent)

    def test_load_directory_raises(self, temp_dir):
        """Test loading a directory raises IsADirectoryError."""
        with pytest.raises(IsADirectoryError):
            load_file(temp_dir)

    def test_load_unsupported_file_type_raises(self, temp_dir):
        """Test loading unsupported file type raises RuntimeError."""
        txt_file = temp_dir / "config.txt"
        txt_file.write_text("some content")

        with pytest.raises(RuntimeError, match="Invalid file type"):
            load_file(txt_file)

    def test_load_none_raises(self):
        """Test loading None raises AssertionError."""
        with pytest.raises(AssertionError):
            load_file(None)

    def test_load_complex_yaml(self, temp_dir):
        """Test loading complex nested YAML structure."""
        config_path = temp_dir / "complex.yaml"
        config_path.write_text("""
database:
  host: localhost
  port: 5432
  credentials:
    user: admin
    password: secret
features:
  - name: feature1
    enabled: true
  - name: feature2
    enabled: false
""")
        result = load_file(config_path)

        assert result["database"]["host"] == "localhost"
        assert result["database"]["port"] == 5432
        assert result["database"]["credentials"]["user"] == "admin"
        assert len(result["features"]) == 2

    def test_load_complex_json(self, temp_dir):
        """Test loading complex nested JSON structure."""
        config_path = temp_dir / "complex.json"
        config_path.write_text("""{
            "database": {
                "host": "localhost",
                "port": 5432
            },
            "features": ["f1", "f2", "f3"]
        }""")
        result = load_file(config_path)

        assert result["database"]["host"] == "localhost"
        assert len(result["features"]) == 3
