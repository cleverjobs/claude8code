"""Unit tests for API routes module."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.api.routes import MODEL_ALIASES, MODEL_METADATA


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestHealthEndpoint:
    """Test health endpoint."""

    def test_health_returns_healthy(self, client: TestClient) -> None:
        """Test health endpoint returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_sdk_health_returns_mode(self, client: TestClient) -> None:
        """Test SDK health endpoint returns mode field."""
        response = client.get("/sdk/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["mode"] == "sdk"


class TestModelsEndpoint:
    """Test models listing endpoint."""

    def test_list_models_returns_data(self, client: TestClient) -> None:
        """Test listing models returns data array."""
        response = client.get("/v1/models", headers={"x-api-key": "test"})
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_list_models_includes_metadata(self, client: TestClient) -> None:
        """Test that models include expected metadata."""
        response = client.get("/v1/models", headers={"x-api-key": "test"})
        data = response.json()

        for model in data["data"]:
            assert "id" in model
            assert "type" in model
            assert model["type"] == "model"

    def test_list_models_respects_limit(self, client: TestClient) -> None:
        """Test that limit parameter works."""
        response = client.get("/v1/models?limit=2", headers={"x-api-key": "test"})
        data = response.json()
        assert len(data["data"]) <= 2

    def test_list_models_with_after_id(self, client: TestClient) -> None:
        """Test pagination with after_id."""
        # Get all models first
        response = client.get("/v1/models", headers={"x-api-key": "test"})
        all_models = response.json()["data"]
        if len(all_models) >= 2:
            first_id = all_models[0]["id"]
            response = client.get(f"/v1/models?after_id={first_id}", headers={"x-api-key": "test"})
            assert response.status_code == 200
            data = response.json()
            # Should not include the first model
            assert first_id not in [m["id"] for m in data["data"]]

    def test_list_models_with_before_id(self, client: TestClient) -> None:
        """Test pagination with before_id."""
        response = client.get("/v1/models", headers={"x-api-key": "test"})
        all_models = response.json()["data"]
        if len(all_models) >= 2:
            last_id = all_models[-1]["id"]
            response = client.get(f"/v1/models?before_id={last_id}", headers={"x-api-key": "test"})
            assert response.status_code == 200
            data = response.json()
            # Should not include the last model
            assert last_id not in [m["id"] for m in data["data"]]

    def test_list_models_with_version_header(self, client: TestClient) -> None:
        """Test that anthropic-version header is accepted."""
        response = client.get(
            "/v1/models",
            headers={"x-api-key": "test", "anthropic-version": "2024-01-01"},
        )
        assert response.status_code == 200

    def test_list_models_with_beta_header(self, client: TestClient) -> None:
        """Test that anthropic-beta header is accepted."""
        response = client.get(
            "/v1/models",
            headers={"x-api-key": "test", "anthropic-beta": "max-tokens-3-5-sonnet-2024-07-15"},
        )
        assert response.status_code == 200


class TestGetModelEndpoint:
    """Test get single model endpoint."""

    def test_get_model_success(self, client: TestClient) -> None:
        """Test getting a specific model."""
        model_id = "claude-opus-4-5-20251101"
        response = client.get(f"/v1/models/{model_id}", headers={"x-api-key": "test"})
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == model_id
        assert "display_name" in data

    def test_get_model_not_found(self, client: TestClient) -> None:
        """Test getting a non-existent model."""
        response = client.get("/v1/models/nonexistent-model", headers={"x-api-key": "test"})
        assert response.status_code == 404

    def test_get_model_with_alias(self, client: TestClient) -> None:
        """Test getting a model using alias."""
        alias = "claude-opus-4-5"
        resolved_id = MODEL_ALIASES[alias]
        response = client.get(f"/v1/models/{alias}", headers={"x-api-key": "test"})
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == resolved_id

    def test_get_model_with_headers(self, client: TestClient) -> None:
        """Test get model with version headers."""
        response = client.get(
            "/v1/models/claude-opus-4-5-20251101",
            headers={
                "x-api-key": "test",
                "anthropic-version": "2024-01-01",
                "anthropic-beta": "test-beta",
            },
        )
        assert response.status_code == 200


class TestModelMetadata:
    """Test model metadata."""

    def test_metadata_has_expected_models(self) -> None:
        """Test MODEL_METADATA contains expected models."""
        assert "claude-opus-4-5-20251101" in MODEL_METADATA
        assert "claude-sonnet-4-5-20250514" in MODEL_METADATA
        assert "claude-haiku-4-5-20251001" in MODEL_METADATA

    def test_metadata_structure(self) -> None:
        """Test metadata has expected structure."""
        for model_id, metadata in MODEL_METADATA.items():
            assert "display_name" in metadata
            assert "created_at" in metadata


class TestMessagesEndpoint:
    """Test messages endpoint."""

    def test_messages_requires_api_key(self, client: TestClient) -> None:
        """Test messages endpoint requires API key."""
        response = client.post("/v1/messages", json={"messages": []})
        # Should return 401 or proceed depending on security config
        assert response.status_code in [401, 422]

    def test_messages_validates_request(self, client: TestClient) -> None:
        """Test messages validates request body."""
        response = client.post(
            "/v1/messages",
            json={},  # Missing required fields
            headers={"x-api-key": "test"},
        )
        assert response.status_code == 422

    def test_messages_requires_model(self, client: TestClient) -> None:
        """Test messages requires model field."""
        response = client.post(
            "/v1/messages",
            json={"messages": [{"role": "user", "content": "Hello"}]},
            headers={"x-api-key": "test"},
        )
        assert response.status_code == 422

    def test_messages_with_value_error(self, client: TestClient) -> None:
        """Test messages handles ValueError."""
        with patch("src.api.routes.process_request", side_effect=ValueError("Bad input")):
            response = client.post(
                "/v1/messages",
                json={
                    "model": "claude-sonnet-4-5-20250514",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "Hello"}],
                },
                headers={"x-api-key": "test"},
            )
            assert response.status_code == 400

    def test_messages_with_permission_error(self, client: TestClient) -> None:
        """Test messages handles PermissionError."""
        with patch("src.api.routes.process_request", side_effect=PermissionError("Access denied")):
            response = client.post(
                "/v1/messages",
                json={
                    "model": "claude-sonnet-4-5-20250514",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "Hello"}],
                },
                headers={"x-api-key": "test"},
            )
            assert response.status_code == 403

    def test_messages_with_generic_error(self, client: TestClient) -> None:
        """Test messages handles generic exceptions."""
        with patch("src.api.routes.process_request", side_effect=RuntimeError("Internal error")):
            response = client.post(
                "/v1/messages",
                json={
                    "model": "claude-sonnet-4-5-20250514",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "Hello"}],
                },
                headers={"x-api-key": "test"},
            )
            assert response.status_code == 500

    def test_messages_with_headers(self, client: TestClient) -> None:
        """Test messages accepts version headers."""
        with patch(
            "src.api.routes.process_request", return_value={"type": "message", "content": []}
        ):
            response = client.post(
                "/v1/messages",
                json={
                    "model": "claude-sonnet-4-5-20250514",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "Hello"}],
                },
                headers={
                    "x-api-key": "test",
                    "anthropic-version": "2024-01-01",
                    "anthropic-beta": "test-beta",
                },
            )
            assert response.status_code == 200


