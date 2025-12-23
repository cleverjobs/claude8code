"""API route handlers for claude8code.

This module contains all the API endpoints mounted on the router.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Depends
from sse_starlette.sse import EventSourceResponse

from ..core import settings, get_access_log_writer
from ..models import (
    MessagesRequest,
    MessagesResponse,
    ErrorResponse,
    ErrorDetail,
    ErrorType,
    ModelInfo,
    ModelsListResponse,
)
from ..sdk import (
    process_request,
    process_request_streaming,
    session_manager,
    build_claude_options,
    get_pool,
)
from .security import verify_api_key


logger = logging.getLogger(__name__)


# Model metadata for API response
MODEL_METADATA = {
    # Claude 4.5 models (latest)
    "claude-opus-4-5-20251101": {
        "display_name": "Claude Opus 4.5",
        "created_at": "2025-11-01T00:00:00Z",
    },
    "claude-sonnet-4-5-20250514": {
        "display_name": "Claude Sonnet 4.5",
        "created_at": "2025-05-14T00:00:00Z",
    },
    "claude-haiku-4-5-20251001": {
        "display_name": "Claude Haiku 4.5",
        "created_at": "2025-10-01T00:00:00Z",
    },
    # Claude 4 models
    "claude-sonnet-4-20250514": {
        "display_name": "Claude Sonnet 4",
        "created_at": "2025-05-14T00:00:00Z",
    },
    "claude-opus-4-20250514": {
        "display_name": "Claude Opus 4",
        "created_at": "2025-05-14T00:00:00Z",
    },
    # Aliases for compatibility
    "claude-3-5-sonnet-latest": {
        "display_name": "Claude 3.5 Sonnet (Latest)",
        "created_at": "2024-10-22T00:00:00Z",
    },
    "claude-3-opus-latest": {
        "display_name": "Claude 3 Opus (Latest)",
        "created_at": "2024-02-29T00:00:00Z",
    },
}


# Create API router
api_router = APIRouter()


@api_router.get("/health")
async def router_health():
    """Health check endpoint (available at both /health and /sdk/health)."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat(), "mode": "sdk"}


@api_router.get("/v1/models", dependencies=[Depends(verify_api_key)])
async def list_models(
    anthropic_version: Optional[str] = Header(None, alias="anthropic-version"),
    anthropic_beta: Optional[str] = Header(None, alias="anthropic-beta"),
):
    """List available models (Anthropic format).

    Supports anthropic-version and anthropic-beta headers for compatibility.
    """
    # Log version header if provided
    if anthropic_version:
        logger.debug(f"API version requested: {anthropic_version}")
    if anthropic_beta:
        logger.debug(f"Beta features requested: {anthropic_beta}")

    models = [
        ModelInfo(
            id=model_id,
            display_name=metadata["display_name"],
            created_at=metadata["created_at"],
        )
        for model_id, metadata in MODEL_METADATA.items()
    ]

    # Return with pagination fields
    return ModelsListResponse(
        data=models,
        first_id=models[0].id if models else None,
        last_id=models[-1].id if models else None,
        has_more=False,
    )


@api_router.post("/v1/messages", dependencies=[Depends(verify_api_key)])
async def create_message(
    request: MessagesRequest,
    anthropic_version: Optional[str] = Header(None, alias="anthropic-version"),
    anthropic_beta: Optional[str] = Header(None, alias="anthropic-beta"),
):
    """Create a message (Anthropic Messages API compatible).

    This endpoint accepts requests in Anthropic's format and routes them
    through Claude Agent SDK, returning responses in Anthropic's format.

    Supports anthropic-version and anthropic-beta headers for compatibility.

    If CLAUDE8CODE_AUTH_KEY is set, requests must include a valid API key
    in x-api-key header or Authorization: Bearer header.
    """
    try:
        # Log version headers if provided
        if anthropic_version:
            logger.debug(f"API version: {anthropic_version}")
        if anthropic_beta:
            logger.debug(f"Beta features: {anthropic_beta}")

        logger.debug(f"Received request: model={request.model}, stream={request.stream}")

        if request.stream:
            return await handle_streaming_request(request)
        else:
            response = await process_request(request)
            return response

    except ValueError as e:
        # Invalid request parameters
        logger.warning(f"Invalid request: {e}")
        raise HTTPException(
            status_code=ErrorType.INVALID_REQUEST.status_code,
            detail=ErrorResponse(
                error=ErrorDetail(
                    type=ErrorType.INVALID_REQUEST.value,
                    message=str(e),
                )
            ).model_dump(),
        )
    except PermissionError as e:
        # Permission denied
        logger.warning(f"Permission denied: {e}")
        raise HTTPException(
            status_code=ErrorType.PERMISSION.status_code,
            detail=ErrorResponse(
                error=ErrorDetail(
                    type=ErrorType.PERMISSION.value,
                    message=str(e),
                )
            ).model_dump(),
        )
    except Exception as e:
        # Generic server error
        logger.exception("Error processing request")
        raise HTTPException(
            status_code=ErrorType.API.status_code,
            detail=ErrorResponse(
                error=ErrorDetail(
                    type=ErrorType.API.value,
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

@api_router.post("/v1/sessions", dependencies=[Depends(verify_api_key)])
async def create_session():
    """Create a new conversation session.

    Sessions enable multi-turn conversations with context persistence.
    """
    # Create a minimal request for options
    dummy_request = MessagesRequest(
        model=settings.default_model,
        messages=[],
        max_tokens=1,
    )
    options = build_claude_options(dummy_request)

    session_id, _ = await session_manager.get_or_create_session(options=options)
    return {"session_id": session_id}


@api_router.delete("/v1/sessions/{session_id}", dependencies=[Depends(verify_api_key)])
async def delete_session(session_id: str):
    """Delete a conversation session."""
    closed = await session_manager.close_session(session_id)
    if not closed:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "closed", "session_id": session_id}


@api_router.get("/v1/config", dependencies=[Depends(verify_api_key)])
async def get_config():
    """Get current server configuration (non-sensitive)."""
    return {
        "default_model": settings.default_model,
        "max_turns": settings.max_turns,
        "permission_mode": settings.permission_mode,
        "system_prompt_mode": settings.system_prompt_mode,
        "sdk_message_mode": settings.sdk_message_mode.value,
        "cwd": settings.cwd,
        "allowed_tools": settings.get_allowed_tools_list(),
        "setting_sources": settings.get_setting_sources_list(),
    }


@api_router.get("/v1/pool/stats", dependencies=[Depends(verify_api_key)])
async def get_pool_stats():
    """Get session pool statistics.

    Returns information about the session pool including:
    - Configuration (max sessions, TTL)
    - Current usage (total, active, available sessions)
    - Individual session details
    """
    pool = get_pool()
    return await pool.get_stats()


@api_router.get("/v1/logs/stats", dependencies=[Depends(verify_api_key)])
async def get_access_log_stats():
    """Get access log statistics.

    Returns information about the DuckDB access logs including:
    - Total requests logged
    - Date range of logs
    - Top models by usage
    - Queue size (pending writes)

    Returns {"available": false} if DuckDB is not installed.
    """
    writer = get_access_log_writer()
    if not writer:
        return {"available": False, "reason": "DuckDB not installed or logging disabled"}
    return writer.get_stats()
