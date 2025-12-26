"""SDK Hooks for claude8code.

Provides configurable hooks for:
- Audit logging: Log all tool usage to access logs
- Permission control: Block dangerous operations
- Rate limiting: Basic rate limiting per session

These hooks integrate with the Claude Agent SDK's hook system
and can be enabled/disabled via settings.
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from claude_agent_sdk import HookMatcher

if TYPE_CHECKING:
    from claude_agent_sdk.types import HookContext, HookInput, HookJSONOutput

logger = logging.getLogger(__name__)


@dataclass
class RateLimitState:
    """Track rate limit state per session."""

    requests: list[float] = field(default_factory=list)

    def is_rate_limited(self, requests_per_minute: int) -> bool:
        """Check if rate limit is exceeded."""
        now = time.time()
        # Remove requests older than 1 minute
        self.requests = [t for t in self.requests if now - t < 60]
        return len(self.requests) >= requests_per_minute

    def record_request(self) -> None:
        """Record a new request."""
        self.requests.append(time.time())


# Global rate limit state per session
_rate_limit_state: dict[str, RateLimitState] = defaultdict(RateLimitState)


# Default dangerous patterns to block
DEFAULT_DENY_PATTERNS = [
    r"rm\s+-rf\s+/\s*$",  # rm -rf /
    r"rm\s+-rf\s+~",  # rm -rf ~
    r"rm\s+-rf\s+/home",  # rm -rf /home
    r"rm\s+-rf\s+/Users",  # rm -rf /Users
    r"rm\s+-rf\s+\*",  # rm -rf *
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;",  # Fork bomb
    r"dd\s+if=.*of=/dev/",  # dd to devices
    r"mkfs\.",  # Format filesystems
    r">\s*/dev/sd",  # Write to block devices
    r"chmod\s+-R\s+777\s+/",  # Chmod 777 root
    r"wget.*\|\s*sh",  # Download and execute
    r"curl.*\|\s*sh",  # Download and execute
    r"curl.*\|\s*bash",  # Download and execute
]


async def audit_hook(
    input_data: HookInput,
    tool_use_id: str | None,
    context: HookContext,  # noqa: ARG001
) -> HookJSONOutput:
    """Log all tool usage for audit purposes.

    This hook logs tool invocations to the application logger.
    It can be extended to write to DuckDB access logs.

    Args:
        input_data: Hook input data containing tool info
        tool_use_id: The tool use ID for correlation
        context: Hook context

    Returns:
        Empty dict (no modifications, just logging)
    """
    tool_name = input_data.get("tool_name", "unknown")
    tool_input = cast(dict[str, Any], input_data.get("tool_input", {}))
    session_id = input_data.get("session_id", "unknown")
    hook_event = input_data.get("hook_event_name", "unknown")

    # Extract relevant info based on tool type
    audit_info = {
        "event": hook_event,
        "tool": tool_name,
        "session_id": session_id,
        "tool_use_id": tool_use_id,
    }

    # Add tool-specific details
    if tool_name == "Bash":
        audit_info["command"] = tool_input.get("command", "")[:200]
    elif tool_name in ("Write", "Edit", "Read"):
        audit_info["file_path"] = tool_input.get("file_path", "")
    elif tool_name == "WebFetch":
        audit_info["url"] = tool_input.get("url", "")

    logger.info("[AUDIT] Tool usage: %s", audit_info)

    return {}


async def permission_hook(
    input_data: HookInput,
    tool_use_id: str | None,  # noqa: ARG001
    context: HookContext,  # noqa: ARG001
    deny_patterns: list[str] | None = None,
) -> HookJSONOutput:
    """Block dangerous operations based on patterns.

    This hook checks tool inputs against dangerous patterns
    and blocks operations that match.

    Args:
        input_data: Hook input data containing tool info
        tool_use_id: The tool use ID for correlation
        context: Hook context
        deny_patterns: List of regex patterns to deny

    Returns:
        Permission decision (allow/deny)
    """
    tool_name = input_data.get("tool_name", "")
    tool_input = cast(dict[str, Any], input_data.get("tool_input", {}))

    patterns = deny_patterns or DEFAULT_DENY_PATTERNS

    # Check Bash commands
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        for pattern in patterns:
            if re.search(pattern, command, re.IGNORECASE):
                logger.warning(
                    "[PERMISSION] Blocked dangerous command: %s (pattern: %s)",
                    command[:100],
                    pattern,
                )
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": (
                            f"Blocked by security policy: matches pattern '{pattern}'"
                        ),
                    }
                }

    # Check file operations on sensitive paths
    if tool_name in ("Write", "Edit"):
        file_path = tool_input.get("file_path", "")
        sensitive_paths = [
            "/etc/passwd",
            "/etc/shadow",
            "/etc/sudoers",
            "~/.ssh/",
            "~/.aws/credentials",
            ".env",
        ]
        for sensitive in sensitive_paths:
            if sensitive in file_path:
                logger.warning(
                    "[PERMISSION] Blocked write to sensitive path: %s",
                    file_path,
                )
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": f"Cannot modify sensitive file: {sensitive}",
                    }
                }

    return {}


async def rate_limit_hook(
    input_data: HookInput,
    tool_use_id: str | None,  # noqa: ARG001
    context: HookContext,  # noqa: ARG001
    requests_per_minute: int = 60,
) -> HookJSONOutput:
    """Basic rate limiting per session.

    Args:
        input_data: Hook input data containing session info
        tool_use_id: The tool use ID for correlation
        context: Hook context
        requests_per_minute: Maximum requests per minute per session

    Returns:
        Permission decision if rate limited
    """
    session_id = input_data.get("session_id", "default")

    state = _rate_limit_state[session_id]

    if state.is_rate_limited(requests_per_minute):
        logger.warning(
            "[RATE_LIMIT] Session %s exceeded rate limit (%d/min)",
            session_id,
            requests_per_minute,
        )
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"Rate limit exceeded: {requests_per_minute} requests per minute"
                ),
            }
        }

    state.record_request()
    return {}


def create_audit_hook() -> HookMatcher:
    """Create a HookMatcher for audit logging.

    Returns:
        HookMatcher configured for all tools
    """
    return HookMatcher(hooks=[audit_hook])


def create_permission_hook(deny_patterns: list[str] | None = None) -> HookMatcher:
    """Create a HookMatcher for permission control.

    Args:
        deny_patterns: Custom patterns to deny

    Returns:
        HookMatcher configured for dangerous operations
    """
    patterns = deny_patterns or DEFAULT_DENY_PATTERNS

    async def hook_with_patterns(
        input_data: HookInput,
        tool_use_id: str | None,
        context: HookContext,
    ) -> HookJSONOutput:
        return await permission_hook(input_data, tool_use_id, context, patterns)

    return HookMatcher(matcher="Bash|Write|Edit", hooks=[hook_with_patterns])


def create_rate_limit_hook(requests_per_minute: int = 60) -> HookMatcher:
    """Create a HookMatcher for rate limiting.

    Args:
        requests_per_minute: Maximum requests per minute

    Returns:
        HookMatcher configured for rate limiting
    """

    async def hook_with_limit(
        input_data: HookInput,
        tool_use_id: str | None,
        context: HookContext,
    ) -> HookJSONOutput:
        return await rate_limit_hook(input_data, tool_use_id, context, requests_per_minute)

    return HookMatcher(hooks=[hook_with_limit])


def get_configured_hooks(
    audit_enabled: bool = True,
    permission_enabled: bool = True,
    rate_limit_enabled: bool = False,
    rate_limit_requests_per_minute: int = 60,
    deny_patterns: list[str] | None = None,
) -> dict[str, list[HookMatcher]] | None:
    """Get configured hooks based on settings.

    Args:
        audit_enabled: Enable audit logging hook
        permission_enabled: Enable permission control hook
        rate_limit_enabled: Enable rate limiting hook
        rate_limit_requests_per_minute: Rate limit threshold
        deny_patterns: Custom patterns to deny

    Returns:
        Dict of hooks for ClaudeAgentOptions, or None if no hooks enabled
    """
    pre_tool_hooks: list[HookMatcher] = []
    post_tool_hooks: list[HookMatcher] = []

    if permission_enabled:
        pre_tool_hooks.append(create_permission_hook(deny_patterns))

    if rate_limit_enabled:
        pre_tool_hooks.append(create_rate_limit_hook(rate_limit_requests_per_minute))

    if audit_enabled:
        # Audit on both pre and post for complete picture
        pre_tool_hooks.append(create_audit_hook())
        post_tool_hooks.append(create_audit_hook())

    if not pre_tool_hooks and not post_tool_hooks:
        return None

    hooks: dict[str, list[HookMatcher]] = {}
    if pre_tool_hooks:
        hooks["PreToolUse"] = pre_tool_hooks
    if post_tool_hooks:
        hooks["PostToolUse"] = post_tool_hooks

    return hooks


def clear_rate_limit_state(session_id: str | None = None) -> None:
    """Clear rate limit state.

    Args:
        session_id: Session to clear, or None for all sessions
    """
    if session_id:
        _rate_limit_state.pop(session_id, None)
    else:
        _rate_limit_state.clear()
