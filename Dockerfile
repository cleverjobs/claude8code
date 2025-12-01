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
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install Python dependencies into a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip wheel \
    && pip install --no-cache-dir -e .

# ==============================================================================
# Stage 2: Runtime image
# ==============================================================================
FROM python:3.11-slim

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

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set up working directory
WORKDIR /app

# Copy application source
COPY --chown=claude8code:claude8code src/ ./src/
COPY --chown=claude8code:claude8code pyproject.toml README.md ./
COPY --chown=claude8code:claude8code entrypoint.sh ./

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Install the package (needed for entry point)
RUN pip install --no-cache-dir -e .

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
