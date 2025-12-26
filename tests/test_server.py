"""Tests for claude8code server API endpoints."""

from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Test health and info endpoints."""

    def test_root_endpoint(self, client: TestClient) -> None:
        """Test root endpoint returns server info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "claude8code"
        assert data["status"] == "running"
        assert "endpoints" in data

    def test_health_endpoint(self, client: TestClient) -> None:
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data


class TestModelsEndpoint:
    """Test models listing endpoint."""

    def test_list_models(self, client: TestClient) -> None:
        """Test listing available models."""
        response = client.get("/v1/models")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) > 0

        # Check model structure
        model = data["data"][0]
        assert "id" in model
        assert "type" in model
        assert model["type"] == "model"

    def test_models_contains_expected(self, client: TestClient) -> None:
        """Test that expected models are in the list."""
        response = client.get("/v1/models")
        data = response.json()
        model_ids = [m["id"] for m in data["data"]]

        # Check for key models
        assert "claude-sonnet-4-5-20250514" in model_ids
        assert "claude-opus-4-5-20251101" in model_ids


class TestConfigEndpoint:
    """Test configuration endpoint."""

    def test_get_config(self, client: TestClient) -> None:
        """Test getting server configuration."""
        response = client.get("/v1/config")
        assert response.status_code == 200
        data = response.json()

        # Check expected config fields
        assert "default_model" in data
        assert "max_turns" in data
        assert "permission_mode" in data


class TestErrorHandling:
    """Test error handling."""

    def test_not_found(self, client: TestClient) -> None:
        """Test 404 for unknown endpoints."""
        response = client.get("/v1/nonexistent")
        assert response.status_code == 404

    def test_method_not_allowed(self, client: TestClient) -> None:
        """Test 405 for wrong HTTP method."""
        response = client.delete("/v1/models")
        assert response.status_code == 405
