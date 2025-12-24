"""Unit tests for batch processor module."""

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.sdk.batch_processor import (
    MAX_BATCH_SIZE,
    DEFAULT_CONCURRENCY,
    StoredBatch,
    BatchProcessor,
    get_batch_processor,
    init_batch_processor,
    shutdown_batch_processor,
)
from src.models.batches import (
    BatchRequest,
    BatchRequestParams,
    BatchResultLine,
    SucceededResult,
    ErroredResult,
    CanceledResult,
    ExpiredResult,
)


def create_batch_request(custom_id: str, content: str = "Hello") -> BatchRequest:
    """Helper to create a BatchRequest."""
    return BatchRequest(
        custom_id=custom_id,
        params=BatchRequestParams(
            model="claude-sonnet-4-5-20250514",
            messages=[{"role": "user", "content": content}],
            max_tokens=100,
        ),
    )


class TestStoredBatch:
    """Test StoredBatch dataclass."""

    def test_get_request_counts_initial(self):
        """Test request counts for new batch."""
        batch = StoredBatch(
            id="msgbatch_test",
            requests=[create_batch_request("req1"), create_batch_request("req2")],
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=29),
        )

        counts = batch.get_request_counts()
        assert counts.processing == 2
        assert counts.succeeded == 0
        assert counts.errored == 0
        assert counts.canceled == 0
        assert counts.expired == 0

    def test_get_request_counts_mixed(self):
        """Test request counts with mixed results."""
        batch = StoredBatch(
            id="msgbatch_test",
            requests=[
                create_batch_request("req1"),
                create_batch_request("req2"),
                create_batch_request("req3"),
                create_batch_request("req4"),
            ],
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=29),
        )

        # Add mixed results
        batch.results["req1"] = BatchResultLine(
            custom_id="req1", result=SucceededResult(message={"id": "msg1"})
        )
        batch.results["req2"] = BatchResultLine(
            custom_id="req2", result=ErroredResult(error={"type": "error"})
        )
        batch.results["req3"] = BatchResultLine(
            custom_id="req3", result=CanceledResult()
        )

        counts = batch.get_request_counts()
        assert counts.processing == 1  # req4 still processing
        assert counts.succeeded == 1
        assert counts.errored == 1
        assert counts.canceled == 1
        assert counts.expired == 0

    def test_get_request_counts_with_expired(self):
        """Test request counts with expired result."""
        batch = StoredBatch(
            id="msgbatch_test",
            requests=[create_batch_request("req1")],
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=29),
        )

        batch.results["req1"] = BatchResultLine(
            custom_id="req1", result=ExpiredResult()
        )

        counts = batch.get_request_counts()
        assert counts.expired == 1
        assert counts.processing == 0

    def test_to_api_response_in_progress(self):
        """Test API response for in-progress batch."""
        batch = StoredBatch(
            id="msgbatch_abc123",
            requests=[create_batch_request("req1")],
            created_at=datetime(2024, 1, 15, 12, 0, 0),
            expires_at=datetime(2024, 2, 13, 12, 0, 0),
            processing_status="in_progress",
        )

        response = batch.to_api_response()
        assert response.id == "msgbatch_abc123"
        assert response.type == "message_batch"
        assert response.processing_status == "in_progress"
        assert response.created_at == "2024-01-15T12:00:00Z"
        assert response.expires_at == "2024-02-13T12:00:00Z"
        assert response.ended_at is None
        assert response.results_url is None

    def test_to_api_response_ended(self):
        """Test API response for ended batch with results URL."""
        batch = StoredBatch(
            id="msgbatch_xyz789",
            requests=[create_batch_request("req1")],
            created_at=datetime(2024, 1, 15, 12, 0, 0),
            expires_at=datetime(2024, 2, 13, 12, 0, 0),
            processing_status="ended",
            ended_at=datetime(2024, 1, 15, 12, 5, 0),
        )
        batch.results["req1"] = BatchResultLine(
            custom_id="req1", result=SucceededResult(message={"id": "msg1"})
        )

        response = batch.to_api_response(base_url="http://localhost:8787")
        assert response.processing_status == "ended"
        assert response.ended_at == "2024-01-15T12:05:00Z"
        assert response.results_url == "http://localhost:8787/v1/messages/batches/msgbatch_xyz789/results"

    def test_to_api_response_canceling(self):
        """Test API response for canceling batch."""
        batch = StoredBatch(
            id="msgbatch_cancel",
            requests=[create_batch_request("req1")],
            created_at=datetime(2024, 1, 15, 12, 0, 0),
            expires_at=datetime(2024, 2, 13, 12, 0, 0),
            processing_status="canceling",
            cancel_initiated_at=datetime(2024, 1, 15, 12, 2, 0),
        )

        response = batch.to_api_response()
        assert response.processing_status == "canceling"
        assert response.cancel_initiated_at == "2024-01-15T12:02:00Z"

    def test_to_api_response_archived(self):
        """Test API response for archived batch."""
        batch = StoredBatch(
            id="msgbatch_archived",
            requests=[create_batch_request("req1")],
            created_at=datetime(2024, 1, 15, 12, 0, 0),
            expires_at=datetime(2024, 2, 13, 12, 0, 0),
            processing_status="ended",
            ended_at=datetime(2024, 1, 15, 12, 5, 0),
            archived_at=datetime(2024, 1, 20, 12, 0, 0),
        )

        response = batch.to_api_response()
        assert response.archived_at == "2024-01-20T12:00:00Z"


