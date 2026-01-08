"""Tool invocation observability for claude8code.

Provides structured logging and metrics for tool, skill, and agent invocations.
Handles timing between pre/post hooks and parameter sanitization.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Global dict to track in-flight tool invocations for timing
_invocation_state: dict[str, "ToolInvocationState"] = {}

# Patterns to redact from logs
SENSITIVE_PATTERNS = [
    "password",
    "secret",
    "token",
    "key",
    "credential",
    "auth",
    "api_key",
    "apikey",
    "private",
    "bearer",
]


@dataclass
class ToolInvocationState:
    """Track state of a tool invocation between pre/post hooks."""

    tool_use_id: str
    tool_name: str
    tool_input: dict[str, Any]
    session_id: str
    start_time: float = field(default_factory=time.perf_counter)

    # Extracted metadata for specific tool types
    subagent_type: str | None = None
    skill_name: str | None = None
    command: str | None = None  # For Bash tool
    file_path: str | None = None  # For Read/Write/Edit tools

    @property
    def duration_seconds(self) -> float:
        """Calculate elapsed time since invocation started."""
        return time.perf_counter() - self.start_time


def extract_tool_metadata(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Extract relevant metadata from tool input based on tool type.

    Args:
        tool_name: Name of the tool being invoked
        tool_input: Tool input parameters

    Returns:
        Dict of extracted metadata for logging
    """
    metadata: dict[str, Any] = {"tool_name": tool_name}

    if tool_name == "Task":
        metadata["subagent_type"] = tool_input.get("subagent_type", "unknown")
        description = tool_input.get("description", "")
        metadata["description"] = description[:200] if len(description) > 200 else description
        # Don't log full prompt - may contain sensitive data, just log length
        prompt = tool_input.get("prompt", "")
        metadata["prompt_length"] = len(prompt)
        metadata["run_in_background"] = tool_input.get("run_in_background", False)

    elif tool_name == "Skill":
        metadata["skill_name"] = tool_input.get("skill", "unknown")
        args = tool_input.get("args", "")
        metadata["args"] = args[:100] if len(args) > 100 else args

    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        # Truncate command to avoid logging sensitive data
        metadata["command"] = command[:200] if len(command) > 200 else command
        metadata["command_length"] = len(command)
        metadata["run_in_background"] = tool_input.get("run_in_background", False)
        metadata["timeout"] = tool_input.get("timeout")

    elif tool_name == "Read":
        metadata["file_path"] = tool_input.get("file_path", "")
        metadata["offset"] = tool_input.get("offset")
        metadata["limit"] = tool_input.get("limit")

    elif tool_name == "Write":
        metadata["file_path"] = tool_input.get("file_path", "")
        content = tool_input.get("content", "")
        metadata["content_length"] = len(content)

    elif tool_name == "Edit":
        metadata["file_path"] = tool_input.get("file_path", "")
        old_string = tool_input.get("old_string", "")
        new_string = tool_input.get("new_string", "")
        metadata["old_string_length"] = len(old_string)
        metadata["new_string_length"] = len(new_string)
        metadata["replace_all"] = tool_input.get("replace_all", False)

    elif tool_name == "WebFetch":
        metadata["url"] = tool_input.get("url", "")
        prompt = tool_input.get("prompt", "")
        metadata["prompt_length"] = len(prompt)

    elif tool_name == "WebSearch":
        metadata["query"] = tool_input.get("query", "")

    elif tool_name == "Glob":
        metadata["pattern"] = tool_input.get("pattern", "")
        metadata["path"] = tool_input.get("path", "")

    elif tool_name == "Grep":
        metadata["pattern"] = tool_input.get("pattern", "")
        metadata["path"] = tool_input.get("path", "")
        metadata["output_mode"] = tool_input.get("output_mode", "files_with_matches")

    elif tool_name == "NotebookEdit":
        metadata["notebook_path"] = tool_input.get("notebook_path", "")
        metadata["edit_mode"] = tool_input.get("edit_mode", "replace")
        metadata["cell_type"] = tool_input.get("cell_type")

    elif tool_name == "TodoWrite":
        todos = tool_input.get("todos", [])
        metadata["todo_count"] = len(todos)

    elif tool_name == "AskUserQuestion":
        questions = tool_input.get("questions", [])
        metadata["question_count"] = len(questions)

    return metadata


