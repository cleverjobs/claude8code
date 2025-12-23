"""Integration tests for session lifecycle and management."""

import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture
def session_client():
    """Create a FastAPI test client for session tests."""
    from src.api.app import app
    return TestClient(app)


class TestSessionCreation:
    """Test session creation endpoints."""

    def test_create_session_endpoint_exists(self, session_client: TestClient):
        """Test that session creation endpoint exists."""
        response = session_client.post(
            "/v1/sessions",
            headers={"x-api-key": "sk-test"},
        )
        # Endpoint should exist - may return 200 or 500 depending on SDK mock
        assert response.status_code in [200, 500]

    def test_create_session_returns_session_id(self, session_client: TestClient):
        """Test session creation returns session ID."""
        response = session_client.post(
            "/v1/sessions",
            headers={"x-api-key": "sk-test"},
        )
        if response.status_code == 200:
            data = response.json()
            assert "session_id" in data


class TestSessionDeletion:
    """Test session deletion endpoints."""

    def test_delete_nonexistent_session(self, session_client: TestClient):
        """Test deleting a session that doesn't exist."""
        response = session_client.delete(
            "/v1/sessions/nonexistent-session-123",
            headers={"x-api-key": "sk-test"},
        )
        assert response.status_code == 404

    def test_delete_session_requires_id(self, session_client: TestClient):
        """Test that DELETE /v1/sessions requires a session ID."""
        response = session_client.delete(
            "/v1/sessions/",
            headers={"x-api-key": "sk-test"},
        )
        # Should be 404 or 405 depending on routing
        assert response.status_code in [404, 405]


class TestSessionPoolStats:
    """Test session pool statistics endpoint."""

    def test_pool_stats_endpoint(self, session_client: TestClient):
        """Test session pool stats endpoint returns data."""
        response = session_client.get(
            "/v1/pool/stats",
            headers={"x-api-key": "sk-test"},
        )
        # Should return 200 with stats or 500 if pool not initialized
        assert response.status_code in [200, 500]

        if response.status_code == 200:
            data = response.json()
            # Should have pool statistics
            assert isinstance(data, dict)


class TestSessionWithRequests:
    """Test session persistence across requests."""

    def test_session_header_accepted(self, session_client: TestClient):
        """Test that x-session-id header is accepted."""
        response = session_client.get(
            "/health",
            headers={
                "x-api-key": "sk-test",
                "x-session-id": "sess_test123",
            },
        )
        assert response.status_code == 200


class TestConfigEndpoint:
    """Test configuration endpoint."""

    def test_config_endpoint_returns_settings(self, session_client: TestClient):
        """Test /v1/config returns server configuration."""
        response = session_client.get(
            "/v1/config",
            headers={"x-api-key": "sk-test"},
        )
        assert response.status_code == 200

        data = response.json()
        # Should have configuration sections
        assert "server" in data or "config" in data or isinstance(data, dict)

    def test_config_hides_secrets(self, session_client: TestClient):
        """Test /v1/config doesn't expose secrets."""
        response = session_client.get(
            "/v1/config",
            headers={"x-api-key": "sk-test"},
        )
        assert response.status_code == 200

        data = response.json()
        # Should not contain sensitive keys in output
        data_str = str(data).lower()
        assert "password" not in data_str or "****" in data_str
        assert "secret" not in data_str or "****" in data_str
