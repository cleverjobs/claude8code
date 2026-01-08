"""Main entry point for claude8code server."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import uvicorn

from src.core import settings

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the claude8code server."""
    parser = argparse.ArgumentParser(
        description="claude8code - Anthropic-compatible API powered by Claude Agent SDK",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  claude8code                          # Start with defaults (0.0.0.0:8787)
  claude8code --port 8080              # Custom port
  claude8code --host 127.0.0.1         # Localhost only
  claude8code --debug                  # Enable debug logging

Environment variables:
  CLAUDE8CODE_HOST              Server host (default: 0.0.0.0)
  CLAUDE8CODE_PORT              Server port (default: 8787)
  CLAUDE8CODE_DEBUG             Enable debug mode (default: false)
  CLAUDE8CODE_DEFAULT_MODEL     Default model (default: claude-opus-4-5-20251101)
  CLAUDE8CODE_MAX_TURNS         Max agent turns (default: 10)
  CLAUDE8CODE_PERMISSION_MODE   Permission mode (default: acceptEdits)
  CLAUDE8CODE_CWD               Working directory for Claude Code
  CLAUDE8CODE_SYSTEM_PROMPT_MODE  "claude_code" or "custom" (default: claude_code)
  CLAUDE8CODE_CUSTOM_SYSTEM_PROMPT  Custom system prompt text
  CLAUDE8CODE_ALLOWED_TOOLS     Comma-separated list of allowed tools
  CLAUDE8CODE_SETTING_SOURCES   Comma-separated: user,project,local
  CLAUDE8CODE_CORS_ORIGINS      CORS origins (default: *)

n8n Integration:
  1. Start: claude8code --port 8787
  2. Set env: ANTHROPIC_BASE_URL=http://localhost:8787
  3. Start n8n: n8n start
  4. Use Anthropic Chat Model node with any API key
        """,
    )

    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help=f"Host to bind to (default: {settings.host})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Port to bind to (default: {settings.port})",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (development only)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes (default: 1)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="claude8code 0.1.0",
    )

    args = parser.parse_args()

    # Override settings from CLI args
    host = args.host or settings.host
    port = args.port or settings.port
    debug = args.debug or settings.debug

    # Validate cwd configuration
    if settings.cwd:
        cwd_path = Path(settings.cwd)
        if not cwd_path.is_absolute():
            cwd_path = cwd_path.resolve()
        if not cwd_path.exists():
            logging.basicConfig(level=logging.WARNING)
            logger.warning(f"Configured cwd does not exist: {cwd_path}")

    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║                        claude8code                            ║
║     Anthropic-compatible API powered by Claude Agent SDK      ║
╠═══════════════════════════════════════════════════════════════╣
║  Endpoint: http://{host}:{port}/v1/messages{" " * (26 - len(str(port)))}║
║  Docs:     http://{host}:{port}/docs{" " * (33 - len(str(port)))}║
╚═══════════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(
        "src.api.app:app",
        host=host,
        port=port,
        reload=args.reload,
        workers=args.workers if not args.reload else 1,
        log_level="debug" if debug else "info",
    )


if __name__ == "__main__":
    main()