def sanitize_for_logging(data: dict[str, Any]) -> dict[str, Any]:
    """Remove or redact potentially sensitive data before logging.

    Args:
        data: Dict of data to sanitize

    Returns:
        Sanitized dict safe for logging
    """
    sanitized: dict[str, Any] = {}

    for key, value in data.items():
        key_lower = key.lower()

        # Check if key contains sensitive pattern
        if any(pattern in key_lower for pattern in SENSITIVE_PATTERNS):
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, str):
            # Check if value contains sensitive patterns
            value_lower = value.lower()
            if any(pattern in value_lower for pattern in SENSITIVE_PATTERNS):
                sanitized[key] = "[REDACTED]"
            elif len(value) > 500:
                sanitized[key] = value[:500] + "...[truncated]"
            else:
                sanitized[key] = value
        elif isinstance(value, dict):
            # Recursively sanitize nested dicts
            sanitized[key] = sanitize_for_logging(value)
        elif isinstance(value, list):
            # Sanitize list items if they're dicts
            sanitized[key] = [
                sanitize_for_logging(item) if isinstance(item, dict) else item for item in value
            ]
        else:
            sanitized[key] = value

    return sanitized


def start_tool_invocation(
    tool_use_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
    session_id: str,
) -> ToolInvocationState:
    """Start tracking a tool invocation (called from pre-hook).

    Args:
        tool_use_id: Unique ID for this tool invocation
        tool_name: Name of the tool being invoked
        tool_input: Tool input parameters
        session_id: Session identifier

    Returns:
        ToolInvocationState for this invocation
    """
    # Extract metadata based on tool type
    metadata = extract_tool_metadata(tool_name, tool_input)

    state = ToolInvocationState(
        tool_use_id=tool_use_id,
        tool_name=tool_name,
        tool_input=tool_input,
        session_id=session_id,
        subagent_type=metadata.get("subagent_type"),
        skill_name=metadata.get("skill_name"),
        command=metadata.get("command"),
        file_path=metadata.get("file_path"),
    )

    # Store state for retrieval in post-hook
    _invocation_state[tool_use_id] = state

    # Log invocation start with sanitized metadata
    log_data = {
        "event": "tool_invocation_start",
        "tool_use_id": tool_use_id,
        "session_id": session_id,
        **sanitize_for_logging(metadata),
    }
    logger.info("[TOOL_START] %s", log_data)

    return state


def complete_tool_invocation(tool_use_id: str) -> ToolInvocationState | None:
    """Complete tracking a tool invocation (called from post-hook).

    Args:
        tool_use_id: Unique ID for this tool invocation

    Returns:
        ToolInvocationState with duration, or None if not found
    """
    state = _invocation_state.pop(tool_use_id, None)

    if state:
        duration = state.duration_seconds

        # Log invocation completion
        log_data = {
            "event": "tool_invocation_end",
            "tool_use_id": tool_use_id,
            "tool_name": state.tool_name,
            "session_id": state.session_id,
            "duration_seconds": round(duration, 4),
        }

        # Add tool-specific info
        if state.subagent_type:
            log_data["subagent_type"] = state.subagent_type
        if state.skill_name:
            log_data["skill_name"] = state.skill_name
        if state.file_path:
            log_data["file_path"] = state.file_path

        logger.info("[TOOL_END] %s", log_data)

    return state


def get_pending_invocations() -> dict[str, ToolInvocationState]:
    """Get currently pending (in-flight) tool invocations.

    Returns:
        Dict of tool_use_id to ToolInvocationState
    """
    return _invocation_state.copy()


def clear_pending_invocations() -> None:
    """Clear all pending invocations (for cleanup/testing)."""
    _invocation_state.clear()
