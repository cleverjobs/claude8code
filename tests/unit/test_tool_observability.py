"""Unit tests for tool observability module."""

import time

from src.core.tool_observability import (
    SENSITIVE_PATTERNS,
    ToolInvocationState,
    clear_pending_invocations,
    complete_tool_invocation,
    extract_tool_metadata,
    get_pending_invocations,
    sanitize_for_logging,
    start_tool_invocation,
)


class TestToolInvocationState:
    """Test ToolInvocationState dataclass."""

    def test_creation(self) -> None:
        """Test creating a ToolInvocationState."""
        state = ToolInvocationState(
            tool_use_id="tool_123",
            tool_name="Bash",
            tool_input={"command": "ls"},
            session_id="sess_456",
        )
        assert state.tool_use_id == "tool_123"
        assert state.tool_name == "Bash"
        assert state.tool_input == {"command": "ls"}
        assert state.session_id == "sess_456"
        assert state.subagent_type is None
        assert state.skill_name is None
        assert state.command is None
        assert state.file_path is None

    def test_duration_seconds(self) -> None:
        """Test duration_seconds property."""
        state = ToolInvocationState(
            tool_use_id="tool_123",
            tool_name="Read",
            tool_input={},
            session_id="sess_456",
        )
        # Wait a small amount of time
        time.sleep(0.01)
        duration = state.duration_seconds
        assert duration >= 0.01
        assert duration < 1.0

    def test_with_metadata(self) -> None:
        """Test state with extracted metadata."""
        state = ToolInvocationState(
            tool_use_id="tool_123",
            tool_name="Task",
            tool_input={"subagent_type": "Explore"},
            session_id="sess_456",
            subagent_type="Explore",
        )
        assert state.subagent_type == "Explore"


