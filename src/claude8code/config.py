"""Configuration settings for claude8code server."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server configuration loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_prefix="CLAUDE8CODE_",
        env_file=".env",
        env_file_encoding="utf-8",
    )
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8787
    debug: bool = False

    # Optional API key authentication (empty = disabled)
    # Set CLAUDE8CODE_AUTH_KEY to require authentication
    auth_key: str | None = None
    
    # Claude Agent SDK settings
    default_model: str = "claude-sonnet-4-5-20250514"
    max_turns: int = 10
    permission_mode: str = "acceptEdits"  # auto-accept for API usage
    
    # Working directory for Claude Code operations
    cwd: str | None = None
    
    # System prompt configuration
    # "claude_code" = use Claude Code's preset, "custom" = use custom_system_prompt
    system_prompt_mode: str = "claude_code"
    custom_system_prompt: str | None = None
    
    # Tool configuration
    # Comma-separated list of allowed tools, empty = all tools
    allowed_tools: str = ""
    
    # Settings sources for Claude Agent SDK
    # Comma-separated: user, project, local (empty = none)
    setting_sources: str = "user,project"
    
    # Rate limiting (requests per minute, 0 = disabled)
    rate_limit_rpm: int = 0
    
    # CORS settings
    cors_origins: str = "*"
    
    def get_allowed_tools_list(self) -> list[str] | None:
        """Parse allowed_tools into a list."""
        if not self.allowed_tools:
            return None
        return [t.strip() for t in self.allowed_tools.split(",") if t.strip()]
    
    def get_setting_sources_list(self) -> list[str]:
        """Parse setting_sources into a list."""
        if not self.setting_sources:
            return []
        return [s.strip() for s in self.setting_sources.split(",") if s.strip()]
    
    def get_cors_origins_list(self) -> list[str]:
        """Parse CORS origins."""
        if self.cors_origins == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
