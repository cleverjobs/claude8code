"""Unit tests for middleware module."""

from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import Response
from starlette.testclient import TestClient

from src.api.app import app
from src.api.middleware import RequestContextMiddleware, RequestLoggingMiddleware


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestRequestContextMiddleware:
    """Test RequestContextMiddleware."""

    def test_adds_request_id_to_response(self, client: TestClient) -> None:
        """Test that request ID is added to response headers."""
        response = client.get("/health")
        assert response.status_code == 200
        # Check both formats
        assert "request-id" in response.headers
        assert "x-request-id" in response.headers

    def test_uses_provided_request_id(self, client: TestClient) -> None:
        """Test that provided request ID is used."""
        custom_id = "custom-request-123"
        response = client.get("/health", headers={"x-request-id": custom_id})
        assert response.status_code == 200
        assert response.headers["x-request-id"] == custom_id

    def test_adds_rate_limit_headers(self, client: TestClient) -> None:
        """Test that rate limit headers are added."""
        response = client.get("/health")
        assert response.status_code == 200
        assert "anthropic-ratelimit-requests-limit" in response.headers
        assert "anthropic-ratelimit-tokens-limit" in response.headers

    def test_handles_session_id_header(self, client: TestClient) -> None:
        """Test that session ID header is processed."""
        response = client.get(
            "/health",
            headers={"x-session-id": "session-123"},
        )
        assert response.status_code == 200

    def test_handles_user_agent(self, client: TestClient) -> None:
        """Test that user agent is processed."""
        response = client.get(
            "/health",
            headers={"user-agent": "test-client/1.0"},
        )
        assert response.status_code == 200


class TestRequestLoggingMiddleware:
    """Test RequestLoggingMiddleware."""

    @pytest.mark.asyncio
    async def test_logs_successful_request(self) -> None:
        """Test logging of successful request."""
        middleware = RequestLoggingMiddleware(app)

        mock_request = MagicMock()
        mock_request.method = "GET"
        mock_url = MagicMock()
        mock_url.path = "/test"
        mock_request.url = mock_url
        mock_headers = MagicMock()
        mock_headers.get = MagicMock(return_value="test-123")
        mock_request.headers = mock_headers

        mock_response = Response(content=b"OK", status_code=200)

        async def mock_call_next(req: Request) -> Response:
            return mock_response

        with patch("src.api.middleware.logger") as mock_logger:
            response = await middleware.dispatch(mock_request, mock_call_next)

            assert response.status_code == 200
            mock_logger.info.assert_called_once()

    @pytest.mark.asyncio
    async def test_logs_error_request(self) -> None:
        """Test logging of request that raises exception."""
        middleware = RequestLoggingMiddleware(app)

        mock_request = MagicMock()
        mock_request.method = "POST"
        mock_url = MagicMock()
        mock_url.path = "/error"
        mock_request.url = mock_url
        mock_headers = MagicMock()
        mock_headers.get = MagicMock(return_value="-")
        mock_request.headers = mock_headers

        async def mock_call_next(req: Request) -> Response:
            raise ValueError("Test error")

        with patch("src.api.middleware.logger") as mock_logger:
            with pytest.raises(ValueError, match="Test error"):
                await middleware.dispatch(mock_request, mock_call_next)

            mock_logger.error.assert_called_once()


class TestMiddlewareIntegration:
    """Integration tests for middleware."""

    def test_middleware_chain(self, client: TestClient) -> None:
        """Test that middleware chain works together."""
        response = client.get(
            "/health",
            headers={
                "x-request-id": "integration-test-123",
                "x-session-id": "session-abc",
                "user-agent": "integration-test",
            },
        )
        assert response.status_code == 200
        assert response.headers["x-request-id"] == "integration-test-123"

    def test_middleware_with_error_response(self, client: TestClient) -> None:
        """Test middleware with error response."""
        response = client.get("/v1/models/nonexistent", headers={"x-api-key": "test"})
        assert response.status_code == 404
        # Middleware should still add headers
        assert "x-request-id" in response.headers

    def test_middleware_handles_exception(self, client: TestClient) -> None:
        """Test middleware handles exceptions from handlers."""
        # This endpoint doesn't exist and should trigger an exception path
        response = client.post("/v1/unknown_endpoint")
        # Should either be 404 or handled by exception middleware
        assert response.status_code in [404, 405, 500]


class TestRequestContextMiddlewareException:
    """Test RequestContextMiddleware exception handling."""

    @pytest.mark.asyncio
    async def test_context_middleware_exception_path(self) -> None:
        """Test middleware sets error on exception."""

        middleware = RequestContextMiddleware(app)

        mock_request = MagicMock()
        mock_request.method = "GET"
        mock_url = MagicMock()
        mock_url.path = "/test"
        mock_request.url = mock_url
        mock_headers = MagicMock()
        mock_headers.get = MagicMock(return_value=None)
        mock_request.headers = mock_headers
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"

        async def mock_call_next(req: Request) -> Response:
            raise ValueError("Test exception from handler")

        with pytest.raises(ValueError, match="Test exception from handler"):
            await middleware.dispatch(mock_request, mock_call_next)
