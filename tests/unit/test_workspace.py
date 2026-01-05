"""Tests for workspace loader functionality."""

from __future__ import annotations

import json
from pathlib import Path

from src.sdk.workspace import (
    WorkspaceConfig,
    build_system_context,
    expand_command,
    load_workspace,
)


class TestWorkspaceConfig:
    """Tests for WorkspaceConfig dataclass."""

    def test_empty_config(self) -> None:
        """Test empty workspace config."""
        config = WorkspaceConfig()
        assert config.claude_md is None
        assert config.mcp_config is None
        assert config.commands == {}
        assert config.skills == {}
        assert config.agents == {}

    def test_has_extensions_empty(self) -> None:
        """Test has_extensions is False for empty config."""
        config = WorkspaceConfig()
        assert config.has_extensions is False

    def test_has_extensions_with_claude_md(self) -> None:
        """Test has_extensions is True with CLAUDE.md."""
        config = WorkspaceConfig(claude_md="Some instructions")
        assert config.has_extensions is True

    def test_has_extensions_with_commands(self) -> None:
        """Test has_extensions is True with commands."""
        config = WorkspaceConfig(commands={"commit": "Commit changes"})
        assert config.has_extensions is True


class TestLoadWorkspace:
    """Tests for load_workspace function."""

    def test_load_none_cwd(self) -> None:
        """Test loading with None cwd."""
        config = load_workspace(None)
        assert config.claude_md is None
        assert config.commands == {}

    def test_load_nonexistent_directory(self, tmp_path: Path) -> None:
        """Test loading from nonexistent directory."""
        nonexistent = tmp_path / "nonexistent"
        config = load_workspace(nonexistent)
        assert config.claude_md is None

    def test_load_empty_directory(self, tmp_path: Path) -> None:
        """Test loading from empty directory."""
        config = load_workspace(tmp_path)
        assert config.claude_md is None
        assert config.commands == {}

    def test_load_claude_md(self, tmp_path: Path) -> None:
        """Test loading CLAUDE.md."""
        (tmp_path / "CLAUDE.md").write_text("# Project Rules\n\nDo good things.")
        config = load_workspace(tmp_path)
        assert config.claude_md == "# Project Rules\n\nDo good things."

    def test_load_mcp_json(self, tmp_path: Path) -> None:
        """Test loading .mcp.json."""
        mcp_config = {"mcpServers": {"test": {"command": "test"}}}
        (tmp_path / ".mcp.json").write_text(json.dumps(mcp_config))
        config = load_workspace(tmp_path)
        assert config.mcp_config == mcp_config

    def test_load_commands(self, tmp_path: Path) -> None:
        """Test loading commands."""
        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "commit.md").write_text("# /commit\n\nCommit changes")
        (commands_dir / "pr.md").write_text("# /pr\n\nCreate PR")

        config = load_workspace(tmp_path)
        assert "commit" in config.commands
        assert "pr" in config.commands
        assert "# /commit" in config.commands["commit"]

    def test_load_skills(self, tmp_path: Path) -> None:
        """Test loading skills."""
        skill_dir = tmp_path / ".claude" / "skills" / "database"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Database Skill\n\nHandle DB operations")

        config = load_workspace(tmp_path)
        assert "database" in config.skills
        assert "Database Skill" in config.skills["database"]

    def test_load_agents(self, tmp_path: Path) -> None:
        """Test loading agents."""
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "code-reviewer.md").write_text("# Code Reviewer\n\nReview code")

        config = load_workspace(tmp_path)
        assert "code-reviewer" in config.agents
        assert "Code Reviewer" in config.agents["code-reviewer"]


class TestExpandCommand:
    """Tests for expand_command function."""

    def test_no_command_prefix(self) -> None:
        """Test prompt without / prefix."""
        workspace = WorkspaceConfig(commands={"commit": "Commit instructions"})
        expanded, cmd = expand_command("Hello world", workspace)
        assert expanded == "Hello world"
        assert cmd is None

    def test_unknown_command(self) -> None:
        """Test unknown command passes through."""
        workspace = WorkspaceConfig(commands={"commit": "Commit instructions"})
        expanded, cmd = expand_command("/unknown", workspace)
        assert expanded == "/unknown"
        assert cmd is None

    def test_expand_command_without_args(self) -> None:
        """Test expanding command without additional args."""
        workspace = WorkspaceConfig(commands={"commit": "Commit instructions"})
        expanded, cmd = expand_command("/commit", workspace)
        assert expanded == "Commit instructions"
        assert cmd == "commit"

    def test_expand_command_with_args(self) -> None:
        """Test expanding command with additional args."""
        workspace = WorkspaceConfig(commands={"commit": "Commit instructions"})
        expanded, cmd = expand_command("/commit fix bug in auth", workspace)
        assert "Commit instructions" in expanded
        assert "User input: fix bug in auth" in expanded
        assert cmd == "commit"


class TestBuildSystemContext:
    """Tests for build_system_context function."""

    def test_empty_workspace(self) -> None:
        """Test empty workspace produces no context."""
        workspace = WorkspaceConfig()
        context = build_system_context(workspace)
        assert context == ""

    def test_claude_md_only(self) -> None:
        """Test context with only CLAUDE.md."""
        workspace = WorkspaceConfig(claude_md="Project rules here")
        context = build_system_context(workspace)
        assert "<project-instructions>" in context
        assert "Project rules here" in context
        assert "</project-instructions>" in context

    def test_commands_list(self) -> None:
        """Test commands are listed."""
        workspace = WorkspaceConfig(commands={"commit": "...", "pr": "..."})
        context = build_system_context(workspace)
        assert "<available-commands>" in context
        assert "- /commit" in context
        assert "- /pr" in context

    def test_skills_content(self) -> None:
        """Test skills include full content."""
        workspace = WorkspaceConfig(skills={"database": "DB operations guide"})
        context = build_system_context(workspace)
        assert "<available-skills>" in context
        assert "### database" in context
        assert "DB operations guide" in context

    def test_agents_content(self) -> None:
        """Test agents include full content."""
        workspace = WorkspaceConfig(agents={"code-reviewer": "Review code quality"})
        context = build_system_context(workspace)
        assert "<available-agents>" in context
        assert "### code-reviewer" in context
        assert "Review code quality" in context

    def test_full_workspace(self) -> None:
        """Test context with all components."""
        workspace = WorkspaceConfig(
            claude_md="Project rules",
            commands={"commit": "..."},
            skills={"db": "DB guide"},
            agents={"reviewer": "Review guide"},
        )
        context = build_system_context(workspace)
        assert "<project-instructions>" in context
        assert "<available-commands>" in context
        assert "<available-skills>" in context
        assert "<available-agents>" in context
