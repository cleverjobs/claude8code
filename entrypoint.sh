#!/bin/bash
# claude8code entrypoint script
# Handles OAuth credential setup from environment variable

set -e

CLAUDE_CONFIG_DIR="${HOME}/.claude"

# Setup OAuth credentials from environment variable if provided
if [ -n "${CLAUDE_CODE_OAUTH_TOKEN}" ]; then
    echo "Setting up Claude Code OAuth credentials..."

    # Create config directory if it doesn't exist
    mkdir -p "${CLAUDE_CONFIG_DIR}"

    # Write credentials.json with OAuth token
    cat > "${CLAUDE_CONFIG_DIR}/credentials.json" << EOF
{
  "claudeAiOauth": {
    "accessToken": "${CLAUDE_CODE_OAUTH_TOKEN}",
    "refreshToken": "${CLAUDE_CODE_REFRESH_TOKEN:-}",
    "expiresAt": "${CLAUDE_CODE_EXPIRES_AT:-2099-12-31T23:59:59.000Z}",
    "scopes": ["user:inference", "user:profile"]
  }
}
EOF

    echo "Claude Code OAuth credentials configured"
else
    # Check if credentials already exist (mounted volume)
    if [ -f "${CLAUDE_CONFIG_DIR}/credentials.json" ]; then
        echo "Using existing Claude Code credentials from mounted volume"
    else
        echo "WARNING: No Claude Code credentials found!"
        echo "Either:"
        echo "  1. Set CLAUDE_CODE_OAUTH_TOKEN environment variable"
        echo "  2. Mount ~/.claude directory to ${CLAUDE_CONFIG_DIR}"
        echo ""
        echo "To get your OAuth token, run 'claude /login' locally and copy from ~/.claude/credentials.json"
    fi
fi

# Generate a random auth key if not provided (optional)
if [ "${CLAUDE8CODE_GENERATE_AUTH_KEY:-false}" = "true" ] && [ -z "${CLAUDE8CODE_AUTH_KEY}" ]; then
    export CLAUDE8CODE_AUTH_KEY=$(openssl rand -hex 32)
    echo "Generated random API key: ${CLAUDE8CODE_AUTH_KEY}"
    echo "Set this as x-api-key header in your requests"
fi

# Print startup info
echo ""
echo "============================================"
echo "  claude8code - Anthropic-compatible API"
echo "============================================"
echo "  Host: ${CLAUDE8CODE_HOST:-0.0.0.0}"
echo "  Port: ${CLAUDE8CODE_PORT:-8787}"
echo "  Auth: ${CLAUDE8CODE_AUTH_KEY:+ENABLED}${CLAUDE8CODE_AUTH_KEY:-DISABLED}"
echo "============================================"
echo ""

# Execute the main command
exec "$@"