class TestExtractToolMetadata:
    """Test extract_tool_metadata function."""

    def test_task_tool(self) -> None:
        """Test metadata extraction for Task tool."""
        tool_input = {
            "subagent_type": "Explore",
            "description": "Search for files",
            "prompt": "Find all Python files in the project" * 100,  # Long prompt
            "run_in_background": True,
        }
        metadata = extract_tool_metadata("Task", tool_input)

        assert metadata["tool_name"] == "Task"
        assert metadata["subagent_type"] == "Explore"
        assert metadata["description"] == "Search for files"
        assert metadata["prompt_length"] == len(str(tool_input["prompt"]))
        assert metadata["run_in_background"] is True

    def test_task_tool_truncates_description(self) -> None:
        """Test that long descriptions are truncated."""
        long_desc = "x" * 300
        tool_input = {
            "description": long_desc,
            "prompt": "test",
        }
        metadata = extract_tool_metadata("Task", tool_input)
        assert len(metadata["description"]) == 200

    def test_skill_tool(self) -> None:
        """Test metadata extraction for Skill tool."""
        tool_input = {
            "skill": "commit",
            "args": "-m 'test commit'",
        }
        metadata = extract_tool_metadata("Skill", tool_input)

        assert metadata["tool_name"] == "Skill"
        assert metadata["skill_name"] == "commit"
        assert metadata["args"] == "-m 'test commit'"

    def test_bash_tool(self) -> None:
        """Test metadata extraction for Bash tool."""
        tool_input = {
            "command": "git status",
            "run_in_background": False,
            "timeout": 30000,
        }
        metadata = extract_tool_metadata("Bash", tool_input)

        assert metadata["tool_name"] == "Bash"
        assert metadata["command"] == "git status"
        assert metadata["command_length"] == len("git status")
        assert metadata["run_in_background"] is False
        assert metadata["timeout"] == 30000

    def test_bash_tool_truncates_command(self) -> None:
        """Test that long commands are truncated."""
        long_cmd = "echo " + "x" * 300
        tool_input = {"command": long_cmd}
        metadata = extract_tool_metadata("Bash", tool_input)
        assert len(metadata["command"]) == 200
        assert metadata["command_length"] == len(long_cmd)

    def test_read_tool(self) -> None:
        """Test metadata extraction for Read tool."""
        tool_input = {
            "file_path": "/path/to/file.py",
            "offset": 10,
            "limit": 100,
        }
        metadata = extract_tool_metadata("Read", tool_input)

        assert metadata["tool_name"] == "Read"
        assert metadata["file_path"] == "/path/to/file.py"
        assert metadata["offset"] == 10
        assert metadata["limit"] == 100

    def test_write_tool(self) -> None:
        """Test metadata extraction for Write tool."""
        tool_input = {
            "file_path": "/path/to/file.py",
            "content": "print('hello world')",
        }
        metadata = extract_tool_metadata("Write", tool_input)

        assert metadata["tool_name"] == "Write"
        assert metadata["file_path"] == "/path/to/file.py"
        assert metadata["content_length"] == len("print('hello world')")

    def test_edit_tool(self) -> None:
        """Test metadata extraction for Edit tool."""
        tool_input = {
            "file_path": "/path/to/file.py",
            "old_string": "old text",
            "new_string": "new text",
            "replace_all": True,
        }
        metadata = extract_tool_metadata("Edit", tool_input)

        assert metadata["tool_name"] == "Edit"
        assert metadata["file_path"] == "/path/to/file.py"
        assert metadata["old_string_length"] == len("old text")
        assert metadata["new_string_length"] == len("new text")
        assert metadata["replace_all"] is True

    def test_webfetch_tool(self) -> None:
        """Test metadata extraction for WebFetch tool."""
        tool_input = {
            "url": "https://example.com",
            "prompt": "Extract the main content",
        }
        metadata = extract_tool_metadata("WebFetch", tool_input)

        assert metadata["tool_name"] == "WebFetch"
        assert metadata["url"] == "https://example.com"
        assert metadata["prompt_length"] == len("Extract the main content")

    def test_websearch_tool(self) -> None:
        """Test metadata extraction for WebSearch tool."""
        tool_input = {"query": "Claude Code documentation"}
        metadata = extract_tool_metadata("WebSearch", tool_input)

        assert metadata["tool_name"] == "WebSearch"
        assert metadata["query"] == "Claude Code documentation"

    def test_glob_tool(self) -> None:
        """Test metadata extraction for Glob tool."""
        tool_input = {
            "pattern": "**/*.py",
            "path": "/project/src",
        }
        metadata = extract_tool_metadata("Glob", tool_input)

        assert metadata["tool_name"] == "Glob"
        assert metadata["pattern"] == "**/*.py"
        assert metadata["path"] == "/project/src"

    def test_grep_tool(self) -> None:
        """Test metadata extraction for Grep tool."""
        tool_input = {
            "pattern": "def test_",
            "path": "/project/tests",
            "output_mode": "content",
        }
        metadata = extract_tool_metadata("Grep", tool_input)

        assert metadata["tool_name"] == "Grep"
        assert metadata["pattern"] == "def test_"
        assert metadata["path"] == "/project/tests"
        assert metadata["output_mode"] == "content"

    def test_notebook_edit_tool(self) -> None:
        """Test metadata extraction for NotebookEdit tool."""
        tool_input = {
            "notebook_path": "/project/notebook.ipynb",
            "edit_mode": "insert",
            "cell_type": "code",
        }
        metadata = extract_tool_metadata("NotebookEdit", tool_input)

        assert metadata["tool_name"] == "NotebookEdit"
        assert metadata["notebook_path"] == "/project/notebook.ipynb"
        assert metadata["edit_mode"] == "insert"
        assert metadata["cell_type"] == "code"

    def test_todo_write_tool(self) -> None:
        """Test metadata extraction for TodoWrite tool."""
        tool_input = {
            "todos": [
                {"content": "Task 1", "status": "pending"},
                {"content": "Task 2", "status": "in_progress"},
            ]
        }
        metadata = extract_tool_metadata("TodoWrite", tool_input)

        assert metadata["tool_name"] == "TodoWrite"
        assert metadata["todo_count"] == 2

    def test_ask_user_question_tool(self) -> None:
        """Test metadata extraction for AskUserQuestion tool."""
        tool_input = {
            "questions": [
                {"question": "Q1?", "options": []},
                {"question": "Q2?", "options": []},
            ]
        }
        metadata = extract_tool_metadata("AskUserQuestion", tool_input)

        assert metadata["tool_name"] == "AskUserQuestion"
        assert metadata["question_count"] == 2

    def test_unknown_tool(self) -> None:
        """Test metadata extraction for unknown tool."""
        tool_input = {"custom_param": "value"}
        metadata = extract_tool_metadata("UnknownTool", tool_input)

        assert metadata["tool_name"] == "UnknownTool"
        assert len(metadata) == 1  # Only tool_name


