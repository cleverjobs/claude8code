"""File storage for the Files API.

Provides local file storage with metadata tracking for the Files API.
Files are stored in a configurable directory with in-memory metadata.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import BinaryIO

from ..models.files import FileMetadata

logger = logging.getLogger(__name__)


# Maximum file size (500 MB per API spec)
MAX_FILE_SIZE = 500 * 1024 * 1024


@dataclass
class StoredFile:
    """Internal representation of a stored file."""
    id: str
    filename: str
    mime_type: str
    size_bytes: int
    created_at: datetime
    file_path: Path
    expires_at: datetime | None = None

    def to_metadata(self) -> FileMetadata:
        """Convert to API response format."""
        return FileMetadata(
            id=self.id,
            filename=self.filename,
            mime_type=self.mime_type,
            size_bytes=self.size_bytes,
            created_at=self.created_at.isoformat() + "Z",
            downloadable=True,
        )


@dataclass
class FileStore:
    """File storage manager.

    Stores files locally and tracks metadata in memory.
    Supports TTL-based expiration for automatic cleanup.
    """
    storage_dir: Path
    default_ttl_hours: int = 24
    _files: dict[str, StoredFile] = field(default_factory=dict)
    _cleanup_task: asyncio.Task | None = None

    def __post_init__(self) -> None:
        """Ensure storage directory exists."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"FileStore initialized at {self.storage_dir}")

    async def start(self) -> None:
        """Start the background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("FileStore cleanup task started")

    async def stop(self) -> None:
        """Stop the background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("FileStore cleanup task stopped")

    async def _cleanup_loop(self) -> None:
        """Background task to clean up expired files."""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in cleanup loop: {e}")

    async def _cleanup_expired(self) -> None:
        """Remove expired files."""
        now = datetime.utcnow()
        expired = [
            file_id
            for file_id, stored in self._files.items()
            if stored.expires_at and stored.expires_at < now
        ]

        for file_id in expired:
            await self.delete(file_id)
            logger.info(f"Cleaned up expired file: {file_id}")

    def _generate_id(self) -> str:
        """Generate a unique file ID."""
        return f"file_{uuid.uuid4().hex[:24]}"

    def _guess_mime_type(self, filename: str) -> str:
        """Guess MIME type from filename."""
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"

    async def upload(
        self,
        file: BinaryIO,
        filename: str,
        content_type: str | None = None,
        ttl_hours: int | None = None,
    ) -> FileMetadata:
        """Upload a file to storage.

        Args:
            file: File-like object to upload.
            filename: Original filename.
            content_type: MIME type (guessed from filename if not provided).
            ttl_hours: Time to live in hours (uses default if not provided).

        Returns:
            FileMetadata for the uploaded file.

        Raises:
            ValueError: If file exceeds size limit.
        """
        file_id = self._generate_id()
        mime_type = content_type or self._guess_mime_type(filename)

        # Create file path
        file_path = self.storage_dir / file_id

        # Read and write file content
        content = file.read()
        size_bytes = len(content)

        if size_bytes > MAX_FILE_SIZE:
            raise ValueError(f"File exceeds maximum size of {MAX_FILE_SIZE} bytes")

        # Write to disk
        file_path.write_bytes(content)

        # Calculate expiration
        created_at = datetime.utcnow()
        ttl = ttl_hours or self.default_ttl_hours
        expires_at = created_at + timedelta(hours=ttl) if ttl > 0 else None

        # Store metadata
        stored = StoredFile(
            id=file_id,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            created_at=created_at,
            file_path=file_path,
            expires_at=expires_at,
        )
        self._files[file_id] = stored

        logger.info(f"Uploaded file: {file_id} ({filename}, {size_bytes} bytes)")
        return stored.to_metadata()

    async def get(self, file_id: str) -> FileMetadata | None:
        """Get file metadata by ID.

        Args:
            file_id: The file ID.

        Returns:
            FileMetadata or None if not found.
        """
        stored = self._files.get(file_id)
        if stored is None:
            return None
        return stored.to_metadata()

    async def get_content(self, file_id: str) -> tuple[bytes, str, str] | None:
        """Get file content by ID.

        Args:
            file_id: The file ID.

        Returns:
            Tuple of (content, filename, mime_type) or None if not found.
        """
        stored = self._files.get(file_id)
        if stored is None:
            return None
        if not stored.file_path.exists():
            # File was deleted from disk but metadata remains
            del self._files[file_id]
            return None
        content = stored.file_path.read_bytes()
        return content, stored.filename, stored.mime_type

    async def delete(self, file_id: str) -> bool:
        """Delete a file by ID.

        Args:
            file_id: The file ID.

        Returns:
            True if file was deleted, False if not found.
        """
        stored = self._files.pop(file_id, None)
        if stored is None:
            return False

        # Remove from disk
        try:
            stored.file_path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Error deleting file {file_id} from disk: {e}")

        logger.info(f"Deleted file: {file_id}")
        return True

    async def list(
        self,
        limit: int = 20,
        after_id: str | None = None,
        before_id: str | None = None,
    ) -> tuple[list[FileMetadata], bool]:
        """List files with pagination.

        Args:
            limit: Maximum number of files to return.
            after_id: Return files after this ID (exclusive).
            before_id: Return files before this ID (exclusive).

        Returns:
            Tuple of (files list, has_more flag).
        """
        # Sort files by creation time (newest first)
        sorted_files = sorted(
            self._files.values(),
            key=lambda f: f.created_at,
            reverse=True,
        )

        # Apply cursor-based pagination
        if after_id:
            # Find the index of the cursor file
            cursor_idx = None
            for i, f in enumerate(sorted_files):
                if f.id == after_id:
                    cursor_idx = i
                    break
            if cursor_idx is not None:
                sorted_files = sorted_files[cursor_idx + 1:]

        if before_id:
            cursor_idx = None
            for i, f in enumerate(sorted_files):
                if f.id == before_id:
                    cursor_idx = i
                    break
            if cursor_idx is not None:
                sorted_files = sorted_files[:cursor_idx]

        # Apply limit
        has_more = len(sorted_files) > limit
        result = sorted_files[:limit]

        return [f.to_metadata() for f in result], has_more

    def get_stats(self) -> dict:
        """Get storage statistics."""
        total_size = sum(f.size_bytes for f in self._files.values())
        return {
            "file_count": len(self._files),
            "total_size_bytes": total_size,
            "storage_dir": str(self.storage_dir),
            "default_ttl_hours": self.default_ttl_hours,
        }


# Global file store instance
_file_store: FileStore | None = None


def get_file_store() -> FileStore | None:
    """Get the global file store instance."""
    return _file_store


def init_file_store(storage_dir: str | Path, default_ttl_hours: int = 24) -> FileStore:
    """Initialize the global file store.

    Args:
        storage_dir: Directory to store files.
        default_ttl_hours: Default time to live for files.

    Returns:
        The initialized FileStore.
    """
    global _file_store
    _file_store = FileStore(
        storage_dir=Path(storage_dir),
        default_ttl_hours=default_ttl_hours,
    )
    return _file_store


async def shutdown_file_store() -> None:
    """Shutdown the global file store."""
    global _file_store
    if _file_store:
        await _file_store.stop()
        _file_store = None
