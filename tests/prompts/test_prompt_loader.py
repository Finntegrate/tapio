"""Tests for the prompt loader module."""

import os
import tempfile
from pathlib import Path
from unittest import mock

from tapio.prompts.prompt_loader import get_prompt_path, load_prompt


def test_get_prompt_path_existing_md():
    """Test getting a path for an existing markdown prompt file."""
    with mock.patch("pathlib.Path.exists", return_value=True):
        path = get_prompt_path("test_prompt")
        assert path.endswith("test_prompt.md")


def test_get_prompt_path_existing_txt():
    """Test getting a path for an existing txt prompt file."""
    with mock.patch("pathlib.Path.exists", side_effect=[False, True]):
        path = get_prompt_path("test_prompt")
        assert path.endswith("test_prompt.txt")


def test_get_prompt_path_nonexistent():
    """Test getting a path for a nonexistent prompt file."""
    with mock.patch("pathlib.Path.exists", return_value=False):
        path = get_prompt_path("nonexistent_prompt")
        assert path.endswith("nonexistent_prompt.md")  # Default to md


def test_load_prompt_with_variables():
    """Test loading a prompt template with variable substitution."""
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".md", delete=False) as temp_file:
        temp_file.write("Hello, $name!\nYour score is $score.")
        temp_file.flush()

        prompt_name = Path(temp_file.name).stem
        prompt_path = temp_file.name

        try:
            with mock.patch(
                "tapio.prompts.prompt_loader.get_prompt_path",
                return_value=prompt_path,
            ):
                result = load_prompt(prompt_name, name="John", score=42)
                assert result == "Hello, John!\nYour score is 42."
        finally:
            os.unlink(temp_file.name)


def test_load_prompt_without_variables():
    """Test loading a prompt template without variable substitution."""
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".md", delete=False) as temp_file:
        temp_file.write("This is a test prompt without variables.")
        temp_file.flush()

        prompt_name = Path(temp_file.name).stem
        prompt_path = temp_file.name

        try:
            with mock.patch(
                "tapio.prompts.prompt_loader.get_prompt_path",
                return_value=prompt_path,
            ):
                result = load_prompt(prompt_name)
                assert result == "This is a test prompt without variables."
        finally:
            os.unlink(temp_file.name)


def test_load_nonexistent_prompt():
    """Test loading a nonexistent prompt file returns empty string."""
    with mock.patch("pathlib.Path.exists", return_value=False):
        result = load_prompt("nonexistent_prompt")
        assert result == ""


def test_load_prompt_file_error():
    """Test handling of file errors when loading prompt."""
    with (
        mock.patch("pathlib.Path.exists", return_value=True),
        mock.patch("pathlib.Path.open", side_effect=OSError("Mock error")),
    ):
        result = load_prompt("error_prompt")
        assert result == ""