class TestSanitizeForLogging:
    """Test sanitize_for_logging function."""

    def test_redacts_sensitive_keys(self) -> None:
        """Test that sensitive keys are redacted."""
        data = {
            "username": "user123",
            "password": "secret123",
            "api_key": "sk-1234",
            "token": "bearer-token",
        }
        sanitized = sanitize_for_logging(data)

        assert sanitized["username"] == "user123"
        assert sanitized["password"] == "[REDACTED]"
        assert sanitized["api_key"] == "[REDACTED]"
        assert sanitized["token"] == "[REDACTED]"

    def test_redacts_sensitive_values(self) -> None:
        """Test that values containing sensitive patterns are redacted."""
        data = {
            "config": "API_KEY=secret123",
            "env": "PASSWORD=hunter2",
            "normal": "just normal text",
        }
        sanitized = sanitize_for_logging(data)

        assert sanitized["config"] == "[REDACTED]"
        assert sanitized["env"] == "[REDACTED]"
        assert sanitized["normal"] == "just normal text"

    def test_truncates_long_values(self) -> None:
        """Test that long string values are truncated."""
        long_value = "x" * 600
        data = {"content": long_value}
        sanitized = sanitize_for_logging(data)

        assert len(sanitized["content"]) == 500 + len("...[truncated]")
        assert sanitized["content"].endswith("...[truncated]")

    def test_sanitizes_nested_dicts(self) -> None:
        """Test that nested dicts are sanitized recursively."""
        data = {
            "outer": {
                "password": "secret",
                "safe": "value",
            }
        }
        sanitized = sanitize_for_logging(data)

        assert sanitized["outer"]["password"] == "[REDACTED]"
        assert sanitized["outer"]["safe"] == "value"

    def test_sanitizes_lists_of_dicts(self) -> None:
        """Test that lists containing dicts are sanitized."""
        data = {
            "items": [
                {"name": "item1", "secret": "hidden"},
                {"name": "item2", "token": "tok_123"},
            ]
        }
        sanitized = sanitize_for_logging(data)

        assert sanitized["items"][0]["name"] == "item1"
        assert sanitized["items"][0]["secret"] == "[REDACTED]"
        assert sanitized["items"][1]["token"] == "[REDACTED]"

    def test_preserves_non_string_values(self) -> None:
        """Test that non-string values are preserved."""
        data = {
            "count": 42,
            "enabled": True,
            "ratio": 3.14,
            "nothing": None,
        }
        sanitized = sanitize_for_logging(data)

        assert sanitized["count"] == 42
        assert sanitized["enabled"] is True
        assert sanitized["ratio"] == 3.14
        assert sanitized["nothing"] is None

    def test_case_insensitive_matching(self) -> None:
        """Test that pattern matching is case-insensitive."""
        data = {
            "PASSWORD": "secret",
            "Api_Key": "key123",
            "SECRET": "hidden",
        }
        sanitized = sanitize_for_logging(data)

        assert sanitized["PASSWORD"] == "[REDACTED]"
        assert sanitized["Api_Key"] == "[REDACTED]"
        assert sanitized["SECRET"] == "[REDACTED]"


class TestSensitivePatterns:
    """Test SENSITIVE_PATTERNS configuration."""

    def test_patterns_exist(self) -> None:
        """Test that sensitive patterns are defined."""
        assert len(SENSITIVE_PATTERNS) > 0

    def test_common_patterns_covered(self) -> None:
        """Test that common sensitive patterns are covered."""
        required_patterns = ["password", "secret", "token", "key", "credential"]
        for pattern in required_patterns:
            assert pattern in SENSITIVE_PATTERNS, f"Missing pattern: {pattern}"