class TestBatchProcessorInit:
    """Test BatchProcessor initialization."""

    def test_default_concurrency(self):
        """Test default concurrency setting."""
        processor = BatchProcessor()
        assert processor.concurrency == DEFAULT_CONCURRENCY

    def test_custom_concurrency(self):
        """Test custom concurrency setting."""
        processor = BatchProcessor(concurrency=10)
        assert processor.concurrency == 10

    def test_set_request_processor(self):
        """Test setting request processor function."""
        processor = BatchProcessor()
        mock_fn = AsyncMock()

        processor.set_request_processor(mock_fn)
        assert processor._process_request_fn is mock_fn


class TestBatchProcessorIdGeneration:
    """Test BatchProcessor ID generation."""

    def test_generate_id_format(self):
        """Test batch ID format."""
        processor = BatchProcessor()

        batch_id = processor._generate_id()
        assert batch_id.startswith("msgbatch_")
        assert len(batch_id) == 33  # "msgbatch_" + 24 hex chars

    def test_generate_id_uniqueness(self):
        """Test batch ID uniqueness."""
        processor = BatchProcessor()

        ids = [processor._generate_id() for _ in range(100)]
        assert len(ids) == len(set(ids))


class TestBatchProcessorCreateBatch:
    """Test BatchProcessor create_batch functionality."""

    @pytest.mark.asyncio
    async def test_create_batch_success(self):
        """Test successful batch creation."""
        processor = BatchProcessor()
        mock_process = AsyncMock(return_value=MagicMock(
            model_dump=lambda: {"id": "msg_123", "content": []}
        ))
        processor.set_request_processor(mock_process)

        requests = [create_batch_request("req1")]
        batch = await processor.create_batch(requests)

        assert batch.id.startswith("msgbatch_")
        assert batch.processing_status == "in_progress"
        assert batch.request_counts.processing == 1

        # Wait for processing to complete
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_create_batch_size_limit(self):
        """Test batch rejects too many requests."""
        processor = BatchProcessor()

        requests = [create_batch_request(f"req{i}") for i in range(MAX_BATCH_SIZE + 1)]

        with pytest.raises(ValueError) as exc_info:
            await processor.create_batch(requests)
        assert f"exceeds maximum size of {MAX_BATCH_SIZE}" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_batch_starts_processing(self):
        """Test batch processing starts automatically."""
        processor = BatchProcessor()
        mock_process = AsyncMock(return_value=MagicMock(
            model_dump=lambda: {"id": "msg_123", "content": []}
        ))
        processor.set_request_processor(mock_process)

        requests = [create_batch_request("req1")]
        batch = await processor.create_batch(requests)

        # Processing task should be created
        stored_batch = processor._batches[batch.id]
        assert stored_batch._processing_task is not None

        # Wait for completion
        await asyncio.sleep(0.1)
        assert stored_batch.processing_status == "ended"


