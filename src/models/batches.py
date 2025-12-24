"""Message Batches API models matching Anthropic's schema.

These models support the Message Batches API for processing
multiple message requests in parallel.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class BatchRequestParams(BaseModel):
    """Parameters for a single batch request - same as MessagesRequest."""
    model: str
    messages: list[dict[str, Any]]
    max_tokens: int = 4096
    system: str | list[dict[str, Any]] | None = None
    stop_sequences: list[str] | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    thinking: dict[str, Any] | None = None


class BatchRequest(BaseModel):
    """A single request in a batch."""
    custom_id: str = Field(..., min_length=1, max_length=64)
    params: BatchRequestParams


class CreateBatchRequest(BaseModel):
    """Request body for POST /v1/messages/batches."""
    requests: list[BatchRequest] = Field(..., min_length=1, max_length=100)


class RequestCounts(BaseModel):
    """Counts of requests in different states."""
    processing: int = 0
    succeeded: int = 0
    errored: int = 0
    canceled: int = 0
    expired: int = 0


ProcessingStatus = Literal["in_progress", "canceling", "ended"]


class MessageBatch(BaseModel):
    """A message batch object - matches Anthropic's schema."""
    id: str
    type: Literal["message_batch"] = "message_batch"
    processing_status: ProcessingStatus
    request_counts: RequestCounts
    created_at: str  # RFC 3339 datetime string
    ended_at: str | None = None
    expires_at: str  # RFC 3339 datetime string
    archived_at: str | None = None
    cancel_initiated_at: str | None = None
    results_url: str | None = None


class MessageBatchDeletedResponse(BaseModel):
    """Response when a batch is deleted."""
    id: str
    type: Literal["message_batch_deleted"] = "message_batch_deleted"


class BatchesListResponse(BaseModel):
    """Response for GET /v1/messages/batches - matches Anthropic's pagination format."""
    data: list[MessageBatch]
    first_id: str | None = None
    last_id: str | None = None
    has_more: bool = False


# Batch result types for JSONL output


class SucceededResult(BaseModel):
    """A successful batch request result."""
    type: Literal["succeeded"] = "succeeded"
    message: dict[str, Any]


class ErroredResult(BaseModel):
    """A failed batch request result."""
    type: Literal["errored"] = "errored"
    error: dict[str, Any]


class CanceledResult(BaseModel):
    """A canceled batch request result."""
    type: Literal["canceled"] = "canceled"


class ExpiredResult(BaseModel):
    """An expired batch request result."""
    type: Literal["expired"] = "expired"


BatchResult = SucceededResult | ErroredResult | CanceledResult | ExpiredResult


class BatchResultLine(BaseModel):
    """A single line in the batch results JSONL output."""
    custom_id: str
    result: BatchResult
