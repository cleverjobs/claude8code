"""
Optional API key authentication for claude8code.

When CLAUDE8CODE_AUTH_KEY is set, requests must include a valid API key
in either the `x-api-key` header or `Authorization: Bearer <key>` header.

When CLAUDE8CODE_AUTH_KEY is not set (empty/None), authentication is disabled.
"""

from fastapi import Header, HTTPException, status

from ..core import settings


async def verify_api_key(
    x_api_key: str | None = Header(None, alias="x-api-key"),
    authorization: str | None = Header(None),
) -> None:
    """
    Verify API key if CLAUDE8CODE_AUTH_KEY is configured.

    Checks both standard Anthropic header (x-api-key) and Bearer token.
    If no auth_key is configured, all requests are allowed.

    Args:
        x_api_key: Value from x-api-key header (Anthropic SDK style)
        authorization: Value from Authorization header (Bearer token style)

    Raises:
        HTTPException: 401 if auth is required but key is missing/invalid
    """
    # If no auth key configured, allow all requests
    if not settings.auth_key:
        return

    # Check x-api-key header first (Anthropic SDK convention)
    if x_api_key and x_api_key == settings.auth_key:
        return

    # Check Authorization: Bearer <key> header
    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            if parts[1] == settings.auth_key:
                return

    # Auth required but no valid key provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API key. Provide via x-api-key header or Authorization: Bearer <key>",
        headers={"WWW-Authenticate": "Bearer"},
    )
