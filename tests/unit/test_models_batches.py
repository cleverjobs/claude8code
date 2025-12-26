"""Unit tests for Message Batches API models."""

import pytest
from pydantic import ValidationError

from src.models.batches import (
    BatchesListResponse,
    BatchRequest,
    BatchRequestParams,
    BatchResultLine,
    CanceledResult,
    CreateBatchRequest,
    ErroredResult,
    ExpiredResult,
    MessageBatch,
    MessageBatchDeletedResponse,
    RequestCounts,
    SucceededResult,
)


class TestBatchRequestParams:
    """Test BatchRequestParams model."""

    def test_minimal_params(self) -> None:
        """Test creating with minimal required fields."""
        params = BatchRequestParams(
            model="claude-sonnet-4-5-20250514",
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert params.model == "claude-sonnet-4-5-20250514"
        assert len(params.messages) == 1
        assert params.max_tokens == 4096  # default

    def test_default_values(self) -> None:
        """Test all default values."""
        params = BatchRequestParams(
            model="claude-sonnet-4-5",
            messages=[],
        )

        assert params.max_tokens == 4096
        assert params.system is None
        assert params.stop_sequences is None
        assert params.temperature is None
        assert params.top_p is None
        assert params.top_k is None
        assert params.tools is None
        assert params.tool_choice is None
        assert params.metadata is None
        assert params.thinking is None

    def test_all_optional_fields(self) -> None:
        """Test setting all optional fields."""
        params = BatchRequestParams(
            model="claude-sonnet-4-5",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=1024,
            system="You are helpful.",
            stop_sequences=["STOP"],
            temperature=0.7,
            top_p=0.9,
            top_k=40,
            tools=[{"name": "test_tool", "input_schema": {}}],
            tool_choice={"type": "auto"},
            metadata={"user_id": "123"},
            thinking={"type": "enabled"},
        )

        assert params.max_tokens == 1024
        assert params.system == "You are helpful."
        assert params.stop_sequences == ["STOP"]
        assert params.temperature == 0.7
        assert params.top_p == 0.9
        assert params.top_k == 40
        assert params.tools is not None
        assert params.tool_choice == {"type": "auto"}
        assert params.metadata == {"user_id": "123"}
        assert params.thinking == {"type": "enabled"}

    def test_system_as_list(self) -> None:
        """Test system prompt as list of blocks."""
        params = BatchRequestParams(
            model="claude-sonnet-4-5",
            messages=[],
            system=[{"type": "text", "text": "System prompt"}],
        )

        assert isinstance(params.system, list)


class TestBatchRequest:
    """Test BatchRequest model."""

    def test_valid_request(self) -> None:
        """Test creating valid BatchRequest."""
        request = BatchRequest(
            custom_id="my-request-1",
            params=BatchRequestParams(
                model="claude-sonnet-4-5",
                messages=[{"role": "user", "content": "Hello"}],
            ),
        )

        assert request.custom_id == "my-request-1"
        assert request.params.model == "claude-sonnet-4-5"

    def test_custom_id_min_length(self) -> None:
        """Test custom_id minimum length validation."""
        with pytest.raises(ValidationError) as exc_info:
            BatchRequest(
                custom_id="",  # empty string
                params=BatchRequestParams(
                    model="claude-sonnet-4-5",
                    messages=[],
                ),
            )
        assert "custom_id" in str(exc_info.value).lower() or "string" in str(exc_info.value).lower()

    def test_custom_id_max_length(self) -> None:
        """Test custom_id maximum length validation."""
        with pytest.raises(ValidationError) as exc_info:
            BatchRequest(
                custom_id="x" * 65,  # 65 chars, max is 64
                params=BatchRequestParams(
                    model="claude-sonnet-4-5",
                    messages=[],
                ),
            )
        assert "custom_id" in str(exc_info.value).lower() or "string" in str(exc_info.value).lower()

    def test_custom_id_exact_max_length(self) -> None:
        """Test custom_id at exactly max length."""
        request = BatchRequest(
            custom_id="x" * 64,  # exactly 64 chars
            params=BatchRequestParams(
                model="claude-sonnet-4-5",
                messages=[],
            ),
        )
        assert len(request.custom_id) == 64


class TestCreateBatchRequest:
    """Test CreateBatchRequest model."""

    def test_valid_request(self) -> None:
        """Test creating valid CreateBatchRequest."""
        request = CreateBatchRequest(
            requests=[
                BatchRequest(
                    custom_id="req1",
                    params=BatchRequestParams(
                        model="claude-sonnet-4-5",
                        messages=[{"role": "user", "content": "Hello"}],
                    ),
                )
            ]
        )

        assert len(request.requests) == 1

    def test_requests_min_length(self) -> None:
        """Test requests minimum length validation."""
        with pytest.raises(ValidationError):
            CreateBatchRequest(requests=[])  # empty list

    def test_requests_max_length(self) -> None:
        """Test requests maximum length validation."""
        requests = [
            BatchRequest(
                custom_id=f"req{i}",
                params=BatchRequestParams(
                    model="claude-sonnet-4-5",
                    messages=[],
                ),
            )
            for i in range(101)  # 101 requests, max is 100
        ]

        with pytest.raises(ValidationError):
            CreateBatchRequest(requests=requests)

    def test_requests_at_max(self) -> None:
        """Test requests at exactly max length."""
        requests = [
            BatchRequest(
                custom_id=f"req{i}",
                params=BatchRequestParams(
                    model="claude-sonnet-4-5",
                    messages=[],
                ),
            )
            for i in range(100)  # exactly 100 requests
        ]

        batch = CreateBatchRequest(requests=requests)
        assert len(batch.requests) == 100


class TestRequestCounts:
    """Test RequestCounts model."""

    def test_default_values(self) -> None:
        """Test all default values are 0."""
        counts = RequestCounts()

        assert counts.processing == 0
        assert counts.succeeded == 0
        assert counts.errored == 0
        assert counts.canceled == 0
        assert counts.expired == 0

    def test_all_fields(self) -> None:
        """Test setting all fields."""
        counts = RequestCounts(
            processing=5,
            succeeded=10,
            errored=2,
            canceled=1,
            expired=0,
        )

        assert counts.processing == 5
        assert counts.succeeded == 10
        assert counts.errored == 2
        assert counts.canceled == 1
        assert counts.expired == 0

    def test_model_dump(self) -> None:
        """Test model serialization."""
        counts = RequestCounts(succeeded=5, errored=1)
        data = counts.model_dump()

        assert data["succeeded"] == 5
        assert data["errored"] == 1
        assert data["processing"] == 0


class TestMessageBatch:
    """Test MessageBatch model."""

    def test_minimal_batch(self) -> None:
        """Test creating batch with minimal fields."""
        batch = MessageBatch(
            id="msgbatch_abc123",
            processing_status="in_progress",
            request_counts=RequestCounts(processing=5),
            created_at="2024-01-15T12:00:00Z",
            expires_at="2024-02-13T12:00:00Z",
        )

        assert batch.id == "msgbatch_abc123"
        assert batch.type == "message_batch"
        assert batch.processing_status == "in_progress"
        assert batch.ended_at is None
        assert batch.archived_at is None
        assert batch.cancel_initiated_at is None
        assert batch.results_url is None

    def test_all_fields(self) -> None:
        """Test batch with all fields."""
        batch = MessageBatch(
            id="msgbatch_xyz789",
            processing_status="ended",
            request_counts=RequestCounts(succeeded=10),
            created_at="2024-01-15T12:00:00Z",
            expires_at="2024-02-13T12:00:00Z",
            ended_at="2024-01-15T12:05:00Z",
            archived_at="2024-01-20T12:00:00Z",
            cancel_initiated_at="2024-01-15T12:02:00Z",
            results_url="https://example.com/results",
        )

        assert batch.ended_at == "2024-01-15T12:05:00Z"
        assert batch.archived_at == "2024-01-20T12:00:00Z"
        assert batch.cancel_initiated_at == "2024-01-15T12:02:00Z"
        assert batch.results_url == "https://example.com/results"

    def test_processing_status_values(self) -> None:
        """Test valid processing status values."""
        for status in ["in_progress", "canceling", "ended"]:
            batch = MessageBatch(
                id="msgbatch_test",
                processing_status=status,  # type: ignore[arg-type]
                request_counts=RequestCounts(),
                created_at="2024-01-15T12:00:00Z",
                expires_at="2024-02-13T12:00:00Z",
            )
            assert batch.processing_status == status

    def test_default_type(self) -> None:
        """Test default type is 'message_batch'."""
        batch = MessageBatch(
            id="msgbatch_test",
            processing_status="in_progress",
            request_counts=RequestCounts(),
            created_at="2024-01-15T12:00:00Z",
            expires_at="2024-02-13T12:00:00Z",
        )
        assert batch.type == "message_batch"


class TestMessageBatchDeletedResponse:
    """Test MessageBatchDeletedResponse model."""

    def test_create_response(self) -> None:
        """Test creating deleted response."""
        response = MessageBatchDeletedResponse(id="msgbatch_deleted")

        assert response.id == "msgbatch_deleted"
        assert response.type == "message_batch_deleted"

    def test_default_type(self) -> None:
        """Test default type."""
        response = MessageBatchDeletedResponse(id="msgbatch_xyz")
        assert response.type == "message_batch_deleted"

    def test_model_dump(self) -> None:
        """Test model serialization."""
        response = MessageBatchDeletedResponse(id="msgbatch_123")
        data = response.model_dump()

        assert data["id"] == "msgbatch_123"
        assert data["type"] == "message_batch_deleted"


class TestBatchesListResponse:
    """Test BatchesListResponse model."""

    def test_empty_list(self) -> None:
        """Test response with empty list."""
        response = BatchesListResponse(data=[])

        assert response.data == []
        assert response.first_id is None
        assert response.last_id is None
        assert response.has_more is False

    def test_with_batches(self) -> None:
        """Test response with batches."""
        batches = [
            MessageBatch(
                id="msgbatch_1",
                processing_status="ended",
                request_counts=RequestCounts(succeeded=5),
                created_at="2024-01-15T12:00:00Z",
                expires_at="2024-02-13T12:00:00Z",
            ),
            MessageBatch(
                id="msgbatch_2",
                processing_status="in_progress",
                request_counts=RequestCounts(processing=3),
                created_at="2024-01-15T12:01:00Z",
                expires_at="2024-02-13T12:01:00Z",
            ),
        ]

        response = BatchesListResponse(
            data=batches,
            first_id="msgbatch_1",
            last_id="msgbatch_2",
            has_more=True,
        )

        assert len(response.data) == 2
        assert response.first_id == "msgbatch_1"
        assert response.last_id == "msgbatch_2"
        assert response.has_more is True

    def test_default_has_more(self) -> None:
        """Test default has_more is False."""
        response = BatchesListResponse(data=[])
        assert response.has_more is False


class TestResultTypes:
    """Test batch result type models."""

    def test_succeeded_result(self) -> None:
        """Test SucceededResult model."""
        result = SucceededResult(
            message={
                "id": "msg_123",
                "content": [{"type": "text", "text": "Hello!"}],
                "role": "assistant",
            }
        )

        assert result.type == "succeeded"
        assert result.message["id"] == "msg_123"

    def test_errored_result(self) -> None:
        """Test ErroredResult model."""
        result = ErroredResult(
            error={
                "type": "api_error",
                "message": "Request failed",
            }
        )

        assert result.type == "errored"
        assert result.error["type"] == "api_error"

    def test_canceled_result(self) -> None:
        """Test CanceledResult model."""
        result = CanceledResult()

        assert result.type == "canceled"

    def test_expired_result(self) -> None:
        """Test ExpiredResult model."""
        result = ExpiredResult()

        assert result.type == "expired"

    def test_succeeded_result_model_dump(self) -> None:
        """Test SucceededResult serialization."""
        result = SucceededResult(message={"id": "msg_abc"})
        data = result.model_dump()

        assert data["type"] == "succeeded"
        assert data["message"]["id"] == "msg_abc"

    def test_errored_result_model_dump(self) -> None:
        """Test ErroredResult serialization."""
        result = ErroredResult(error={"type": "error", "message": "Failed"})
        data = result.model_dump()

        assert data["type"] == "errored"
        assert data["error"]["type"] == "error"


class TestBatchResultLine:
    """Test BatchResultLine model."""

    def test_with_succeeded_result(self) -> None:
        """Test result line with succeeded result."""
        line = BatchResultLine(
            custom_id="req-1",
            result=SucceededResult(message={"id": "msg_123"}),
        )

        assert line.custom_id == "req-1"
        assert line.result.type == "succeeded"

    def test_with_errored_result(self) -> None:
        """Test result line with errored result."""
        line = BatchResultLine(
            custom_id="req-2",
            result=ErroredResult(error={"type": "api_error"}),
        )

        assert line.custom_id == "req-2"
        assert line.result.type == "errored"

    def test_with_canceled_result(self) -> None:
        """Test result line with canceled result."""
        line = BatchResultLine(
            custom_id="req-3",
            result=CanceledResult(),
        )

        assert line.custom_id == "req-3"
        assert line.result.type == "canceled"

    def test_with_expired_result(self) -> None:
        """Test result line with expired result."""
        line = BatchResultLine(
            custom_id="req-4",
            result=ExpiredResult(),
        )

        assert line.custom_id == "req-4"
        assert line.result.type == "expired"

    def test_model_dump(self) -> None:
        """Test model serialization for JSONL output."""
        line = BatchResultLine(
            custom_id="my-request",
            result=SucceededResult(message={"id": "msg_xyz", "content": []}),
        )

        data = line.model_dump()
        assert data["custom_id"] == "my-request"
        assert data["result"]["type"] == "succeeded"
        assert "message" in data["result"]

    def test_required_fields(self) -> None:
        """Test required fields."""
        with pytest.raises(ValidationError):
            BatchResultLine(custom_id="test")  # type: ignore[call-arg]  # missing result

        with pytest.raises(ValidationError):
            BatchResultLine(result=CanceledResult())  # type: ignore[call-arg]  # missing custom_id
