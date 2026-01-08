"""Tests for workspace loader functionality."""

from __future__ import annotations

import json
from pathlib import Path

from src.sdk.workspace import (
    WorkspaceConfig,
    expand_command,
    get_project_instructions,
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


class TestGetProjectInstructions:
    """Tests for get_project_instructions function."""

    def test_returns_none_for_empty_workspace(self) -> None:
        """Test returns None when no CLAUDE.md present."""
        workspace = WorkspaceConfig()
        result = get_project_instructions(workspace)
        assert result is None

    def test_returns_none_with_only_commands(self) -> None:
        """Test returns None when only commands are present."""
        workspace = WorkspaceConfig(commands={"commit": "..."})
        result = get_project_instructions(workspace)
        assert result is None

    def test_returns_formatted_claude_md(self) -> None:
        """Test returns CLAUDE.md content wrapped in XML tags."""
        workspace = WorkspaceConfig(claude_md="Project specific rules")
        result = get_project_instructions(workspace)
        assert result is not None
        assert "<project-instructions>" in result
        assert "Project specific rules" in result
        assert "</project-instructions>" in result

    def test_ignores_skills_agents_commands(self) -> None:
        """Test only returns CLAUDE.md, ignores other extensions."""
        workspace = WorkspaceConfig(
            claude_md="My rules",
            commands={"commit": "..."},
            skills={"db": "..."},
            agents={"reviewer": "..."},
        )
        result = get_project_instructions(workspace)
        assert result is not None
        assert "My rules" in result
        # Should not include other extensions
        assert "commit" not in result
        assert "db" not in result
        assert "reviewer" not in result
