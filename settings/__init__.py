"""Settings loader for claude8code.

Loads configuration from settings/settings.toml (non-secrets) and .env (secrets).
"""

from __future__ import annotations

import tomllib
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Path to settings.toml (relative to this file)
SETTINGS_DIR = Path(__file__).parent
SETTINGS_TOML_PATH = SETTINGS_DIR / "settings.toml"


class SDKMessageMode(str, Enum):
    """How to handle Claude SDK internal messages in responses."""

    FORWARD = "forward"  # Pass through raw SDK messages
    FORMATTED = "formatted"  # Convert to XML-tagged text format
    IGNORE = "ignore"  # Strip SDK messages, only final text


class SystemPromptMode(str, Enum):
    """System prompt configuration mode."""

    CLAUDE_CODE = "claude_code"  # Use Claude Code's preset
    CUSTOM = "custom"  # Use custom_system_prompt


class ServerConfig(BaseModel):
    """Server configuration."""

    host: str = "0.0.0.0"
    port: int = 8787
    debug: bool = False
    workers: int = 1
    log_level: str = "info"


class SystemPromptConfig(BaseModel):
    """System prompt configuration."""

    mode: SystemPromptMode = SystemPromptMode.CLAUDE_CODE
    custom_prompt: str | None = None


class ToolsConfig(BaseModel):
    """Tools configuration."""

    allowed: list[str] = Field(default_factory=list)


class HooksConfig(BaseModel):
    """SDK Hooks configuration."""

    audit_enabled: bool = True
    permission_enabled: bool = True
    rate_limit_enabled: bool = False
    rate_limit_requests_per_minute: int = 60
    deny_patterns: list[str] = Field(default_factory=list)


class ClaudeConfig(BaseModel):
    """Claude Agent SDK configuration."""

    default_model: str = "claude-sonnet-4-5-20250514"
    max_turns: int = 10
    permission_mode: str = "acceptEdits"
    cwd: str | None = None
    sdk_message_mode: SDKMessageMode = SDKMessageMode.FORWARD
    system_prompt: SystemPromptConfig = Field(default_factory=SystemPromptConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    hooks: HooksConfig = Field(default_factory=HooksConfig)
    setting_sources: list[str] = Field(default_factory=lambda: ["user", "project", "local"])


class SecurityConfig(BaseModel):
    """Security configuration."""

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


class SessionConfig(BaseModel):
    """Session pool configuration."""

    max_sessions: int = 100
    ttl_seconds: int = 3600
    cleanup_interval_seconds: int = 60
    clear_on_release: bool = True  # Always clear context between requests


class ObservabilityConfig(BaseModel):
    """Observability configuration."""

    metrics_enabled: bool = True
    access_logs_enabled: bool = True
    access_logs_path: str = "data/access_logs.duckdb"


class TomlSettings(BaseModel):
    """Settings loaded from TOML file."""

    server: ServerConfig = Field(default_factory=ServerConfig)
    claude: ClaudeConfig = Field(default_factory=ClaudeConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)


class Settings(BaseSettings):
    """Combined settings from TOML (non-secrets) and .env (secrets).

    Usage:
        from settings import get_settings
        settings = get_settings()
    """

    model_config = SettingsConfigDict(
        env_prefix="CLAUDE8CODE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Secrets from .env
    auth_key: str | None = None

    # Non-secret settings from TOML
    server: ServerConfig = Field(default_factory=ServerConfig)
    claude: ClaudeConfig = Field(default_factory=ClaudeConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)

    # Computed properties for backwards compatibility
    @property
    def host(self) -> str:
        return self.server.host

    @property
    def port(self) -> int:
        return self.server.port

    @property
    def debug(self) -> bool:
        return self.server.debug

    @property
    def default_model(self) -> str:
        return self.claude.default_model

    @property
    def max_turns(self) -> int:
        return self.claude.max_turns

    @property
    def permission_mode(self) -> str:
        return self.claude.permission_mode

    @property
    def cwd(self) -> str | None:
        return self.claude.cwd

    @property
    def system_prompt_mode(self) -> str:
        return self.claude.system_prompt.mode.value

    @property
    def custom_system_prompt(self) -> str | None:
        return self.claude.system_prompt.custom_prompt

    @property
    def sdk_message_mode(self) -> SDKMessageMode:
        return self.claude.sdk_message_mode

    def get_allowed_tools_list(self) -> list[str] | None:
        """Get list of allowed tools, or None for all tools."""
        if not self.claude.tools.allowed:
            return None
        return self.claude.tools.allowed

    def get_setting_sources_list(self) -> list[str]:
        """Get list of setting sources."""
        return self.claude.setting_sources

    def get_hooks_config(self) -> HooksConfig:
        """Get hooks configuration."""
        return self.claude.hooks

    def get_cors_origins_list(self) -> list[str]:
        """Get CORS origins."""
        return self.security.cors_origins


def load_toml_settings() -> dict[str, Any]:
    """Load settings from TOML file.

    Returns:
        Dictionary of settings from TOML file, or empty dict if file doesn't exist.
    """
    if not SETTINGS_TOML_PATH.exists():
        return {}

    with open(SETTINGS_TOML_PATH, "rb") as f:
        result: dict[str, Any] = tomllib.load(f)
        return result


def get_settings() -> Settings:
    """Load and return the combined settings.

    Loads non-secrets from settings/settings.toml and secrets from .env.

    Returns:
        Settings object with all configuration.
    """
    toml_data = load_toml_settings()

    # Parse TOML sections into Pydantic models
    toml_settings = TomlSettings(**toml_data)

    # Create Settings with TOML values as defaults, .env overrides for secrets
    return Settings(
        server=toml_settings.server,
        claude=toml_settings.claude,
        security=toml_settings.security,
        session=toml_settings.session,
        observability=toml_settings.observability,
    )


# Module-level singleton for convenience
_settings: Settings | None = None


def settings() -> Settings:
    """Get cached settings singleton.

    Returns:
        Settings object with all configuration.
    """
    global _settings
    if _settings is None:
        _settings = get_settings()
    return _settings


def reload_settings() -> Settings:
    """Reload settings from files.

    Returns:
        Fresh Settings object.
    """
    global _settings
    _settings = get_settings()
    return _settings
