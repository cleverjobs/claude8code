"""Error types and response models for Anthropic API compatibility.

Provides error type enums with HTTP status code mapping and
error response structures matching the official API format.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel


class SDKMessageMode(str, Enum):
    """How to handle Claude SDK internal messages in responses.

    - FORWARD: Pass through raw SDK messages (tool_use, tool_result blocks)
    - FORMATTED: Convert tool blocks to XML-tagged text format
    - IGNORE: Strip SDK internal messages, only return final text
    """

    FORWARD = "forward"
    FORMATTED = "formatted"
    IGNORE = "ignore"


class ErrorType(str, Enum):
    """Anthropic API error types with corresponding HTTP status codes.

    Maps to official error types:
    - invalid_request_error (400): Invalid request parameters
    - authentication_error (401): Invalid or missing API key
    - permission_error (403): API key lacks permission
    - not_found_error (404): Resource not found
    - rate_limit_error (429): Rate limit exceeded
    - api_error (500): Internal server error
    - overloaded_error (529): Service overloaded
    """

    INVALID_REQUEST = "invalid_request_error"
    AUTHENTICATION = "authentication_error"
    PERMISSION = "permission_error"
    NOT_FOUND = "not_found_error"
    RATE_LIMIT = "rate_limit_error"
    API = "api_error"
    OVERLOADED = "overloaded_error"

    @property
    def status_code(self) -> int:
        """Get HTTP status code for this error type."""
        return {
            ErrorType.INVALID_REQUEST: 400,
            ErrorType.AUTHENTICATION: 401,
            ErrorType.PERMISSION: 403,
            ErrorType.NOT_FOUND: 404,
            ErrorType.RATE_LIMIT: 429,
            ErrorType.API: 500,
            ErrorType.OVERLOADED: 529,
        }[self]


class ErrorDetail(BaseModel):
    """Error detail object."""
    type: str
    message: str


class ErrorResponse(BaseModel):
    """Error response body."""
    type: Literal["error"] = "error"
    error: ErrorDetail
