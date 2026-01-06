# claude8code Dockerfile
# Anthropic-compatible API server powered by Claude Agent SDK
#
# Build: docker build -t claude8code .
# Run:   docker run -p 8787:8787 -e CLAUDE_CODE_OAUTH_TOKEN=... claude8code
#
# Or with mounted credentials:
# Run:   docker run -p 8787:8787 -v ~/.claude:/home/claude8code/.claude claude8code

# ==============================================================================
# Stage 1: Build dependencies
# ==============================================================================
FROM python:3.13-slim AS builder

WORKDIR /build

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy project files (including lock file for reproducible builds)
COPY pyproject.toml uv.lock README.md main.py ./
COPY src/ ./src/
COPY settings/ ./settings/

# Install Python dependencies using UV
RUN uv sync --frozen --no-dev

# ==============================================================================
# Stage 2: Runtime image
# ==============================================================================
FROM python:3.13-slim

# Install Node.js (required for Claude Code CLI) and runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    openssl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* \
    && npm cache clean --force

# Create non-root user
RUN useradd -m -s /bin/bash -u 1000 claude8code

# Set up working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /build/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application source
COPY --chown=claude8code:claude8code src/ ./src/
COPY --chown=claude8code:claude8code settings/ ./settings/
COPY --chown=claude8code:claude8code pyproject.toml README.md main.py ./
COPY --chown=claude8code:claude8code entrypoint.sh ./

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Switch to non-root user
USER claude8code

# Set environment
ENV HOME=/home/claude8code
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Create workspace directory for Claude file operations
RUN mkdir -p /home/claude8code/workspace /home/claude8code/.claude

# Default environment variables
ENV CLAUDE8CODE_HOST=0.0.0.0
ENV CLAUDE8CODE_PORT=8787
ENV CLAUDE8CODE_CWD=/home/claude8code/workspace

# Expose port
EXPOSE 8787

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8787/health || exit 1

# Use entrypoint script for credential setup
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["claude8code", "--host", "0.0.0.0", "--port", "8787"]