class TestStartToolInvocation:
    """Test start_tool_invocation function."""

    def setup_method(self) -> None:
        """Clear pending invocations before each test."""
        clear_pending_invocations()

    def test_starts_tracking(self) -> None:
        """Test that invocation is tracked."""
        state = start_tool_invocation(
            tool_use_id="tool_123",
            tool_name="Bash",
            tool_input={"command": "ls"},
            session_id="sess_456",
        )

        assert state.tool_use_id == "tool_123"
        assert state.tool_name == "Bash"
        pending = get_pending_invocations()
        assert "tool_123" in pending

    def test_extracts_subagent_type(self) -> None:
        """Test that Task tool extracts subagent_type."""
        state = start_tool_invocation(
            tool_use_id="tool_task",
            tool_name="Task",
            tool_input={"subagent_type": "Explore", "prompt": "test"},
            session_id="sess_456",
        )

        assert state.subagent_type == "Explore"

    def test_extracts_skill_name(self) -> None:
        """Test that Skill tool extracts skill_name."""
        state = start_tool_invocation(
            tool_use_id="tool_skill",
            tool_name="Skill",
            tool_input={"skill": "commit", "args": "-m test"},
            session_id="sess_456",
        )

        assert state.skill_name == "commit"

    def test_extracts_command(self) -> None:
        """Test that Bash tool extracts command."""
        state = start_tool_invocation(
            tool_use_id="tool_bash",
            tool_name="Bash",
            tool_input={"command": "git status"},
            session_id="sess_456",
        )

        assert state.command == "git status"

    def test_extracts_file_path(self) -> None:
        """Test that file tools extract file_path."""
        for tool_name in ["Read", "Write", "Edit"]:
            clear_pending_invocations()
            state = start_tool_invocation(
                tool_use_id=f"tool_{tool_name.lower()}",
                tool_name=tool_name,
                tool_input={"file_path": "/path/to/file.py"},
                session_id="sess_456",
            )
            assert state.file_path == "/path/to/file.py"


class TestCompleteToolInvocation:
    """Test complete_tool_invocation function."""

    def setup_method(self) -> None:
        """Clear pending invocations before each test."""
        clear_pending_invocations()

    def test_completes_and_returns_state(self) -> None:
        """Test that completion returns state with duration."""
        start_tool_invocation(
            tool_use_id="tool_123",
            tool_name="Read",
            tool_input={},
            session_id="sess_456",
        )

        time.sleep(0.01)  # Brief delay for measurable duration
        state = complete_tool_invocation("tool_123")

        assert state is not None
        assert state.tool_use_id == "tool_123"
        assert state.duration_seconds >= 0.01

    def test_removes_from_pending(self) -> None:
        """Test that completion removes from pending."""
        start_tool_invocation(
            tool_use_id="tool_123",
            tool_name="Read",
            tool_input={},
            session_id="sess_456",
        )

        complete_tool_invocation("tool_123")

        pending = get_pending_invocations()
        assert "tool_123" not in pending

    def test_returns_none_for_unknown(self) -> None:
        """Test that unknown tool_use_id returns None."""
        state = complete_tool_invocation("unknown_tool")
        assert state is None


class TestGetPendingInvocations:
    """Test get_pending_invocations function."""

    def setup_method(self) -> None:
        """Clear pending invocations before each test."""
        clear_pending_invocations()

    def test_returns_copy(self) -> None:
        """Test that returns a copy, not the original."""
        start_tool_invocation(
            tool_use_id="tool_123",
            tool_name="Read",
            tool_input={},
            session_id="sess_456",
        )

        pending1 = get_pending_invocations()
        pending2 = get_pending_invocations()

        assert pending1 is not pending2
        assert pending1 == pending2

    def test_empty_when_cleared(self) -> None:
        """Test that returns empty dict after clear."""
        clear_pending_invocations()
        pending = get_pending_invocations()
        assert len(pending) == 0


class TestClearPendingInvocations:
    """Test clear_pending_invocations function."""

    def test_clears_all(self) -> None:
        """Test that clears all pending invocations."""
        start_tool_invocation(
            tool_use_id="tool_1",
            tool_name="Read",
            tool_input={},
            session_id="sess_1",
        )
        start_tool_invocation(
            tool_use_id="tool_2",
            tool_name="Write",
            tool_input={},
            session_id="sess_2",
        )

        clear_pending_invocations()

        pending = get_pending_invocations()
        assert len(pending) == 0
