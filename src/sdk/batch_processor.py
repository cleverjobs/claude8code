"""Batch processor for the Message Batches API.

Provides parallel processing of message requests using asyncio.
Unlike the real Anthropic API (which takes up to 24 hours), this
processes batches immediately for testing and development purposes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, AsyncIterator

from ..models.batches import (
    BatchRequest,
    BatchResultLine,
    CanceledResult,
    ErroredResult,
    MessageBatch,
    RequestCounts,
    SucceededResult,
)
from ..models.requests import Message, MessagesRequest

logger = logging.getLogger(__name__)


# Maximum requests per batch (lower than real API for bridge use)
MAX_BATCH_SIZE = 100

# Maximum concurrent requests to process
DEFAULT_CONCURRENCY = 5


@dataclass
class StoredBatch:
    """Internal representation of a stored batch."""

    id: str
    requests: list[BatchRequest]
    created_at: datetime
    expires_at: datetime
    processing_status: str = "in_progress"
    ended_at: datetime | None = None
    cancel_initiated_at: datetime | None = None
    archived_at: datetime | None = None
    results: dict[str, BatchResultLine] = field(default_factory=dict)
    _processing_task: asyncio.Task[None] | None = field(default=None, repr=False)
    _canceled: bool = field(default=False, repr=False)

    def get_request_counts(self) -> RequestCounts:
        """Get current request counts."""
        succeeded = sum(1 for r in self.results.values() if r.result.type == "succeeded")
        errored = sum(1 for r in self.results.values() if r.result.type == "errored")
        canceled = sum(1 for r in self.results.values() if r.result.type == "canceled")
        expired = sum(1 for r in self.results.values() if r.result.type == "expired")
        processing = len(self.requests) - len(self.results)

        return RequestCounts(
            processing=processing,
            succeeded=succeeded,
            errored=errored,
            canceled=canceled,
            expired=expired,
        )

    def to_api_response(self, base_url: str = "") -> MessageBatch:
        """Convert to API response format."""
        results_url = None
        if self.processing_status == "ended" and self.results:
            results_url = f"{base_url}/v1/messages/batches/{self.id}/results"

        return MessageBatch(
            id=self.id,
            processing_status=self.processing_status,  # type: ignore
            request_counts=self.get_request_counts(),
            created_at=self.created_at.isoformat() + "Z",
            ended_at=self.ended_at.isoformat() + "Z" if self.ended_at else None,
            expires_at=self.expires_at.isoformat() + "Z",
            archived_at=self.archived_at.isoformat() + "Z" if self.archived_at else None,
            cancel_initiated_at=(
                self.cancel_initiated_at.isoformat() + "Z" if self.cancel_initiated_at else None
            ),
            results_url=results_url,
        )


@dataclass
class BatchProcessor:
    """Batch processor for parallel message request execution.

    Processes batches using asyncio for parallel execution.
    Unlike the real API, batches are processed immediately.
    """

    concurrency: int = DEFAULT_CONCURRENCY
    results_ttl_hours: int = 24 * 29  # 29 days like real API
    _batches: dict[str, StoredBatch] = field(default_factory=dict)
    _process_request_fn: Any = None  # Will be set to process_request function

    def set_request_processor(self, fn: Any) -> None:
        """Set the function to use for processing individual requests."""
        self._process_request_fn = fn

    def _generate_id(self) -> str:
        """Generate a unique batch ID."""
        return f"msgbatch_{uuid.uuid4().hex[:24]}"

    async def create_batch(self, requests: list[BatchRequest]) -> MessageBatch:
        """Create a new batch and start processing.

        Args:
            requests: List of batch requests to process.

        Returns:
            MessageBatch object for the created batch.

        Raises:
            ValueError: If batch exceeds size limit.
        """
        if len(requests) > MAX_BATCH_SIZE:
            raise ValueError(f"Batch exceeds maximum size of {MAX_BATCH_SIZE} requests")

        batch_id = self._generate_id()
        now = datetime.utcnow()

        batch = StoredBatch(
            id=batch_id,
            requests=requests,
            created_at=now,
            expires_at=now + timedelta(hours=self.results_ttl_hours),
        )
        self._batches[batch_id] = batch

        # Start processing in background
        batch._processing_task = asyncio.create_task(self._process_batch(batch))

        logger.info(f"Created batch {batch_id} with {len(requests)} requests")
        return batch.to_api_response()

    async def _process_batch(self, batch: StoredBatch) -> None:
        """Process all requests in a batch with concurrency control."""
        semaphore = asyncio.Semaphore(self.concurrency)

        async def process_one(request: BatchRequest) -> None:
            async with semaphore:
                if batch._canceled:
                    # Mark as canceled
                    batch.results[request.custom_id] = BatchResultLine(
                        custom_id=request.custom_id,
                        result=CanceledResult(),
                    )
                    return

                try:
                    result = await self._execute_request(request)
                    batch.results[request.custom_id] = BatchResultLine(
                        custom_id=request.custom_id,
                        result=SucceededResult(message=result),
                    )
                except Exception as e:
                    logger.warning(f"Batch request {request.custom_id} failed: {e}")
                    batch.results[request.custom_id] = BatchResultLine(
                        custom_id=request.custom_id,
                        result=ErroredResult(error={"type": "api_error", "message": str(e)}),
                    )

        # Process all requests concurrently (with semaphore limiting)
        await asyncio.gather(*[process_one(req) for req in batch.requests])

        # Mark batch as ended
        batch.processing_status = "ended"
        batch.ended_at = datetime.utcnow()
        logger.info(f"Batch {batch.id} completed: {batch.get_request_counts()}")

    async def _execute_request(self, request: BatchRequest) -> dict[str, Any]:
        """Execute a single request from the batch."""
        if self._process_request_fn is None:
            raise RuntimeError("Request processor not configured")

        # Convert batch params to MessagesRequest
        params = request.params
        messages = [Message(role=m["role"], content=m["content"]) for m in params.messages]

        msg_request = MessagesRequest(
            model=params.model,
            messages=messages,
            max_tokens=params.max_tokens,
            system=params.system,
            stop_sequences=params.stop_sequences,
            stream=False,  # Batch never streams
            temperature=params.temperature,
            top_p=params.top_p,
            top_k=params.top_k,
            tools=params.tools,  # type: ignore
            tool_choice=params.tool_choice,
            metadata=params.metadata,
        )

        # Execute via the main process_request function
        response = await self._process_request_fn(msg_request)
        result: dict[str, Any] = response.model_dump()
        return result

    async def get_batch(self, batch_id: str) -> MessageBatch | None:
        """Get a batch by ID.

        Args:
            batch_id: The batch ID.

        Returns:
            MessageBatch or None if not found.
        """
        batch = self._batches.get(batch_id)
        if batch is None:
            return None
        return batch.to_api_response()

    async def list_batches(
        self,
        limit: int = 20,
        after_id: str | None = None,
        before_id: str | None = None,
    ) -> tuple[list[MessageBatch], bool]:
        """List batches with pagination.

        Args:
            limit: Maximum number of batches to return.
            after_id: Return batches after this ID (exclusive).
            before_id: Return batches before this ID (exclusive).

        Returns:
            Tuple of (batches list, has_more flag).
        """
        # Sort batches by creation time (newest first)
        sorted_batches = sorted(
            self._batches.values(),
            key=lambda b: b.created_at,
            reverse=True,
        )

        # Apply cursor-based pagination
        if after_id:
            cursor_idx = None
            for i, b in enumerate(sorted_batches):
                if b.id == after_id:
                    cursor_idx = i
                    break
            if cursor_idx is not None:
                sorted_batches = sorted_batches[cursor_idx + 1 :]

        if before_id:
            cursor_idx = None
            for i, b in enumerate(sorted_batches):
                if b.id == before_id:
                    cursor_idx = i
                    break
            if cursor_idx is not None:
                sorted_batches = sorted_batches[:cursor_idx]

        # Apply limit
        has_more = len(sorted_batches) > limit
        result = sorted_batches[:limit]

        return [b.to_api_response() for b in result], has_more

    async def cancel_batch(self, batch_id: str) -> MessageBatch | None:
        """Cancel a batch.

        Args:
            batch_id: The batch ID.

        Returns:
            Updated MessageBatch or None if not found.
        """
        batch = self._batches.get(batch_id)
        if batch is None:
            return None

        if batch.processing_status == "ended":
            # Already ended, return as-is
            return batch.to_api_response()

        # Mark as canceling
        batch._canceled = True
        batch.cancel_initiated_at = datetime.utcnow()
        batch.processing_status = "canceling"

        logger.info(f"Canceling batch {batch_id}")
        return batch.to_api_response()

    async def delete_batch(self, batch_id: str) -> bool:
        """Delete a batch.

        Args:
            batch_id: The batch ID.

        Returns:
            True if deleted, False if not found or not ended.
        """
        batch = self._batches.get(batch_id)
        if batch is None:
            return False

        if batch.processing_status != "ended":
            raise ValueError("Cannot delete batch that is not ended")

        del self._batches[batch_id]
        logger.info(f"Deleted batch {batch_id}")
        return True

    async def get_results(self, batch_id: str) -> AsyncIterator[str]:
        """Stream batch results as JSONL.

        Args:
            batch_id: The batch ID.

        Yields:
            JSONL lines with batch results.

        Raises:
            ValueError: If batch not found or not ended.
        """
        batch = self._batches.get(batch_id)
        if batch is None:
            raise ValueError(f"Batch not found: {batch_id}")

        if batch.processing_status != "ended":
            raise ValueError(f"Batch not ended: {batch_id}")

        # Yield results as JSONL
        for custom_id, result in batch.results.items():
            yield json.dumps(result.model_dump()) + "\n"

    def get_stats(self) -> dict[str, Any]:
        """Get processor statistics."""
        status_counts = {"in_progress": 0, "canceling": 0, "ended": 0}
        for batch in self._batches.values():
            status = batch.processing_status
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "batch_count": len(self._batches),
            "status_counts": status_counts,
            "concurrency": self.concurrency,
            "max_batch_size": MAX_BATCH_SIZE,
        }


# Global batch processor instance
_batch_processor: BatchProcessor | None = None


def get_batch_processor() -> BatchProcessor | None:
    """Get the global batch processor instance."""
    return _batch_processor


def init_batch_processor(
    concurrency: int = DEFAULT_CONCURRENCY,
    process_request_fn: Any = None,
) -> BatchProcessor:
    """Initialize the global batch processor.

    Args:
        concurrency: Maximum concurrent requests per batch.
        process_request_fn: Function to process individual requests.

    Returns:
        The initialized BatchProcessor.
    """
    global _batch_processor
    _batch_processor = BatchProcessor(concurrency=concurrency)
    if process_request_fn:
        _batch_processor.set_request_processor(process_request_fn)
    return _batch_processor


async def shutdown_batch_processor() -> None:
    """Shutdown the global batch processor."""
    global _batch_processor
    if _batch_processor:
        # Cancel any running batches
        for batch in _batch_processor._batches.values():
            if batch._processing_task and not batch._processing_task.done():
                batch._processing_task.cancel()
        _batch_processor = None
