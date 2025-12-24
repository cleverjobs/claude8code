"""
Example MCP tools for claude8code.

These tools demonstrate how to create custom tools using the @tool decorator
from claude_agent_sdk. Tools registered here can be used with create_sdk_mcp_server().

Usage:
    from src.sdk.mcp_tools import get_custom_tools, create_tools_server
    tools = get_custom_tools()
    server = create_tools_server()
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool


@tool("get_current_time", "Get the current date and time in ISO format", {})
async def get_current_time(args: dict[str, Any]) -> dict[str, Any]:
    """Get the current date and time."""
    timestamp = datetime.now().astimezone().isoformat()
    return {"content": [{"type": "text", "text": timestamp}]}


@tool(
    "list_directory",
    "List contents of a directory with file metadata",
    {"path": str}
)
async def list_directory(args: dict[str, Any]) -> dict[str, Any]:
    """List contents of a directory."""
    path = args.get("path", ".")
    try:
        target = Path(path).resolve()
        if not target.exists():
            return {"content": [{"type": "text", "text": json.dumps({"error": f"Path does not exist: {path}"})}]}
        if not target.is_dir():
            return {"content": [{"type": "text", "text": json.dumps({"error": f"Not a directory: {path}"})}]}

        entries = []
        for entry in target.iterdir():
            stat = entry.stat()
            entries.append({
                "name": entry.name,
                "type": "directory" if entry.is_dir() else "file",
                "size": stat.st_size if entry.is_file() else None,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })

        result = {
            "path": str(target),
            "entries": sorted(entries, key=lambda x: (x["type"] != "directory", x["name"])),
        }
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
    except PermissionError:
        return {"content": [{"type": "text", "text": json.dumps({"error": f"Permission denied: {path}"})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}]}


@tool(
    "read_file_preview",
    "Read a preview of a file's contents (first N lines)",
    {"path": str, "max_lines": int}
)
async def read_file_preview(args: dict[str, Any]) -> dict[str, Any]:
    """Read a preview of a file's contents."""
    path = args.get("path", "")
    max_lines = args.get("max_lines", 50)
    try:
        target = Path(path).resolve()
        if not target.exists():
            return {"content": [{"type": "text", "text": json.dumps({"error": f"File does not exist: {path}"})}]}
        if not target.is_file():
            return {"content": [{"type": "text", "text": json.dumps({"error": f"Not a file: {path}"})}]}

        with open(target, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total_lines = len(lines)
        preview_lines = lines[:max_lines]
        truncated = total_lines > max_lines

        result = {
            "path": str(target),
            "total_lines": total_lines,
            "showing_lines": len(preview_lines),
            "truncated": truncated,
            "content": "".join(preview_lines),
        }
        return {"content": [{"type": "text", "text": json.dumps(result)}]}
    except PermissionError:
        return {"content": [{"type": "text", "text": json.dumps({"error": f"Permission denied: {path}"})}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}]}


@tool("get_env_info", "Get environment information (cwd, Python version, platform)", {})
async def get_env_info(args: dict[str, Any]) -> dict[str, Any]:
    """Get environment information."""
    import platform
    import sys

    result = {
        "cwd": os.getcwd(),
        "python_version": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "user": os.environ.get("USER", os.environ.get("USERNAME", "unknown")),
    }
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


@tool(
    "search_files",
    "Search for files matching a glob pattern",
    {"pattern": str, "path": str, "max_results": int}
)
async def search_files(args: dict[str, Any]) -> dict[str, Any]:
    """Search for files matching a glob pattern."""
    pattern = args.get("pattern", "*")
    path = args.get("path", ".")
    max_results = args.get("max_results", 20)
    try:
        base = Path(path).resolve()
        if not base.exists():
            return {"content": [{"type": "text", "text": json.dumps({"error": f"Path does not exist: {path}"})}]}

        matches = list(base.glob(pattern))[:max_results]

        result = {
            "base_path": str(base),
            "pattern": pattern,
            "showing": len(matches),
            "matches": [str(m.relative_to(base)) for m in matches],
        }
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}]}


# Registry of all custom tools
_CUSTOM_TOOLS = [
    get_current_time,
    list_directory,
    read_file_preview,
    get_env_info,
    search_files,
]


def get_custom_tools() -> list:
    """
    Get list of custom MCP tools to register with Claude Agent SDK.

    Returns:
        List of SdkMcpTool instances created with @tool decorator.
    """
    return _CUSTOM_TOOLS.copy()


def get_tool_names() -> list[str]:
    """
    Get names of all registered custom tools.

    Returns:
        List of tool names.
    """
    return [t.name for t in _CUSTOM_TOOLS]


def create_tools_server():
    """
    Create an SDK MCP server with all custom tools.

    Returns:
        MCP server instance ready for use with ClaudeAgentOptions.
    """
    return create_sdk_mcp_server("claude8code_tools", _CUSTOM_TOOLS)
