"""Files API models matching Anthropic's schema.

These models support the Files API for uploading and managing files
that can be referenced in Messages API requests.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class FileMetadata(BaseModel):
    """Metadata for an uploaded file - matches Anthropic's schema.

    Returned when uploading, listing, or retrieving file info.
    """
    id: str
    type: Literal["file"] = "file"
    filename: str
    mime_type: str
    size_bytes: int
    created_at: str  # RFC 3339 datetime string
    downloadable: bool = True


class FileDeletedResponse(BaseModel):
    """Response when a file is deleted."""
    id: str
    type: Literal["file_deleted"] = "file_deleted"


class FilesListResponse(BaseModel):
    """Response for GET /v1/files - matches Anthropic's pagination format."""
    data: list[FileMetadata]
    first_id: str | None = None
    last_id: str | None = None
    has_more: bool = False
