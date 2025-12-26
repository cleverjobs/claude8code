"""Unit tests for MCP tools module."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from src.sdk.mcp_tools import (
    create_tools_server,
    get_current_time,
    get_custom_tools,
    get_env_info,
    get_tool_names,
    list_directory,
    read_file_preview,
    search_files,
)

# Access the underlying handler functions from SdkMcpTool objects
_get_current_time = get_current_time.handler
_list_directory = list_directory.handler
_read_file_preview = read_file_preview.handler
_get_env_info = get_env_info.handler
_search_files = search_files.handler


class TestGetCurrentTime:
    """Test get_current_time tool."""

    @pytest.mark.asyncio
    async def test_returns_iso_timestamp(self) -> None:
        """Test that current time is returned in ISO format."""
        result = await _get_current_time({})

        assert "content" in result
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"

        # Parse the timestamp to verify it's valid ISO format
        timestamp = result["content"][0]["text"]
        datetime.fromisoformat(timestamp)  # Should not raise

    @pytest.mark.asyncio
    async def test_timestamp_is_current(self) -> None:
        """Test that timestamp is approximately current."""
        before = datetime.now()
        result = await _get_current_time({})
        after = datetime.now()

        timestamp = datetime.fromisoformat(result["content"][0]["text"])
        # Remove timezone info for comparison
        timestamp_naive = timestamp.replace(tzinfo=None)

        assert before <= timestamp_naive <= after


class TestListDirectory:
    """Test list_directory tool."""

    @pytest.mark.asyncio
    async def test_list_current_directory(self) -> None:
        """Test listing current directory."""
        result = await _list_directory({"path": "."})

        assert "content" in result
        data = json.loads(result["content"][0]["text"])
        assert "path" in data
        assert "entries" in data
        assert isinstance(data["entries"], list)

    @pytest.mark.asyncio
    async def test_list_directory_with_files(self) -> None:
        """Test listing directory with actual files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files and directories
            Path(tmpdir, "file1.txt").write_text("content")
            Path(tmpdir, "file2.py").write_text("code")
            Path(tmpdir, "subdir").mkdir()

            result = await _list_directory({"path": tmpdir})
            data = json.loads(result["content"][0]["text"])

            assert len(data["entries"]) == 3

            # Check that entries have required fields
            for entry in data["entries"]:
                assert "name" in entry
                assert "type" in entry
                assert "modified" in entry

            # Directories should come first (sorted)
            names = [e["name"] for e in data["entries"]]
            assert names[0] == "subdir"

    @pytest.mark.asyncio
    async def test_list_nonexistent_path(self) -> None:
        """Test listing non-existent path."""
        result = await _list_directory({"path": "/nonexistent/path/xyz"})
        data = json.loads(result["content"][0]["text"])

        assert "error" in data
        assert "does not exist" in data["error"]

    @pytest.mark.asyncio
    async def test_list_file_instead_of_directory(self) -> None:
        """Test listing a file path instead of directory."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test")
            temp_path = f.name

        try:
            result = await _list_directory({"path": temp_path})
            data = json.loads(result["content"][0]["text"])

            assert "error" in data
            assert "Not a directory" in data["error"]
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_list_default_path(self) -> None:
        """Test listing with default path (current directory)."""
        result = await _list_directory({})
        data = json.loads(result["content"][0]["text"])

        assert "path" in data
        assert "entries" in data

    @pytest.mark.asyncio
    async def test_permission_denied(self) -> None:
        """Test permission denied error handling."""
        with patch("pathlib.Path.iterdir", side_effect=PermissionError("denied")):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = await _list_directory({"path": tmpdir})
                data = json.loads(result["content"][0]["text"])

                assert "error" in data
                assert "Permission denied" in data["error"]

    @pytest.mark.asyncio
    async def test_generic_exception(self) -> None:
        """Test generic exception handling."""
        with patch("pathlib.Path.iterdir", side_effect=OSError("disk error")):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = await _list_directory({"path": tmpdir})
                data = json.loads(result["content"][0]["text"])

                assert "error" in data


class TestReadFilePreview:
    """Test read_file_preview tool."""

    @pytest.mark.asyncio
    async def test_read_small_file(self) -> None:
        """Test reading a small file completely."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("line1\nline2\nline3\n")
            temp_path = f.name

        try:
            result = await _read_file_preview({"path": temp_path})
            data = json.loads(result["content"][0]["text"])

            assert data["total_lines"] == 3
            assert data["showing_lines"] == 3
            assert data["truncated"] is False
            assert "line1\n" in data["content"]
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_read_large_file_truncated(self) -> None:
        """Test reading a large file with truncation."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            for i in range(100):
                f.write(f"line {i}\n")
            temp_path = f.name

        try:
            result = await _read_file_preview({"path": temp_path, "max_lines": 10})
            data = json.loads(result["content"][0]["text"])

            assert data["total_lines"] == 100
            assert data["showing_lines"] == 10
            assert data["truncated"] is True
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self) -> None:
        """Test reading non-existent file."""
        result = await _read_file_preview({"path": "/nonexistent/file.txt"})
        data = json.loads(result["content"][0]["text"])

        assert "error" in data
        assert "does not exist" in data["error"]

    @pytest.mark.asyncio
    async def test_read_directory_as_file(self) -> None:
        """Test reading a directory as a file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await _read_file_preview({"path": tmpdir})
            data = json.loads(result["content"][0]["text"])

            assert "error" in data
            assert "Not a file" in data["error"]

    @pytest.mark.asyncio
    async def test_read_with_default_max_lines(self) -> None:
        """Test reading with default max_lines."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test content\n")
            temp_path = f.name

        try:
            result = await _read_file_preview({"path": temp_path})
            data = json.loads(result["content"][0]["text"])

            assert "content" in data
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_read_empty_path(self) -> None:
        """Test reading with empty path."""
        result = await _read_file_preview({})
        data = json.loads(result["content"][0]["text"])

        assert "error" in data

    @pytest.mark.asyncio
    async def test_permission_denied(self) -> None:
        """Test permission denied error."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test")
            temp_path = f.name

        try:
            with patch("builtins.open", side_effect=PermissionError("denied")):
                result = await _read_file_preview({"path": temp_path})
                data = json.loads(result["content"][0]["text"])

                assert "error" in data
                assert "Permission denied" in data["error"]
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_generic_exception(self) -> None:
        """Test generic exception handling."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test")
            temp_path = f.name

        try:
            with patch("builtins.open", side_effect=OSError("disk error")):
                result = await _read_file_preview({"path": temp_path})
                data = json.loads(result["content"][0]["text"])

                assert "error" in data
        finally:
            os.unlink(temp_path)


class TestGetEnvInfo:
    """Test get_env_info tool."""

    @pytest.mark.asyncio
    async def test_returns_env_info(self) -> None:
        """Test that environment info is returned."""
        result = await _get_env_info({})
        data = json.loads(result["content"][0]["text"])

        assert "cwd" in data
        assert "python_version" in data
        assert "platform" in data
        assert "machine" in data
        assert "user" in data

    @pytest.mark.asyncio
    async def test_cwd_is_current_directory(self) -> None:
        """Test that cwd matches actual current directory."""
        result = await _get_env_info({})
        data = json.loads(result["content"][0]["text"])

        assert data["cwd"] == os.getcwd()

    @pytest.mark.asyncio
    async def test_user_fallback(self) -> None:
        """Test user detection with fallback."""
        with patch.dict(os.environ, {"USER": "", "USERNAME": ""}, clear=False):
            result = await _get_env_info({})
            data = json.loads(result["content"][0]["text"])
            # Should have some value for user
            assert "user" in data


class TestSearchFiles:
    """Test search_files tool."""

    @pytest.mark.asyncio
    async def test_search_all_files(self) -> None:
        """Test searching for all files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file1.txt").write_text("a")
            Path(tmpdir, "file2.txt").write_text("b")

            result = await _search_files({"pattern": "*", "path": tmpdir})
            data = json.loads(result["content"][0]["text"])

            assert "matches" in data
            assert len(data["matches"]) == 2

    @pytest.mark.asyncio
    async def test_search_with_pattern(self) -> None:
        """Test searching with specific pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file1.txt").write_text("a")
            Path(tmpdir, "file2.py").write_text("b")
            Path(tmpdir, "file3.txt").write_text("c")

            result = await _search_files({"pattern": "*.txt", "path": tmpdir})
            data = json.loads(result["content"][0]["text"])

            assert len(data["matches"]) == 2
            assert all(".txt" in m for m in data["matches"])

    @pytest.mark.asyncio
    async def test_search_with_max_results(self) -> None:
        """Test search with max_results limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(10):
                Path(tmpdir, f"file{i}.txt").write_text(str(i))

            result = await _search_files({"pattern": "*.txt", "path": tmpdir, "max_results": 3})
            data = json.loads(result["content"][0]["text"])

            assert data["showing"] == 3
            assert len(data["matches"]) == 3

    @pytest.mark.asyncio
    async def test_search_nonexistent_path(self) -> None:
        """Test searching in non-existent path."""
        result = await _search_files({"pattern": "*", "path": "/nonexistent/path"})
        data = json.loads(result["content"][0]["text"])

        assert "error" in data
        assert "does not exist" in data["error"]

    @pytest.mark.asyncio
    async def test_search_with_defaults(self) -> None:
        """Test search with default parameters."""
        result = await _search_files({})
        data = json.loads(result["content"][0]["text"])

        # Should work with current directory
        assert "matches" in data or "error" in data

    @pytest.mark.asyncio
    async def test_search_exception_handling(self) -> None:
        """Test generic exception handling."""
        with patch("pathlib.Path.glob", side_effect=OSError("error")):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = await _search_files({"pattern": "*", "path": tmpdir})
                data = json.loads(result["content"][0]["text"])

                assert "error" in data


class TestToolRegistry:
    """Test tool registry functions."""

    def test_get_custom_tools_returns_list(self) -> None:
        """Test that get_custom_tools returns a list."""
        tools = get_custom_tools()
        assert isinstance(tools, list)
        assert len(tools) == 5

    def test_get_custom_tools_returns_copy(self) -> None:
        """Test that get_custom_tools returns a copy."""
        tools1 = get_custom_tools()
        tools2 = get_custom_tools()
        assert tools1 is not tools2

    def test_get_tool_names(self) -> None:
        """Test get_tool_names returns correct names."""
        names = get_tool_names()
        assert isinstance(names, list)
        assert "get_current_time" in names
        assert "list_directory" in names
        assert "read_file_preview" in names
        assert "get_env_info" in names
        assert "search_files" in names

    def test_create_tools_server(self) -> None:
        """Test create_tools_server creates a server."""
        server = create_tools_server()
        assert server is not None
