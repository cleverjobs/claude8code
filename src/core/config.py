"""Configuration settings for claude8code server.

This module provides backwards compatibility with the old settings API
while delegating to the new settings/ module.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path for settings import
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Import from new settings module
from settings import (  # noqa: E402
    ClaudeConfig,
    ObservabilityConfig,
    SDKMessageMode,
    SecurityConfig,
    ServerConfig,
    SessionConfig,
    Settings,
    SystemPromptMode,
    get_settings,
    reload_settings,
)
from settings import settings as get_settings_singleton  # noqa: E402

# Module-level settings singleton for backwards compatibility
settings = get_settings_singleton()

__all__ = [
    "Settings",
    "settings",
    "get_settings",
    "reload_settings",
    "SDKMessageMode",
    "SystemPromptMode",
    "ServerConfig",
    "ClaudeConfig",
    "SecurityConfig",
    "SessionConfig",
    "ObservabilityConfig",
]
