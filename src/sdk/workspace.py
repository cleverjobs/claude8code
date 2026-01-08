"""Workspace loader for Claude Code parity.

Loads workspace configuration from the cwd directory:
- CLAUDE.md - Rules and instructions (injected into system prompt)
- .mcp.json - MCP server configuration
- .claude/commands/*.md - Slash commands
- .claude/skills/*/SKILL.md - Skills
- .claude/agents/*.md - Subagents
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WorkspaceConfig:
    """Loaded workspace configuration."""

    claude_md: str | None = None
    """CLAUDE.md content (project instructions)."""

    mcp_config: dict[str, Any] | None = None
    """.mcp.json parsed content."""

    commands: dict[str, str] = field(default_factory=dict)
    """command_name -> markdown content."""

    skills: dict[str, str] = field(default_factory=dict)
    """skill_name -> SKILL.md content."""

    agents: dict[str, str] = field(default_factory=dict)
    """agent_name -> markdown content."""

    @property
    def has_extensions(self) -> bool:
        """Check if any extensions are loaded."""
        return bool(
            self.claude_md or self.mcp_config or self.commands or self.skills or self.agents
        )


def load_workspace(cwd: Path | str | None) -> WorkspaceConfig:
    """Load all workspace configuration from the given directory.

    Args:
        cwd: Working directory containing workspace configuration.

    Returns:
        WorkspaceConfig with all loaded extensions.
    """
    config = WorkspaceConfig()
    if not cwd:
        return config

    cwd = Path(cwd)
    if not cwd.exists():
        logger.debug(f"Workspace directory does not exist: {cwd}")
        return config

    # Load CLAUDE.md
    claude_md = cwd / "CLAUDE.md"
    if claude_md.exists():
        try:
            config.claude_md = claude_md.read_text().strip()
            logger.debug(f"Loaded CLAUDE.md ({len(config.claude_md)} chars)")
        except Exception as e:
            logger.warning(f"Failed to load CLAUDE.md: {e}")

    # Load .mcp.json
    mcp_json = cwd / ".mcp.json"
    if mcp_json.exists():
        try:
            mcp_data = json.loads(mcp_json.read_text())
            config.mcp_config = mcp_data
            logger.debug(f"Loaded .mcp.json with {len(mcp_data)} keys")
        except Exception as e:
            logger.warning(f"Failed to load .mcp.json: {e}")

    claude_dir = cwd / ".claude"
    if not claude_dir.exists():
        return config

    # Load commands
    commands_dir = claude_dir / "commands"
    if commands_dir.exists():
        for md in sorted(commands_dir.glob("*.md")):
            try:
                config.commands[md.stem] = md.read_text().strip()
            except Exception as e:
                logger.warning(f"Failed to load command {md.stem}: {e}")
        if config.commands:
            logger.debug(f"Loaded {len(config.commands)} commands")

    # Load skills
    skills_dir = claude_dir / "skills"
    if skills_dir.exists():
        for skill_dir in sorted(skills_dir.iterdir()):
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    try:
                        config.skills[skill_dir.name] = skill_file.read_text().strip()
                    except Exception as e:
                        logger.warning(f"Failed to load skill {skill_dir.name}: {e}")
        if config.skills:
            logger.debug(f"Loaded {len(config.skills)} skills")

    # Load agents
    agents_dir = claude_dir / "agents"
    if agents_dir.exists():
        for md in sorted(agents_dir.glob("*.md")):
            try:
                config.agents[md.stem] = md.read_text().strip()
            except Exception as e:
                logger.warning(f"Failed to load agent {md.stem}: {e}")
        if config.agents:
            logger.debug(f"Loaded {len(config.agents)} agents")

    return config


def expand_command(prompt: str, workspace: WorkspaceConfig) -> tuple[str, str | None]:
    """Detect /command in prompt and expand it.

    Args:
        prompt: User prompt that may start with /command.
        workspace: Loaded workspace configuration.

    Returns:
        Tuple of (expanded_prompt, command_name or None).
    """
    prompt = prompt.strip()
    if not prompt.startswith("/"):
        return prompt, None

    # Extract command name (first word after /)
    parts = prompt[1:].split(maxsplit=1)
    command_name = parts[0]
    args = parts[1] if len(parts) > 1 else ""

    if command_name not in workspace.commands:
        return prompt, None  # Unknown command, pass through

    # Expand command
    command_content = workspace.commands[command_name]
    if args:
        expanded = f"{command_content}\n\nUser input: {args}"
    else:
        expanded = command_content

    logger.debug(f"Expanded command /{command_name}")
    return expanded, command_name


def get_project_instructions(workspace: WorkspaceConfig) -> str | None:
    """Get CLAUDE.md project instructions only.

    The SDK handles skills, agents, and commands natively via setting_sources.
    This function only returns the CLAUDE.md content for project-specific instructions.

    Args:
        workspace: Loaded workspace configuration.

    Returns:
        CLAUDE.md content wrapped in XML tags, or None if not present.
    """
    if workspace.claude_md:
        return f"<project-instructions>\n{workspace.claude_md}\n</project-instructions>"
    return None


# Module-level cache for workspace config
_workspace_cache: WorkspaceConfig | None = None
_workspace_cwd: str | None = None


def get_workspace(cwd: str | None) -> WorkspaceConfig:
    """Get workspace configuration, cached by cwd.

    Args:
        cwd: Working directory to load from.

    Returns:
        Cached or freshly loaded WorkspaceConfig.
    """
    global _workspace_cache, _workspace_cwd

    if _workspace_cache is None or _workspace_cwd != cwd:
        _workspace_cache = load_workspace(cwd)
        _workspace_cwd = cwd
        if _workspace_cache.has_extensions:
            logger.info(
                f"Loaded workspace from {cwd}: "
                f"{len(_workspace_cache.commands)} commands, "
                f"{len(_workspace_cache.skills)} skills, "
                f"{len(_workspace_cache.agents)} agents"
            )

    return _workspace_cache


def reload_workspace(cwd: str | None) -> WorkspaceConfig:
    """Force reload workspace configuration.

    Args:
        cwd: Working directory to load from.

    Returns:
        Freshly loaded WorkspaceConfig.
    """
    global _workspace_cache, _workspace_cwd

    _workspace_cache = load_workspace(cwd)
    _workspace_cwd = cwd

    logger.info(f"Reloaded workspace from {cwd}")
    return _workspace_cache
