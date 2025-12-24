"""Unit tests for API security module."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

from src.api.security import verify_api_key


class TestVerifyApiKey:
    """Test API key verification."""

    @pytest.mark.asyncio
    async def test_no_auth_key_configured_allows_all(self):
        """Test that requests are allowed when no auth key is configured."""
        with patch("src.api.security.settings") as mock_settings:
            mock_settings.auth_key = None

            # Should not raise
            await verify_api_key(x_api_key=None, authorization=None)
            await verify_api_key(x_api_key="any-key", authorization=None)

    @pytest.mark.asyncio
    async def test_empty_auth_key_allows_all(self):
        """Test that empty auth key allows all requests."""
        with patch("src.api.security.settings") as mock_settings:
            mock_settings.auth_key = ""

            # Should not raise
            await verify_api_key(x_api_key=None, authorization=None)

    @pytest.mark.asyncio
    async def test_valid_x_api_key_header(self):
        """Test valid x-api-key header passes."""
        with patch("src.api.security.settings") as mock_settings:
            mock_settings.auth_key = "secret-key-123"

            # Should not raise
            await verify_api_key(x_api_key="secret-key-123", authorization=None)

    @pytest.mark.asyncio
    async def test_valid_bearer_token(self):
        """Test valid Bearer token passes."""
        with patch("src.api.security.settings") as mock_settings:
            mock_settings.auth_key = "secret-key-123"

            # Should not raise
            await verify_api_key(x_api_key=None, authorization="Bearer secret-key-123")

    @pytest.mark.asyncio
    async def test_bearer_case_insensitive(self):
        """Test Bearer token prefix is case-insensitive."""
        with patch("src.api.security.settings") as mock_settings:
            mock_settings.auth_key = "secret-key-123"

            # Should not raise with different cases
            await verify_api_key(x_api_key=None, authorization="bearer secret-key-123")
            await verify_api_key(x_api_key=None, authorization="BEARER secret-key-123")

    @pytest.mark.asyncio
    async def test_invalid_x_api_key_raises_401(self):
        """Test invalid x-api-key raises 401."""
        with patch("src.api.security.settings") as mock_settings:
            mock_settings.auth_key = "secret-key-123"

            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(x_api_key="wrong-key", authorization=None)

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_bearer_token_raises_401(self):
        """Test invalid Bearer token raises 401."""
        with patch("src.api.security.settings") as mock_settings:
            mock_settings.auth_key = "secret-key-123"

            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(x_api_key=None, authorization="Bearer wrong-key")

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_key_when_required_raises_401(self):
        """Test missing key when auth required raises 401."""
        with patch("src.api.security.settings") as mock_settings:
            mock_settings.auth_key = "secret-key-123"

            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(x_api_key=None, authorization=None)

            assert exc_info.value.status_code == 401
            assert "WWW-Authenticate" in exc_info.value.headers

    @pytest.mark.asyncio
    async def test_malformed_authorization_header(self):
        """Test malformed Authorization header raises 401."""
        with patch("src.api.security.settings") as mock_settings:
            mock_settings.auth_key = "secret-key-123"

            # No space separator
            with pytest.raises(HTTPException):
                await verify_api_key(x_api_key=None, authorization="Bearersecret-key-123")

            # Wrong scheme
            with pytest.raises(HTTPException):
                await verify_api_key(x_api_key=None, authorization="Basic secret-key-123")

    @pytest.mark.asyncio
    async def test_x_api_key_takes_precedence(self):
        """Test x-api-key header is checked before Authorization."""
        with patch("src.api.security.settings") as mock_settings:
            mock_settings.auth_key = "secret-key-123"

            # Valid x-api-key with invalid Authorization should pass
            await verify_api_key(
                x_api_key="secret-key-123",
                authorization="Bearer wrong-key"
            )
