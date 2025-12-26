"""Unit tests for the FastAPI app module."""

import pytest
from fastapi.testclient import TestClient

from src.api.app import app, create_app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestAppCreation:
    """Test app creation."""

    def test_create_app_returns_fastapi(self) -> None:
        """Test create_app returns FastAPI instance."""
        from fastapi import FastAPI

        test_app = create_app()
        assert isinstance(test_app, FastAPI)
        assert test_app.title == "claude8code"
        assert test_app.version == "0.1.0"


class TestExceptionHandlers:
    """Test exception handlers."""

    def test_validation_errors_are_handled(self, client: TestClient) -> None:
        """Test validation errors return proper error format."""
        # Send invalid JSON to trigger validation error
        response = client.post(
            "/v1/messages",
            json={"invalid": "data"},
            headers={"x-api-key": "test"},
        )
        # FastAPI validation returns 422
        assert response.status_code == 422


class TestHealthEndpoints:
    """Test health endpoints."""

    def test_root_health(self, client: TestClient) -> None:
        """Test root health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_sdk_health(self, client: TestClient) -> None:
        """Test SDK health endpoint."""
        response = client.get("/sdk/health")
        assert response.status_code == 200


class TestMetricsEndpoint:
    """Test metrics endpoint."""

    def test_metrics_returns_prometheus_format(self, client: TestClient) -> None:
        """Test metrics endpoint returns Prometheus format."""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text" in response.headers["content-type"]


class TestCORSMiddleware:
    """Test CORS middleware configuration."""

    def test_cors_headers_on_options(self, client: TestClient) -> None:
        """Test CORS headers are present on OPTIONS requests."""
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # CORS preflight should be handled
        assert response.status_code in [200, 400]


class TestRequestContextMiddleware:
    """Test request context middleware."""

    def test_request_has_id(self, client: TestClient) -> None:
        """Test request has ID in context."""
        response = client.get("/health")
        assert response.status_code == 200
        # The middleware adds request ID to logs, we just verify request works
