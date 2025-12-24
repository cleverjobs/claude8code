"""FastAPI application for claude8code.

This module creates and configures the FastAPI application with:
- CORS middleware
- Request context middleware
- Error handlers
- Route mounting
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from ..core import (
    get_metrics,
    get_metrics_content_type,
    init_access_log,
    init_app_info,
    settings,
    shutdown_access_log,
)
from ..models import ErrorType
from ..sdk import init_pool, session_manager, shutdown_pool
from .middleware import RequestContextMiddleware
from .routes import api_router

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("claude8code")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Initialize metrics
    init_app_info(version="0.1.0")

    # Initialize session pool
    pool = await init_pool()

    # Initialize access log (DuckDB)
    access_log = None
    if settings.observability.access_logs_enabled:
        access_log = await init_access_log()
        if access_log:
            logger.info(f"   Access logs: {settings.observability.access_logs_path}")
        else:
            logger.info("   Access logs: DISABLED (DuckDB not installed)")

    logger.info(f"claude8code starting on {settings.host}:{settings.port}")
    logger.info(f"   Default model: {settings.default_model}")
    logger.info(f"   System prompt mode: {settings.system_prompt_mode}")
    logger.info(f"   Permission mode: {settings.permission_mode}")
    logger.info(f"   SDK message mode: {settings.sdk_message_mode.value}")
    logger.info(f"   Session pool: max={pool._max_sessions}, ttl={pool._ttl_seconds}s")
    logger.info("   Metrics endpoint: /metrics")
    if settings.auth_key:
        logger.info("   Authentication: ENABLED (API key required)")
    else:
        logger.info("   Authentication: DISABLED (open access)")
    yield
    # Cleanup
    logger.info("Shutting down, closing sessions...")
    await shutdown_access_log()
    await shutdown_pool()
    await session_manager.close_all()
    logger.info("claude8code stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="claude8code",
        description="Anthropic-compatible API server powered by Claude Agent SDK",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add request context middleware
    app.add_middleware(RequestContextMiddleware)

    # ============================================================================
    # Health & Info Endpoints (at root level)
    # ============================================================================

    @app.get("/")
    async def root():
        """Root endpoint with server info."""
        return {
            "name": "claude8code",
            "version": "0.1.0",
            "status": "running",
            "description": "Anthropic-compatible API powered by Claude Agent SDK",
            "endpoints": {
                "messages": "/v1/messages",
                "models": "/v1/models",
                "health": "/health",
                "metrics": "/metrics",
            },
            "sdk_endpoints": {
                "messages": "/sdk/v1/messages",
                "models": "/sdk/v1/models",
                "health": "/sdk/health",
            },
            "usage": {
                "anthropic_base_url": f"http://localhost:{settings.port}",
                "sdk_base_url": f"http://localhost:{settings.port}/sdk",
            },
        }

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

    @app.get("/metrics")
    async def metrics():
        """Prometheus metrics endpoint."""
        return Response(
            content=get_metrics(),
            media_type=get_metrics_content_type(),
        )

    # ============================================================================
    # Mount API Router at both root and /sdk/ prefix
    # ============================================================================

    # Mount at root (backward compatibility)
    app.include_router(api_router)

    # Mount at /sdk/ prefix (Claude Agent SDK style)
    app.include_router(api_router, prefix="/sdk")

    # ============================================================================
    # Error Handlers
    # ============================================================================

    def get_error_type_for_status(status_code: int) -> str:
        """Map HTTP status code to Anthropic error type."""
        status_to_error = {
            400: ErrorType.INVALID_REQUEST.value,
            401: ErrorType.AUTHENTICATION.value,
            403: ErrorType.PERMISSION.value,
            404: ErrorType.NOT_FOUND.value,
            429: ErrorType.RATE_LIMIT.value,
            500: ErrorType.API.value,
            529: ErrorType.OVERLOADED.value,
        }
        return status_to_error.get(status_code, ErrorType.API.value)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle HTTP exceptions in Anthropic error format."""
        # If detail is already in our format, return it
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)

        # Map status code to appropriate error type
        error_type = get_error_type_for_status(exc.status_code)

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "type": "error",
                "error": {
                    "type": error_type,
                    "message": str(exc.detail),
                },
            },
        )

    @app.exception_handler(ValueError)
    async def validation_exception_handler(request: Request, exc: ValueError):
        """Handle validation errors as invalid_request_error."""
        logger.warning(f"Validation error: {exc}")
        return JSONResponse(
            status_code=ErrorType.INVALID_REQUEST.status_code,
            content={
                "type": "error",
                "error": {
                    "type": ErrorType.INVALID_REQUEST.value,
                    "message": str(exc),
                },
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle unexpected exceptions as api_error."""
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=ErrorType.API.status_code,
            content={
                "type": "error",
                "error": {
                    "type": ErrorType.API.value,
                    "message": "Internal server error",
                },
            },
        )

    return app


# Create the application instance
app = create_app()