class TestSessionsEndpoint:
    """Test sessions endpoint."""

    def test_create_session(self, client: TestClient) -> None:
        """Test creating a session."""
        with patch("src.api.routes.session_manager") as mock_manager:
            mock_manager.get_or_create_session = AsyncMock(
                return_value=("session_123", MagicMock())
            )

            response = client.post(
                "/v1/sessions",
                headers={"x-api-key": "test"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "session_id" in data

    def test_delete_session_success(self, client: TestClient) -> None:
        """Test deleting a session."""
        with patch("src.api.routes.session_manager") as mock_manager:
            mock_manager.close_session = AsyncMock(return_value=True)

            response = client.delete(
                "/v1/sessions/session_123",
                headers={"x-api-key": "test"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "closed"

    def test_delete_session_not_found(self, client: TestClient) -> None:
        """Test deleting non-existent session."""
        with patch("src.api.routes.session_manager") as mock_manager:
            mock_manager.close_session = AsyncMock(return_value=False)

            response = client.delete(
                "/v1/sessions/nonexistent",
                headers={"x-api-key": "test"},
            )
            assert response.status_code == 404


class TestCountTokensEndpoint:
    """Test count tokens endpoint."""

    def test_count_tokens_basic(self, client: TestClient) -> None:
        """Test counting tokens for basic request."""
        with patch("src.api.routes.count_request_tokens", return_value=10):
            response = client.post(
                "/v1/messages/count_tokens",
                json={
                    "model": "claude-sonnet-4-5-20250514",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
                headers={"x-api-key": "test"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "input_tokens" in data

    def test_count_tokens_with_system(self, client: TestClient) -> None:
        """Test counting tokens with system prompt."""
        with patch("src.api.routes.count_request_tokens", return_value=25):
            response = client.post(
                "/v1/messages/count_tokens",
                json={
                    "model": "claude-sonnet-4-5-20250514",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "system": "You are helpful",
                },
                headers={"x-api-key": "test"},
            )
            assert response.status_code == 200


class TestConfigEndpoint:
    """Test configuration endpoint."""

    def test_get_config(self, client: TestClient) -> None:
        """Test getting server configuration."""
        response = client.get("/v1/config", headers={"x-api-key": "test"})
        assert response.status_code == 200
        data = response.json()

        # Check expected fields
        assert "default_model" in data
        assert "max_turns" in data


class TestMetricsEndpoint:
    """Test metrics endpoint."""

    def test_metrics_returns_text(self, client: TestClient) -> None:
        """Test metrics endpoint returns text."""
        response = client.get("/metrics")
        assert response.status_code == 200
        # Should return prometheus-style metrics
        assert "text" in response.headers.get("content-type", "")


class TestPoolStatsEndpoint:
    """Test pool stats endpoint."""

    def test_pool_stats(self, client: TestClient) -> None:
        """Test getting pool statistics."""
        with patch("src.api.routes.get_pool") as mock_get_pool:
            mock_pool = MagicMock()
            mock_pool.get_stats = AsyncMock(
                return_value={
                    "max_sessions": 10,
                    "total_sessions": 2,
                    "active_sessions": 1,
                }
            )
            mock_get_pool.return_value = mock_pool

            response = client.get("/v1/pool/stats", headers={"x-api-key": "test"})
            assert response.status_code == 200


class TestBatchesEndpoints:
    """Test batches endpoints."""

    def test_list_batches(self, client: TestClient) -> None:
        """Test listing batches."""
        with patch("src.api.routes.get_batch_processor") as mock_get:
            mock_processor = MagicMock()
            mock_processor.list_batches = AsyncMock(return_value=([], False))
            mock_get.return_value = mock_processor

            response = client.get("/v1/messages/batches", headers={"x-api-key": "test"})
            assert response.status_code == 200
            data = response.json()
            assert "data" in data

    def test_list_batches_with_headers(self, client: TestClient) -> None:
        """Test listing batches with version headers."""
        with patch("src.api.routes.get_batch_processor") as mock_get:
            mock_processor = MagicMock()
            mock_processor.list_batches = AsyncMock(return_value=([], False))
            mock_get.return_value = mock_processor

            response = client.get(
                "/v1/messages/batches",
                headers={
                    "x-api-key": "test",
                    "anthropic-version": "2024-01-01",
                    "anthropic-beta": "message-batches-2024-09-24",
                },
            )
            assert response.status_code == 200

    def test_create_batch_validation(self, client: TestClient) -> None:
        """Test batch creation validates input."""
        response = client.post(
            "/v1/messages/batches",
            json={},  # Missing required fields
            headers={"x-api-key": "test"},
        )
        assert response.status_code == 422

    def test_get_batch_not_found(self, client: TestClient) -> None:
        """Test getting non-existent batch."""
        with patch("src.api.routes.get_batch_processor") as mock_get:
            mock_processor = MagicMock()
            mock_processor.get_batch = AsyncMock(return_value=None)
            mock_get.return_value = mock_processor

            response = client.get("/v1/messages/batches/batch_123", headers={"x-api-key": "test"})
            assert response.status_code == 404

    def test_get_batch_success(self, client: TestClient) -> None:
        """Test getting a batch."""
        mock_batch = MagicMock()
        mock_batch.id = "batch_123"
        mock_batch.model_dump = MagicMock(return_value={"id": "batch_123"})
        with patch("src.api.routes.get_batch_processor") as mock_get:
            mock_processor = MagicMock()
            mock_processor.get_batch = AsyncMock(return_value=mock_batch)
            mock_get.return_value = mock_processor

            response = client.get(
                "/v1/messages/batches/batch_123",
                headers={"x-api-key": "test", "anthropic-version": "2024-01-01"},
            )
            assert response.status_code == 200

    def test_cancel_batch_not_found(self, client: TestClient) -> None:
        """Test canceling non-existent batch."""
        with patch("src.api.routes.get_batch_processor") as mock_get:
            mock_processor = MagicMock()
            mock_processor.cancel_batch = AsyncMock(return_value=None)
            mock_get.return_value = mock_processor

            response = client.post(
                "/v1/messages/batches/batch_123/cancel", headers={"x-api-key": "test"}
            )
            assert response.status_code == 404

    def test_cancel_batch_success(self, client: TestClient) -> None:
        """Test canceling a batch."""
        mock_batch = MagicMock()
        mock_batch.id = "batch_123"
        mock_batch.model_dump = MagicMock(return_value={"id": "batch_123"})
        with patch("src.api.routes.get_batch_processor") as mock_get:
            mock_processor = MagicMock()
            mock_processor.cancel_batch = AsyncMock(return_value=mock_batch)
            mock_get.return_value = mock_processor

            response = client.post(
                "/v1/messages/batches/batch_123/cancel",
                headers={"x-api-key": "test", "anthropic-beta": "message-batches-2024-09-24"},
            )
            assert response.status_code == 200

    def test_get_batch_results_success(self, client: TestClient) -> None:
        """Test getting batch results."""
        with patch("src.api.routes.get_batch_processor") as mock_get:
            mock_processor = MagicMock()
            mock_processor.get_batch_results = AsyncMock(return_value=[])
            mock_get.return_value = mock_processor

            response = client.get(
                "/v1/messages/batches/batch_123/results",
                headers={"x-api-key": "test", "anthropic-version": "2024-01-01"},
            )
            # Returns 200 with empty results (not 404)
            assert response.status_code == 200

    def test_batch_processor_not_available(self, client: TestClient) -> None:
        """Test when batch processor is not available."""
        with patch("src.api.routes.get_batch_processor", return_value=None):
            response = client.get("/v1/messages/batches", headers={"x-api-key": "test"})
            assert response.status_code == 503

    def test_create_batch_success(self, client: TestClient) -> None:
        """Test creating a batch."""
        mock_batch = MagicMock()
        mock_batch.id = "batch_new"
        mock_batch.model_dump = MagicMock(return_value={"id": "batch_new"})
        with patch("src.api.routes.get_batch_processor") as mock_get:
            mock_processor = MagicMock()
            mock_processor.create_batch = AsyncMock(return_value=mock_batch)
            mock_get.return_value = mock_processor

            response = client.post(
                "/v1/messages/batches",
                json={
                    "requests": [
                        {
                            "custom_id": "req1",
                            "params": {
                                "model": "claude-sonnet-4-5-20250514",
                                "max_tokens": 100,
                                "messages": [{"role": "user", "content": "Hello"}],
                            },
                        }
                    ]
                },
                headers={"x-api-key": "test", "anthropic-beta": "message-batches-2024-09-24"},
            )
            assert response.status_code == 200

    def test_create_batch_invalid_request(self, client: TestClient) -> None:
        """Test creating a batch with invalid request."""
        with patch("src.api.routes.get_batch_processor") as mock_get:
            mock_processor = MagicMock()
            mock_processor.create_batch = AsyncMock(side_effect=ValueError("Invalid batch"))
            mock_get.return_value = mock_processor

            response = client.post(
                "/v1/messages/batches",
                json={
                    "requests": [
                        {
                            "custom_id": "req1",
                            "params": {
                                "model": "claude-sonnet-4-5-20250514",
                                "max_tokens": 100,
                                "messages": [{"role": "user", "content": "Hello"}],
                            },
                        }
                    ]
                },
                headers={"x-api-key": "test"},
            )
            assert response.status_code == 400

    def test_create_batch_error(self, client: TestClient) -> None:
        """Test creating a batch with generic error."""
        with patch("src.api.routes.get_batch_processor") as mock_get:
            mock_processor = MagicMock()
            mock_processor.create_batch = AsyncMock(side_effect=RuntimeError("Batch failed"))
            mock_get.return_value = mock_processor

            response = client.post(
                "/v1/messages/batches",
                json={
                    "requests": [
                        {
                            "custom_id": "req1",
                            "params": {
                                "model": "claude-sonnet-4-5-20250514",
                                "max_tokens": 100,
                                "messages": [{"role": "user", "content": "Hello"}],
                            },
                        }
                    ]
                },
                headers={"x-api-key": "test"},
            )
            assert response.status_code == 500


class TestFilesEndpoints:
    """Test files endpoints."""

    def test_list_files(self, client: TestClient) -> None:
        """Test listing files."""
        with patch("src.api.routes.get_file_store") as mock_get:
            mock_store = MagicMock()
            mock_store.list = AsyncMock(return_value=([], False))
            mock_get.return_value = mock_store

            response = client.get("/v1/files", headers={"x-api-key": "test"})
            assert response.status_code == 200
            data = response.json()
            assert "data" in data

    def test_list_files_with_headers(self, client: TestClient) -> None:
        """Test listing files with version headers."""
        with patch("src.api.routes.get_file_store") as mock_get:
            mock_store = MagicMock()
            mock_store.list = AsyncMock(return_value=([], False))
            mock_get.return_value = mock_store

            response = client.get(
                "/v1/files",
                headers={
                    "x-api-key": "test",
                    "anthropic-version": "2024-01-01",
                    "anthropic-beta": "files-api-2025-04-14",
                },
            )
            assert response.status_code == 200

    def test_get_file_not_found(self, client: TestClient) -> None:
        """Test getting non-existent file."""
        with patch("src.api.routes.get_file_store") as mock_get:
            mock_store = MagicMock()
            mock_store.get = AsyncMock(return_value=None)
            mock_get.return_value = mock_store

            response = client.get("/v1/files/file_123", headers={"x-api-key": "test"})
            assert response.status_code == 404

    def test_get_file_success(self, client: TestClient) -> None:
        """Test getting file metadata."""
        mock_file = MagicMock()
        mock_file.id = "file_123"
        mock_file.filename = "test.txt"
        mock_file.model_dump = MagicMock(return_value={"id": "file_123", "filename": "test.txt"})
        with patch("src.api.routes.get_file_store") as mock_get:
            mock_store = MagicMock()
            mock_store.get = AsyncMock(return_value=mock_file)
            mock_get.return_value = mock_store

            response = client.get(
                "/v1/files/file_123",
                headers={"x-api-key": "test", "anthropic-version": "2024-01-01"},
            )
            assert response.status_code == 200

    def test_get_file_content_not_found(self, client: TestClient) -> None:
        """Test getting content for non-existent file."""
        with patch("src.api.routes.get_file_store") as mock_get:
            mock_store = MagicMock()
            mock_store.get_content = AsyncMock(return_value=None)
            mock_get.return_value = mock_store

            response = client.get("/v1/files/file_123/content", headers={"x-api-key": "test"})
            assert response.status_code == 404

    def test_get_file_content_success(self, client: TestClient) -> None:
        """Test getting file content."""
        with patch("src.api.routes.get_file_store") as mock_get:
            mock_store = MagicMock()
            # Returns (content, filename, mime_type)
            mock_store.get_content = AsyncMock(
                return_value=(b"test content", "test.txt", "text/plain")
            )
            mock_get.return_value = mock_store

            response = client.get(
                "/v1/files/file_123/content",
                headers={"x-api-key": "test", "anthropic-beta": "files-api-2025-04-14"},
            )
            assert response.status_code == 200
            assert response.content == b"test content"

    def test_file_store_not_available(self, client: TestClient) -> None:
        """Test when file store is not available."""
        with patch("src.api.routes.get_file_store", return_value=None):
            response = client.get("/v1/files", headers={"x-api-key": "test"})
            assert response.status_code == 503

    def test_delete_file_success(self, client: TestClient) -> None:
        """Test deleting a file."""
        with patch("src.api.routes.get_file_store") as mock_get:
            mock_store = MagicMock()
            mock_store.delete = AsyncMock(return_value=True)
            mock_get.return_value = mock_store

            response = client.delete(
                "/v1/files/file_123",
                headers={"x-api-key": "test", "anthropic-version": "2024-01-01"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "file_123"

    def test_delete_file_not_found(self, client: TestClient) -> None:
        """Test deleting non-existent file."""
        with patch("src.api.routes.get_file_store") as mock_get:
            mock_store = MagicMock()
            mock_store.delete = AsyncMock(return_value=False)
            mock_get.return_value = mock_store

            response = client.delete(
                "/v1/files/nonexistent",
                headers={"x-api-key": "test"},
            )
            assert response.status_code == 404

    def test_upload_file_success(self, client: TestClient) -> None:
        """Test uploading a file."""
        import io

        mock_metadata = MagicMock()
        mock_metadata.id = "file_123"
        mock_metadata.model_dump = MagicMock(
            return_value={"id": "file_123", "filename": "test.txt"}
        )
        with patch("src.api.routes.get_file_store") as mock_get:
            mock_store = MagicMock()
            mock_store.upload = AsyncMock(return_value=mock_metadata)
            mock_get.return_value = mock_store

            files = {"file": ("test.txt", io.BytesIO(b"test content"), "text/plain")}
            response = client.post(
                "/v1/files",
                files=files,
                headers={"x-api-key": "test", "anthropic-beta": "files-api-2025-04-14"},
            )
            assert response.status_code == 200

    def test_upload_file_too_large(self, client: TestClient) -> None:
        """Test uploading file that's too large."""
        import io

        with patch("src.api.routes.get_file_store") as mock_get:
            mock_store = MagicMock()
            mock_store.upload = AsyncMock(side_effect=ValueError("File too large"))
            mock_get.return_value = mock_store

            files = {"file": ("test.txt", io.BytesIO(b"content"), "text/plain")}
            response = client.post(
                "/v1/files",
                files=files,
                headers={"x-api-key": "test"},
            )
            assert response.status_code == 413

    def test_upload_file_error(self, client: TestClient) -> None:
        """Test upload file with generic error."""
        import io

        with patch("src.api.routes.get_file_store") as mock_get:
            mock_store = MagicMock()
            mock_store.upload = AsyncMock(side_effect=RuntimeError("Upload failed"))
            mock_get.return_value = mock_store

            files = {"file": ("test.txt", io.BytesIO(b"content"), "text/plain")}
            response = client.post(
                "/v1/files",
                files=files,
                headers={"x-api-key": "test"},
            )
            assert response.status_code == 500


class TestAccessLogEndpoint:
    """Test access log endpoints."""

    def test_access_logs_stats(self, client: TestClient) -> None:
        """Test getting access log stats."""
        with patch("src.api.routes.get_access_log_writer") as mock_get:
            mock_writer = MagicMock()
            mock_writer.get_stats = MagicMock(
                return_value={
                    "total_requests": 100,
                    "queries_pending": 5,
                }
            )
            mock_get.return_value = mock_writer

            response = client.get("/v1/logs/stats", headers={"x-api-key": "test"})
            assert response.status_code == 200

    def test_access_logs_stats_not_available(self, client: TestClient) -> None:
        """Test access log stats when not available."""
        with patch("src.api.routes.get_access_log_writer", return_value=None):
            response = client.get("/v1/logs/stats", headers={"x-api-key": "test"})
            assert response.status_code == 200
            data = response.json()
            assert data["available"] is False
            assert "reason" in data


class TestErrorResponses:
    """Test error response handling."""

    def test_validation_error_format(self, client: TestClient) -> None:
        """Test validation errors return proper format."""
        response = client.post(
            "/v1/messages",
            json={"invalid": "data"},
            headers={"x-api-key": "test"},
        )
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


class TestCountTokensWithHeaders:
    """Test count_tokens endpoint with version headers."""

    def test_count_tokens_with_anthropic_version(self, client: TestClient) -> None:
        """Test count_tokens logs anthropic version header."""
        with patch("src.api.routes.count_request_tokens", return_value=50):
            response = client.post(
                "/v1/messages/count_tokens",
                json={
                    "model": "claude-sonnet-4-5-20250514",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
                headers={
                    "x-api-key": "test",
                    "anthropic-version": "2024-01-01",
                },
            )
            assert response.status_code == 200

    def test_count_tokens_with_anthropic_beta(self, client: TestClient) -> None:
        """Test count_tokens logs anthropic beta header."""
        with patch("src.api.routes.count_request_tokens", return_value=50):
            response = client.post(
                "/v1/messages/count_tokens",
                json={
                    "model": "claude-sonnet-4-5-20250514",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
                headers={
                    "x-api-key": "test",
                    "anthropic-beta": "extended-thinking-2024-12-01",
                },
            )
            assert response.status_code == 200

    def test_count_tokens_with_both_headers(self, client: TestClient) -> None:
        """Test count_tokens with both version headers."""
        with patch("src.api.routes.count_request_tokens", return_value=100):
            response = client.post(
                "/v1/messages/count_tokens",
                json={
                    "model": "claude-sonnet-4-5-20250514",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
                headers={
                    "x-api-key": "test",
                    "anthropic-version": "2024-01-01",
                    "anthropic-beta": "extended-thinking-2024-12-01",
                },
            )
            assert response.status_code == 200

    def test_count_tokens_error_handling(self, client: TestClient) -> None:
        """Test count_tokens handles exceptions."""
        with patch("src.api.routes.count_request_tokens", side_effect=ValueError("Token error")):
            response = client.post(
                "/v1/messages/count_tokens",
                json={
                    "model": "claude-sonnet-4-5-20250514",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
                headers={"x-api-key": "test"},
            )
            assert response.status_code == 500


class TestDeleteBatch:
    """Test delete batch endpoint."""

    def test_delete_batch_success(self, client: TestClient) -> None:
        """Test successfully deleting a batch."""
        with patch("src.api.routes.get_batch_processor") as mock_get:
            mock_processor = MagicMock()
            mock_processor.delete_batch = AsyncMock(return_value=True)
            mock_get.return_value = mock_processor

            response = client.delete(
                "/v1/messages/batches/batch_123",
                headers={"x-api-key": "test"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "batch_123"

    def test_delete_batch_not_found(self, client: TestClient) -> None:
        """Test deleting a batch that doesn't exist."""
        with patch("src.api.routes.get_batch_processor") as mock_get:
            mock_processor = MagicMock()
            mock_processor.delete_batch = AsyncMock(return_value=False)
            mock_get.return_value = mock_processor

            response = client.delete(
                "/v1/messages/batches/nonexistent",
                headers={"x-api-key": "test"},
            )
            assert response.status_code == 404

    def test_delete_batch_with_headers(self, client: TestClient) -> None:
        """Test delete batch with version headers."""
        with patch("src.api.routes.get_batch_processor") as mock_get:
            mock_processor = MagicMock()
            mock_processor.delete_batch = AsyncMock(return_value=True)
            mock_get.return_value = mock_processor

            response = client.delete(
                "/v1/messages/batches/batch_456",
                headers={
                    "x-api-key": "test",
                    "anthropic-version": "2024-01-01",
                    "anthropic-beta": "batches-2024-12-01",
                },
            )
            assert response.status_code == 200

    def test_delete_batch_value_error(self, client: TestClient) -> None:
        """Test delete batch handles ValueError."""
        with patch("src.api.routes.get_batch_processor") as mock_get:
            mock_processor = MagicMock()
            mock_processor.delete_batch = AsyncMock(side_effect=ValueError("Invalid batch"))
            mock_get.return_value = mock_processor

            response = client.delete(
                "/v1/messages/batches/invalid",
                headers={"x-api-key": "test"},
            )
            assert response.status_code == 400


class TestGetBatchResults:
    """Test get batch results endpoint."""

    def test_get_batch_results_with_headers(self, client: TestClient) -> None:
        """Test get batch results with version headers."""
        with patch("src.api.routes.get_batch_processor") as mock_get:
            mock_processor = MagicMock()

            async def result_gen() -> AsyncIterator[str]:
                yield '{"custom_id": "1", "result": {}}'

            mock_processor.get_results = MagicMock(return_value=result_gen())
            mock_get.return_value = mock_processor

            response = client.get(
                "/v1/messages/batches/batch_123/results",
                headers={
                    "x-api-key": "test",
                    "anthropic-version": "2024-01-01",
                    "anthropic-beta": "batches-2024-12-01",
                },
            )
            # Just check we get a response, SSE behavior is complex
            assert response.status_code == 200