class TestBatchProcessorProcessing:
    """Test BatchProcessor request processing."""

    @pytest.mark.asyncio
    async def test_process_batch_success(self):
        """Test successful batch processing."""
        processor = BatchProcessor()
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"id": "msg_123", "content": [{"type": "text", "text": "Hi"}]}
        mock_process = AsyncMock(return_value=mock_response)
        processor.set_request_processor(mock_process)

        requests = [
            create_batch_request("req1", "Hello"),
            create_batch_request("req2", "World"),
        ]
        batch = await processor.create_batch(requests)

        # Wait for processing
        await asyncio.sleep(0.2)

        stored = processor._batches[batch.id]
        assert stored.processing_status == "ended"
        assert len(stored.results) == 2
        assert all(r.result.type == "succeeded" for r in stored.results.values())

    @pytest.mark.asyncio
    async def test_process_batch_with_errors(self):
        """Test batch processing with request errors."""
        processor = BatchProcessor()

        call_count = 0
        async def mock_process(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Request failed")
            mock_response = MagicMock()
            mock_response.model_dump.return_value = {"id": "msg_123"}
            return mock_response

        processor.set_request_processor(mock_process)

        requests = [
            create_batch_request("req1"),
            create_batch_request("req2"),
        ]
        batch = await processor.create_batch(requests)

        # Wait for processing
        await asyncio.sleep(0.2)

        stored = processor._batches[batch.id]
        assert stored.processing_status == "ended"

        # One should have errored
        error_count = sum(1 for r in stored.results.values() if r.result.type == "errored")
        success_count = sum(1 for r in stored.results.values() if r.result.type == "succeeded")
        assert error_count == 1
        assert success_count == 1

    @pytest.mark.asyncio
    async def test_execute_request_no_processor(self):
        """Test execute request fails without processor."""
        processor = BatchProcessor()

        request = create_batch_request("req1")

        with pytest.raises(RuntimeError) as exc_info:
            await processor._execute_request(request)
        assert "Request processor not configured" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_process_batch_respects_concurrency(self):
        """Test batch processing respects concurrency limit."""
        processor = BatchProcessor(concurrency=2)

        concurrent_calls = []
        max_concurrent = 0

        async def mock_process(request):
            nonlocal max_concurrent
            concurrent_calls.append(1)
            current = len(concurrent_calls)
            if current > max_concurrent:
                max_concurrent = current

            await asyncio.sleep(0.05)  # Simulate processing time

            concurrent_calls.pop()
            mock_response = MagicMock()
            mock_response.model_dump.return_value = {"id": "msg_123"}
            return mock_response

        processor.set_request_processor(mock_process)

        # Create batch with more requests than concurrency
        requests = [create_batch_request(f"req{i}") for i in range(5)]
        await processor.create_batch(requests)

        # Wait for completion
        await asyncio.sleep(0.5)

        # Should never have exceeded concurrency limit
        assert max_concurrent <= 2


class TestBatchProcessorCancel:
    """Test BatchProcessor cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_batch_in_progress(self):
        """Test canceling an in-progress batch."""
        processor = BatchProcessor()

        # Slow processor to keep batch processing
        async def slow_process(request):
            await asyncio.sleep(10)
            mock_response = MagicMock()
            mock_response.model_dump.return_value = {"id": "msg_123"}
            return mock_response

        processor.set_request_processor(slow_process)

        requests = [create_batch_request("req1")]
        batch = await processor.create_batch(requests)

        # Cancel immediately
        result = await processor.cancel_batch(batch.id)

        assert result is not None
        assert result.processing_status == "canceling"
        assert result.cancel_initiated_at is not None

        # Wait a moment and check canceled flag is set
        stored = processor._batches[batch.id]
        assert stored._canceled is True

    @pytest.mark.asyncio
    async def test_cancel_batch_not_found(self):
        """Test canceling nonexistent batch."""
        processor = BatchProcessor()

        result = await processor.cancel_batch("msgbatch_notfound")
        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_batch_already_ended(self):
        """Test canceling already ended batch returns as-is."""
        processor = BatchProcessor()
        mock_process = AsyncMock(return_value=MagicMock(
            model_dump=lambda: {"id": "msg_123"}
        ))
        processor.set_request_processor(mock_process)

        requests = [create_batch_request("req1")]
        batch = await processor.create_batch(requests)

        # Wait for completion
        await asyncio.sleep(0.1)

        # Try to cancel ended batch
        result = await processor.cancel_batch(batch.id)
        assert result.processing_status == "ended"


class TestBatchProcessorDelete:
    """Test BatchProcessor delete functionality."""

    @pytest.mark.asyncio
    async def test_delete_batch_success(self):
        """Test deleting an ended batch."""
        processor = BatchProcessor()
        mock_process = AsyncMock(return_value=MagicMock(
            model_dump=lambda: {"id": "msg_123"}
        ))
        processor.set_request_processor(mock_process)

        requests = [create_batch_request("req1")]
        batch = await processor.create_batch(requests)

        # Wait for completion
        await asyncio.sleep(0.1)

        result = await processor.delete_batch(batch.id)
        assert result is True
        assert batch.id not in processor._batches

    @pytest.mark.asyncio
    async def test_delete_batch_not_found(self):
        """Test deleting nonexistent batch."""
        processor = BatchProcessor()

        result = await processor.delete_batch("msgbatch_notfound")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_batch_not_ended(self):
        """Test deleting batch that is still processing."""
        processor = BatchProcessor()

        async def slow_process(request):
            await asyncio.sleep(10)
            mock_response = MagicMock()
            mock_response.model_dump.return_value = {"id": "msg_123"}
            return mock_response

        processor.set_request_processor(slow_process)

        requests = [create_batch_request("req1")]
        batch = await processor.create_batch(requests)

        with pytest.raises(ValueError) as exc_info:
            await processor.delete_batch(batch.id)
        assert "not ended" in str(exc_info.value)


class TestBatchProcessorGetBatch:
    """Test BatchProcessor get_batch functionality."""

    @pytest.mark.asyncio
    async def test_get_batch_found(self):
        """Test getting existing batch."""
        processor = BatchProcessor()
        mock_process = AsyncMock(return_value=MagicMock(
            model_dump=lambda: {"id": "msg_123"}
        ))
        processor.set_request_processor(mock_process)

        requests = [create_batch_request("req1")]
        created = await processor.create_batch(requests)

        result = await processor.get_batch(created.id)
        assert result is not None
        assert result.id == created.id

    @pytest.mark.asyncio
    async def test_get_batch_not_found(self):
        """Test getting nonexistent batch."""
        processor = BatchProcessor()

        result = await processor.get_batch("msgbatch_notfound")
        assert result is None


class TestBatchProcessorListBatches:
    """Test BatchProcessor list_batches functionality."""

    @pytest.mark.asyncio
    async def test_list_batches_empty(self):
        """Test listing when no batches exist."""
        processor = BatchProcessor()

        batches, has_more = await processor.list_batches()
        assert batches == []
        assert has_more is False

    @pytest.mark.asyncio
    async def test_list_batches_all(self):
        """Test listing all batches."""
        processor = BatchProcessor()
        mock_process = AsyncMock(return_value=MagicMock(
            model_dump=lambda: {"id": "msg_123"}
        ))
        processor.set_request_processor(mock_process)

        # Create multiple batches
        for i in range(3):
            await processor.create_batch([create_batch_request(f"req{i}")])

        # Wait for processing
        await asyncio.sleep(0.2)

        batches, has_more = await processor.list_batches(limit=10)
        assert len(batches) == 3
        assert has_more is False

    @pytest.mark.asyncio
    async def test_list_batches_with_limit(self):
        """Test listing with limit."""
        processor = BatchProcessor()
        mock_process = AsyncMock(return_value=MagicMock(
            model_dump=lambda: {"id": "msg_123"}
        ))
        processor.set_request_processor(mock_process)

        for i in range(5):
            await processor.create_batch([create_batch_request(f"req{i}")])

        await asyncio.sleep(0.2)

        batches, has_more = await processor.list_batches(limit=3)
        assert len(batches) == 3
        assert has_more is True

    @pytest.mark.asyncio
    async def test_list_batches_pagination(self):
        """Test listing with pagination cursors."""
        processor = BatchProcessor()
        mock_process = AsyncMock(return_value=MagicMock(
            model_dump=lambda: {"id": "msg_123"}
        ))
        processor.set_request_processor(mock_process)

        for i in range(3):
            await processor.create_batch([create_batch_request(f"req{i}")])

        await asyncio.sleep(0.2)

        all_batches, _ = await processor.list_batches(limit=10)

        # Get batches after the first one
        cursor_id = all_batches[0].id
        after_batches, _ = await processor.list_batches(after_id=cursor_id)

        assert len(after_batches) <= 2
        assert all(b.id != cursor_id for b in after_batches)


class TestBatchProcessorGetResults:
    """Test BatchProcessor get_results functionality."""

    @pytest.mark.asyncio
    async def test_get_results_success(self):
        """Test streaming results for ended batch."""
        processor = BatchProcessor()
        mock_process = AsyncMock(return_value=MagicMock(
            model_dump=lambda: {"id": "msg_123", "content": []}
        ))
        processor.set_request_processor(mock_process)

        requests = [
            create_batch_request("req1"),
            create_batch_request("req2"),
        ]
        batch = await processor.create_batch(requests)

        # Wait for completion
        await asyncio.sleep(0.2)

        results = []
        async for line in processor.get_results(batch.id):
            results.append(json.loads(line.strip()))

        assert len(results) == 2
        assert all("custom_id" in r for r in results)
        assert all("result" in r for r in results)

    @pytest.mark.asyncio
    async def test_get_results_not_found(self):
        """Test streaming results for nonexistent batch."""
        processor = BatchProcessor()

        with pytest.raises(ValueError) as exc_info:
            async for _ in processor.get_results("msgbatch_notfound"):
                pass
        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_results_not_ended(self):
        """Test streaming results for batch still processing."""
        processor = BatchProcessor()

        async def slow_process(request):
            await asyncio.sleep(10)
            mock_response = MagicMock()
            mock_response.model_dump.return_value = {"id": "msg_123"}
            return mock_response

        processor.set_request_processor(slow_process)

        requests = [create_batch_request("req1")]
        batch = await processor.create_batch(requests)

        with pytest.raises(ValueError) as exc_info:
            async for _ in processor.get_results(batch.id):
                pass
        assert "not ended" in str(exc_info.value)


class TestBatchProcessorStats:
    """Test BatchProcessor statistics."""

    @pytest.mark.asyncio
    async def test_get_stats_empty(self):
        """Test stats with no batches."""
        processor = BatchProcessor()

        stats = processor.get_stats()
        assert stats["batch_count"] == 0
        assert stats["concurrency"] == DEFAULT_CONCURRENCY
        assert stats["max_batch_size"] == MAX_BATCH_SIZE
        assert "status_counts" in stats

    @pytest.mark.asyncio
    async def test_get_stats_with_batches(self):
        """Test stats with batches."""
        processor = BatchProcessor()
        mock_process = AsyncMock(return_value=MagicMock(
            model_dump=lambda: {"id": "msg_123"}
        ))
        processor.set_request_processor(mock_process)

        for i in range(3):
            await processor.create_batch([create_batch_request(f"req{i}")])

        await asyncio.sleep(0.2)

        stats = processor.get_stats()
        assert stats["batch_count"] == 3
        assert stats["status_counts"]["ended"] == 3


class TestGlobalBatchProcessor:
    """Test global batch processor functions."""

    def test_get_batch_processor_initially_none(self):
        """Test get_batch_processor returns None before init."""
        import src.sdk.batch_processor as module
        original = module._batch_processor
        module._batch_processor = None

        try:
            result = get_batch_processor()
            assert result is None
        finally:
            module._batch_processor = original

    def test_init_batch_processor(self):
        """Test init_batch_processor creates processor."""
        import src.sdk.batch_processor as module
        original = module._batch_processor

        try:
            mock_fn = AsyncMock()
            processor = init_batch_processor(concurrency=3, process_request_fn=mock_fn)

            assert processor is not None
            assert processor.concurrency == 3
            assert processor._process_request_fn is mock_fn
            assert get_batch_processor() is processor
        finally:
            module._batch_processor = original

    @pytest.mark.asyncio
    async def test_shutdown_batch_processor(self):
        """Test shutdown_batch_processor cleans up."""
        import src.sdk.batch_processor as module
        original = module._batch_processor

        try:
            processor = init_batch_processor()
            mock_process = AsyncMock(return_value=MagicMock(
                model_dump=lambda: {"id": "msg_123"}
            ))
            processor.set_request_processor(mock_process)

            # Create a batch
            await processor.create_batch([create_batch_request("req1")])
            await asyncio.sleep(0.1)

            await shutdown_batch_processor()
            assert get_batch_processor() is None
        finally:
            module._batch_processor = original

    @pytest.mark.asyncio
    async def test_shutdown_batch_processor_when_none(self):
        """Test shutdown_batch_processor when no processor exists."""
        import src.sdk.batch_processor as module
        original = module._batch_processor
        module._batch_processor = None

        try:
            await shutdown_batch_processor()  # Should not raise
        finally:
            module._batch_processor = original

    @pytest.mark.asyncio
    async def test_shutdown_cancels_running_batches(self):
        """Test shutdown cancels running batch tasks."""
        import src.sdk.batch_processor as module
        original = module._batch_processor

        try:
            processor = init_batch_processor()

            processing_started = asyncio.Event()

            async def slow_process(request):
                processing_started.set()
                await asyncio.sleep(10)
                mock_response = MagicMock()
                mock_response.model_dump.return_value = {"id": "msg_123"}
                return mock_response

            processor.set_request_processor(slow_process)

            batch = await processor.create_batch([create_batch_request("req1")])
            task = processor._batches[batch.id]._processing_task

            # Wait for processing to start
            await asyncio.wait_for(processing_started.wait(), timeout=1.0)

            await shutdown_batch_processor()

            # Give a moment for cancellation to propagate
            await asyncio.sleep(0.1)

            # Task should be cancelled or done
            assert task.cancelled() or task.done()
        finally:
            module._batch_processor = original
