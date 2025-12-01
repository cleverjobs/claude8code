"""FastAPI server exposing Anthropic-compatible Messages API.

This server accepts requests in Anthropic's Messages API format and
routes them through Claude Agent SDK, enabling use of Claude Code
features (subagents, skills, MCP tools) via standard API clients.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse

from .config import settings
from .security import verify_api_key
from .models import (
    MessagesRequest,
    MessagesResponse,
    ErrorResponse,
    ErrorDetail,
    ModelsListResponse,
    ModelInfo,
)
from .bridge import (
    process_request,
    process_request_streaming,
    session_manager,
)


# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("claude8code")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info(f"claude8code starting on {settings.host}:{settings.port}")
    logger.info(f"   Default model: {settings.default_model}")
    logger.info(f"   System prompt mode: {settings.system_prompt_mode}")
    logger.info(f"   Permission mode: {settings.permission_mode}")
    if settings.auth_key:
        logger.info("   Authentication: ENABLED (API key required)")
    else:
        logger.info("   Authentication: DISABLED (open access)")
    yield
    # Cleanup
    logger.info("Shutting down, closing sessions...")
    await session_manager.close_all()
    logger.info("👋 claude8code stopped")


# Create FastAPI app
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


# ============================================================================
# Health & Info Endpoints
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
        },
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# ============================================================================
# Anthropic-Compatible Endpoints
# ============================================================================

@app.get("/v1/models", dependencies=[Depends(verify_api_key)])
async def list_models():
    """List available models (Anthropic format)."""
    models = [
        # Claude 4.5 models (latest)
        ModelInfo(id="claude-opus-4-5-20251101"),
        ModelInfo(id="claude-sonnet-4-5-20250514"),
        ModelInfo(id="claude-haiku-4-5-20251001"),
        # Claude 4 models
        ModelInfo(id="claude-sonnet-4-20250514"),
        ModelInfo(id="claude-opus-4-20250514"),
        # Aliases for compatibility
        ModelInfo(id="claude-3-5-sonnet-latest"),
        ModelInfo(id="claude-3-opus-latest"),
    ]
    return ModelsListResponse(data=models)


@app.post("/v1/messages", dependencies=[Depends(verify_api_key)])
async def create_message(request: MessagesRequest):
    """Create a message (Anthropic Messages API compatible).

    This endpoint accepts requests in Anthropic's format and routes them
    through Claude Agent SDK, returning responses in Anthropic's format.

    If CLAUDE8CODE_AUTH_KEY is set, requests must include a valid API key
    in x-api-key header or Authorization: Bearer header.
    """
    try:
        logger.debug(f"Received request: model={request.model}, stream={request.stream}")
        
        if request.stream:
            return await handle_streaming_request(request)
        else:
            response = await process_request(request)
            return response
            
    except Exception as e:
        logger.exception("Error processing request")
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error=ErrorDetail(
                    type="server_error",
                    message=str(e),
                )
            ).model_dump(),
        )


async def handle_streaming_request(request: MessagesRequest):
    """Handle a streaming request, returning SSE events."""
    
    async def event_generator():
        try:
            async for event in process_request_streaming(request):
                event_data = event.model_dump()
                yield {
                    "event": event.type,
                    "data": json.dumps(event_data),
                }
        except Exception as e:
            logger.exception("Error in streaming response")
            error_event = {
                "type": "error",
                "error": {"type": "server_error", "message": str(e)},
            }
            yield {
                "event": "error",
                "data": json.dumps(error_event),
            }
    
    return EventSourceResponse(
        event_generator(),
        media_type="text/event-stream",
    )


# ============================================================================
# Extended API (claude8code-specific)
# ============================================================================

@app.post("/v1/sessions", dependencies=[Depends(verify_api_key)])
async def create_session():
    """Create a new conversation session.
    
    Sessions enable multi-turn conversations with context persistence.
    """
    from .bridge import build_claude_options
    
    # Create a minimal request for options
    dummy_request = MessagesRequest(
        model=settings.default_model,
        messages=[],
        max_tokens=1,
    )
    options = build_claude_options(dummy_request)
    
    session_id, _ = await session_manager.get_or_create_session(options=options)
    return {"session_id": session_id}


@app.delete("/v1/sessions/{session_id}", dependencies=[Depends(verify_api_key)])
async def delete_session(session_id: str):
    """Delete a conversation session."""
    closed = await session_manager.close_session(session_id)
    if not closed:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "closed", "session_id": session_id}


@app.get("/v1/config", dependencies=[Depends(verify_api_key)])
async def get_config():
    """Get current server configuration (non-sensitive)."""
    return {
        "default_model": settings.default_model,
        "max_turns": settings.max_turns,
        "permission_mode": settings.permission_mode,
        "system_prompt_mode": settings.system_prompt_mode,
        "cwd": settings.cwd,
        "allowed_tools": settings.get_allowed_tools_list(),
        "setting_sources": settings.get_setting_sources_list(),
    }


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions in Anthropic error format."""
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": "error",
            "error": {
                "type": "api_error",
                "message": str(exc.detail),
            },
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={
            "type": "error",
            "error": {
                "type": "server_error",
                "message": "Internal server error",
            },
        },
    )
