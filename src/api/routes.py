"""API route handlers for claude8code.

This module contains all the API endpoints mounted on the router.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sse_starlette.sse import EventSourceResponse

from ..core import get_access_log_writer, settings
from ..models import (
    BatchesListResponse,
    CountTokensRequest,
    CountTokensResponse,
    CreateBatchRequest,
    ErrorDetail,
    ErrorResponse,
    ErrorType,
    FileDeletedResponse,
    FilesListResponse,
    MessageBatchDeletedResponse,
    MessagesRequest,
    ModelInfo,
    ModelsListResponse,
)
from ..sdk import (
    build_claude_options,
    count_request_tokens,
    get_batch_processor,
    get_file_store,
    get_pool,
    process_request,
    process_request_streaming,
    session_manager,
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
    after_id: Optional[str] = Query(None, description="Return models after this ID"),
    before_id: Optional[str] = Query(None, description="Return models before this ID"),
    limit: int = Query(20, ge=1, le=1000, description="Maximum number of models to return"),
    anthropic_version: Optional[str] = Header(None, alias="anthropic-version"),
    anthropic_beta: Optional[str] = Header(None, alias="anthropic-beta"),
):
    """List available models (Anthropic format).

    Supports pagination via after_id, before_id, and limit parameters.
    Supports anthropic-version and anthropic-beta headers for compatibility.
    """
    # Log version header if provided
    if anthropic_version:
        logger.debug(f"API version requested: {anthropic_version}")
    if anthropic_beta:
        logger.debug(f"Beta features requested: {anthropic_beta}")

    # Get all models as a list for pagination
    all_model_ids = list(MODEL_METADATA.keys())

    # Apply after_id filter
    start_idx = 0
    if after_id and after_id in all_model_ids:
        start_idx = all_model_ids.index(after_id) + 1

    # Apply before_id filter
    end_idx = len(all_model_ids)
    if before_id and before_id in all_model_ids:
        end_idx = all_model_ids.index(before_id)

    # Get the slice of model IDs
    paginated_ids = all_model_ids[start_idx:end_idx][:limit]

    # Build model list
    models = [
        ModelInfo(
            id=model_id,
            display_name=MODEL_METADATA[model_id]["display_name"],
            created_at=MODEL_METADATA[model_id]["created_at"],
        )
        for model_id in paginated_ids
    ]

    # Determine if there are more results
    has_more = end_idx < len(all_model_ids) and len(paginated_ids) == limit

    # Return with pagination fields
    return ModelsListResponse(
        data=models,
        first_id=models[0].id if models else None,
        last_id=models[-1].id if models else None,
        has_more=has_more,
    )


# Alias resolution map (aliases -> canonical model ID)
MODEL_ALIASES = {
    "claude-opus-4-5": "claude-opus-4-5-20251101",
    "claude-sonnet-4-5": "claude-sonnet-4-5-20250514",
    "claude-haiku-4-5": "claude-haiku-4-5-20251001",
    "claude-sonnet-4": "claude-sonnet-4-20250514",
    "claude-sonnet-4-0": "claude-sonnet-4-20250514",
    "claude-opus-4": "claude-opus-4-20250514",
    "claude-opus-4-0": "claude-opus-4-20250514",
}


@api_router.get("/v1/models/{model_id}", dependencies=[Depends(verify_api_key)])
async def get_model(
    model_id: str,
    anthropic_version: Optional[str] = Header(None, alias="anthropic-version"),
    anthropic_beta: Optional[str] = Header(None, alias="anthropic-beta"),
):
    """Get information about a specific model.

    Supports alias resolution (e.g., claude-opus-4-5 -> claude-opus-4-5-20251101).
    Returns 404 if model not found.
    """
    # Log version headers if provided
    if anthropic_version:
        logger.debug(f"API version: {anthropic_version}")
    if anthropic_beta:
        logger.debug(f"Beta features: {anthropic_beta}")

    # Resolve alias if applicable
    resolved_id = MODEL_ALIASES.get(model_id, model_id)

    # Look up model metadata
    if resolved_id not in MODEL_METADATA:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error=ErrorDetail(
                    type=ErrorType.NOT_FOUND.value,
                    message=f"Model not found: {model_id}",
                )
            ).model_dump(),
        )

    metadata = MODEL_METADATA[resolved_id]
    return ModelInfo(
        id=resolved_id,
        display_name=metadata["display_name"],
        created_at=metadata["created_at"],
    )


@api_router.post("/v1/messages/count_tokens", dependencies=[Depends(verify_api_key)])
async def count_tokens(
    request: CountTokensRequest,
    anthropic_version: Optional[str] = Header(None, alias="anthropic-version"),
    anthropic_beta: Optional[str] = Header(None, alias="anthropic-beta"),
):
    """Count tokens in a message request without sending it.

    This endpoint counts the number of input tokens that would be used
    by a messages request, useful for cost estimation before sending.

    Uses tiktoken for estimation - results are approximate but accurate
    for planning purposes.
    """
    # Log version headers if provided
    if anthropic_version:
        logger.debug(f"API version: {anthropic_version}")
    if anthropic_beta:
        logger.debug(f"Beta features: {anthropic_beta}")

    try:
        # Convert messages and tools to dicts for token counting
        messages = [msg.model_dump() for msg in request.messages]
        tools = [tool.model_dump() for tool in request.tools] if request.tools else None

        # Handle system prompt
        system = request.system
        if isinstance(system, list):
            # Already a list of dicts
            pass
        # String or None is handled by count_request_tokens

        input_tokens = count_request_tokens(
            messages=messages,
            system=system,
            tools=tools,
        )

        return CountTokensResponse(input_tokens=input_tokens)

    except Exception as e:
        logger.exception("Error counting tokens")
        raise HTTPException(
            status_code=ErrorType.API.status_code,
            detail=ErrorResponse(
                error=ErrorDetail(
                    type=ErrorType.API.value,
                    message=f"Error counting tokens: {str(e)}",
                )
            ).model_dump(),
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


# ============================================================================
# Files API (Beta: files-api-2025-04-14)
# ============================================================================

def _check_file_store():
    """Check if file store is available, raise 503 if not."""
    store = get_file_store()
    if store is None:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error=ErrorDetail(
                    type="service_unavailable",
                    message="File storage is not configured. Initialize with init_file_store().",
                )
            ).model_dump(),
        )
    return store


@api_router.post("/v1/files", dependencies=[Depends(verify_api_key)])
async def upload_file(
    file: UploadFile = File(...),
    anthropic_version: Optional[str] = Header(None, alias="anthropic-version"),
    anthropic_beta: Optional[str] = Header(None, alias="anthropic-beta"),
):
    """Upload a file for use in API requests.

    Files can be referenced in Messages API requests using the file ID.
    Requires the files-api-2025-04-14 beta header.
    """
    store = _check_file_store()

    if anthropic_version:
        logger.debug(f"API version: {anthropic_version}")
    if anthropic_beta:
        logger.debug(f"Beta features: {anthropic_beta}")

    try:
        metadata = await store.upload(
            file=file.file,
            filename=file.filename or "unnamed",
            content_type=file.content_type,
        )
        return metadata
    except ValueError as e:
        raise HTTPException(
            status_code=413,
            detail=ErrorResponse(
                error=ErrorDetail(
                    type="request_too_large",
                    message=str(e),
                )
            ).model_dump(),
        )
    except Exception as e:
        logger.exception("Error uploading file")
        raise HTTPException(
            status_code=ErrorType.API.status_code,
            detail=ErrorResponse(
                error=ErrorDetail(
                    type=ErrorType.API.value,
                    message=f"Error uploading file: {str(e)}",
                )
            ).model_dump(),
        )


@api_router.get("/v1/files", dependencies=[Depends(verify_api_key)])
async def list_files(
    limit: int = Query(default=20, ge=1, le=1000),
    after_id: Optional[str] = Query(default=None),
    before_id: Optional[str] = Query(default=None),
    anthropic_version: Optional[str] = Header(None, alias="anthropic-version"),
    anthropic_beta: Optional[str] = Header(None, alias="anthropic-beta"),
):
    """List uploaded files with pagination."""
    store = _check_file_store()

    if anthropic_version:
        logger.debug(f"API version: {anthropic_version}")
    if anthropic_beta:
        logger.debug(f"Beta features: {anthropic_beta}")

    files, has_more = await store.list(
        limit=limit,
        after_id=after_id,
        before_id=before_id,
    )

    return FilesListResponse(
        data=files,
        first_id=files[0].id if files else None,
        last_id=files[-1].id if files else None,
        has_more=has_more,
    )


@api_router.get("/v1/files/{file_id}", dependencies=[Depends(verify_api_key)])
async def get_file(
    file_id: str,
    anthropic_version: Optional[str] = Header(None, alias="anthropic-version"),
    anthropic_beta: Optional[str] = Header(None, alias="anthropic-beta"),
):
    """Get metadata for a specific file."""
    store = _check_file_store()

    if anthropic_version:
        logger.debug(f"API version: {anthropic_version}")
    if anthropic_beta:
        logger.debug(f"Beta features: {anthropic_beta}")

    metadata = await store.get(file_id)
    if metadata is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error=ErrorDetail(
                    type=ErrorType.NOT_FOUND.value,
                    message=f"File not found: {file_id}",
                )
            ).model_dump(),
        )
    return metadata


@api_router.get("/v1/files/{file_id}/content", dependencies=[Depends(verify_api_key)])
async def get_file_content(
    file_id: str,
    anthropic_version: Optional[str] = Header(None, alias="anthropic-version"),
    anthropic_beta: Optional[str] = Header(None, alias="anthropic-beta"),
):
    """Download file content."""
    store = _check_file_store()

    if anthropic_version:
        logger.debug(f"API version: {anthropic_version}")
    if anthropic_beta:
        logger.debug(f"Beta features: {anthropic_beta}")

    result = await store.get_content(file_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error=ErrorDetail(
                    type=ErrorType.NOT_FOUND.value,
                    message=f"File not found: {file_id}",
                )
            ).model_dump(),
        )

    content, filename, mime_type = result
    return Response(
        content=content,
        media_type=mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@api_router.delete("/v1/files/{file_id}", dependencies=[Depends(verify_api_key)])
async def delete_file(
    file_id: str,
    anthropic_version: Optional[str] = Header(None, alias="anthropic-version"),
    anthropic_beta: Optional[str] = Header(None, alias="anthropic-beta"),
):
    """Delete a file."""
    store = _check_file_store()

    if anthropic_version:
        logger.debug(f"API version: {anthropic_version}")
    if anthropic_beta:
        logger.debug(f"Beta features: {anthropic_beta}")

    deleted = await store.delete(file_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error=ErrorDetail(
                    type=ErrorType.NOT_FOUND.value,
                    message=f"File not found: {file_id}",
                )
            ).model_dump(),
        )

    return FileDeletedResponse(id=file_id)


# ============================================================================
# Message Batches API
# ============================================================================

def _check_batch_processor():
    """Check if batch processor is available, raise 503 if not."""
    processor = get_batch_processor()
    if processor is None:
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error=ErrorDetail(
                    type="service_unavailable",
                    message="Batch processing is not configured. Initialize with init_batch_processor().",
                )
            ).model_dump(),
        )
    return processor


@api_router.post("/v1/messages/batches", dependencies=[Depends(verify_api_key)])
async def create_batch(
    request: CreateBatchRequest,
    anthropic_version: Optional[str] = Header(None, alias="anthropic-version"),
    anthropic_beta: Optional[str] = Header(None, alias="anthropic-beta"),
):
    """Create a message batch for parallel processing.

    Unlike the real Anthropic API which takes up to 24 hours,
    this bridge processes batches immediately using asyncio.
    """
    processor = _check_batch_processor()

    if anthropic_version:
        logger.debug(f"API version: {anthropic_version}")
    if anthropic_beta:
        logger.debug(f"Beta features: {anthropic_beta}")

    try:
        batch = await processor.create_batch(request.requests)
        return batch
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error=ErrorDetail(
                    type=ErrorType.INVALID_REQUEST.value,
                    message=str(e),
                )
            ).model_dump(),
        )
    except Exception as e:
        logger.exception("Error creating batch")
        raise HTTPException(
            status_code=ErrorType.API.status_code,
            detail=ErrorResponse(
                error=ErrorDetail(
                    type=ErrorType.API.value,
                    message=f"Error creating batch: {str(e)}",
                )
            ).model_dump(),
        )


@api_router.get("/v1/messages/batches", dependencies=[Depends(verify_api_key)])
async def list_batches(
    limit: int = Query(default=20, ge=1, le=1000),
    after_id: Optional[str] = Query(default=None),
    before_id: Optional[str] = Query(default=None),
    anthropic_version: Optional[str] = Header(None, alias="anthropic-version"),
    anthropic_beta: Optional[str] = Header(None, alias="anthropic-beta"),
):
    """List message batches with pagination."""
    processor = _check_batch_processor()

    if anthropic_version:
        logger.debug(f"API version: {anthropic_version}")
    if anthropic_beta:
        logger.debug(f"Beta features: {anthropic_beta}")

    batches, has_more = await processor.list_batches(
        limit=limit,
        after_id=after_id,
        before_id=before_id,
    )

    return BatchesListResponse(
        data=batches,
        first_id=batches[0].id if batches else None,
        last_id=batches[-1].id if batches else None,
        has_more=has_more,
    )


@api_router.get("/v1/messages/batches/{batch_id}", dependencies=[Depends(verify_api_key)])
async def get_batch(
    batch_id: str,
    anthropic_version: Optional[str] = Header(None, alias="anthropic-version"),
    anthropic_beta: Optional[str] = Header(None, alias="anthropic-beta"),
):
    """Get a specific message batch by ID."""
    processor = _check_batch_processor()

    if anthropic_version:
        logger.debug(f"API version: {anthropic_version}")
    if anthropic_beta:
        logger.debug(f"Beta features: {anthropic_beta}")

    batch = await processor.get_batch(batch_id)
    if batch is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error=ErrorDetail(
                    type=ErrorType.NOT_FOUND.value,
                    message=f"Batch not found: {batch_id}",
                )
            ).model_dump(),
        )
    return batch


@api_router.post("/v1/messages/batches/{batch_id}/cancel", dependencies=[Depends(verify_api_key)])
async def cancel_batch(
    batch_id: str,
    anthropic_version: Optional[str] = Header(None, alias="anthropic-version"),
    anthropic_beta: Optional[str] = Header(None, alias="anthropic-beta"),
):
    """Cancel a message batch."""
    processor = _check_batch_processor()

    if anthropic_version:
        logger.debug(f"API version: {anthropic_version}")
    if anthropic_beta:
        logger.debug(f"Beta features: {anthropic_beta}")

    batch = await processor.cancel_batch(batch_id)
    if batch is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error=ErrorDetail(
                    type=ErrorType.NOT_FOUND.value,
                    message=f"Batch not found: {batch_id}",
                )
            ).model_dump(),
        )
    return batch


@api_router.get("/v1/messages/batches/{batch_id}/results", dependencies=[Depends(verify_api_key)])
async def get_batch_results(
    batch_id: str,
    anthropic_version: Optional[str] = Header(None, alias="anthropic-version"),
    anthropic_beta: Optional[str] = Header(None, alias="anthropic-beta"),
):
    """Stream batch results as JSONL.

    Returns results for a completed batch. Each line is a JSON object
    with custom_id and result fields.
    """
    processor = _check_batch_processor()

    if anthropic_version:
        logger.debug(f"API version: {anthropic_version}")
    if anthropic_beta:
        logger.debug(f"Beta features: {anthropic_beta}")

    try:
        async def generate():
            async for line in processor.get_results(batch_id):
                yield line

        return EventSourceResponse(
            generate(),
            media_type="application/x-jsonlines",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=404 if "not found" in str(e).lower() else 400,
            detail=ErrorResponse(
                error=ErrorDetail(
                    type=ErrorType.NOT_FOUND.value if "not found" in str(e).lower() else ErrorType.INVALID_REQUEST.value,
                    message=str(e),
                )
            ).model_dump(),
        )


@api_router.delete("/v1/messages/batches/{batch_id}", dependencies=[Depends(verify_api_key)])
async def delete_batch(
    batch_id: str,
    anthropic_version: Optional[str] = Header(None, alias="anthropic-version"),
    anthropic_beta: Optional[str] = Header(None, alias="anthropic-beta"),
):
    """Delete a completed message batch."""
    processor = _check_batch_processor()

    if anthropic_version:
        logger.debug(f"API version: {anthropic_version}")
    if anthropic_beta:
        logger.debug(f"Beta features: {anthropic_beta}")

    try:
        deleted = await processor.delete_batch(batch_id)
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=ErrorResponse(
                    error=ErrorDetail(
                        type=ErrorType.NOT_FOUND.value,
                        message=f"Batch not found: {batch_id}",
                    )
                ).model_dump(),
            )
        return MessageBatchDeletedResponse(id=batch_id)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error=ErrorDetail(
                    type=ErrorType.INVALID_REQUEST.value,
                    message=str(e),
                )
            ).model_dump(),
        )
