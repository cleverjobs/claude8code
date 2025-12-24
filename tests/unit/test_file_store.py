"""Unit tests for file storage module."""

import asyncio
import io
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from src.sdk.file_store import (
    MAX_FILE_SIZE,
    StoredFile,
    FileStore,
    get_file_store,
    init_file_store,
    shutdown_file_store,
)


class TestStoredFile:
    """Test StoredFile dataclass."""

    def test_to_metadata(self):
        """Test converting StoredFile to FileMetadata."""
        stored = StoredFile(
            id="file_abc123",
            filename="test.txt",
            mime_type="text/plain",
            size_bytes=100,
            created_at=datetime(2024, 1, 15, 12, 0, 0),
            file_path=Path("/tmp/file_abc123"),
        )
        metadata = stored.to_metadata()

        assert metadata.id == "file_abc123"
        assert metadata.filename == "test.txt"
        assert metadata.mime_type == "text/plain"
        assert metadata.size_bytes == 100
        assert metadata.type == "file"
        assert metadata.downloadable is True
        assert metadata.created_at == "2024-01-15T12:00:00Z"

    def test_to_metadata_with_expires(self):
        """Test StoredFile with expiration."""
        stored = StoredFile(
            id="file_xyz789",
            filename="temp.txt",
            mime_type="text/plain",
            size_bytes=50,
            created_at=datetime(2024, 1, 15, 12, 0, 0),
            file_path=Path("/tmp/file_xyz789"),
            expires_at=datetime(2024, 1, 16, 12, 0, 0),
        )
        # expires_at doesn't appear in metadata
        metadata = stored.to_metadata()
        assert metadata.id == "file_xyz789"


class TestFileStoreInit:
    """Test FileStore initialization."""

    def test_creates_storage_directory(self):
        """Test that __post_init__ creates storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "new_storage" / "nested"
            assert not storage_path.exists()

            store = FileStore(storage_dir=storage_path)
            assert storage_path.exists()

    def test_default_ttl(self):
        """Test default TTL is 24 hours."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))
            assert store.default_ttl_hours == 24

    def test_custom_ttl(self):
        """Test custom TTL setting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir), default_ttl_hours=48)
            assert store.default_ttl_hours == 48


class TestFileStoreLifecycle:
    """Test FileStore start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_cleanup_task(self):
        """Test start creates background cleanup task."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))
            assert store._cleanup_task is None

            await store.start()
            assert store._cleanup_task is not None
            assert not store._cleanup_task.done()

            await store.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_cleanup_task(self):
        """Test stop cancels the cleanup task."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))
            await store.start()
            task = store._cleanup_task

            await store.stop()
            assert store._cleanup_task is None
            assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        """Test calling start multiple times is safe."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))
            await store.start()
            first_task = store._cleanup_task

            await store.start()  # Should not create new task
            assert store._cleanup_task is first_task

            await store.stop()

    @pytest.mark.asyncio
    async def test_stop_idempotent(self):
        """Test calling stop multiple times is safe."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))
            await store.start()

            await store.stop()
            await store.stop()  # Should not raise
            assert store._cleanup_task is None


class TestFileStoreUpload:
    """Test FileStore upload functionality."""

    @pytest.mark.asyncio
    async def test_upload_success(self):
        """Test successful file upload."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))
            file_content = b"Hello, world!"
            file = io.BytesIO(file_content)

            metadata = await store.upload(file, "test.txt")

            assert metadata.id.startswith("file_")
            assert metadata.filename == "test.txt"
            assert metadata.size_bytes == len(file_content)
            assert metadata.mime_type == "text/plain"

    @pytest.mark.asyncio
    async def test_upload_with_content_type(self):
        """Test upload with explicit content type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))
            file = io.BytesIO(b"data")

            metadata = await store.upload(
                file, "data.bin", content_type="application/octet-stream"
            )

            assert metadata.mime_type == "application/octet-stream"

    @pytest.mark.asyncio
    async def test_upload_guesses_mime_type(self):
        """Test upload guesses mime type from filename."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))

            # JSON file
            json_meta = await store.upload(io.BytesIO(b"{}"), "config.json")
            assert json_meta.mime_type == "application/json"

            # Python file
            py_meta = await store.upload(io.BytesIO(b"pass"), "script.py")
            assert py_meta.mime_type == "text/x-python"

    @pytest.mark.asyncio
    async def test_upload_unknown_extension(self):
        """Test upload with unknown extension defaults to octet-stream."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))
            file = io.BytesIO(b"binary data")

            metadata = await store.upload(file, "file.xyz123unknown")
            assert metadata.mime_type == "application/octet-stream"

    @pytest.mark.asyncio
    async def test_upload_size_limit(self):
        """Test upload rejects files exceeding size limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))
            # Create file larger than MAX_FILE_SIZE
            large_content = b"x" * (MAX_FILE_SIZE + 1)
            file = io.BytesIO(large_content)

            with pytest.raises(ValueError) as exc_info:
                await store.upload(file, "large.bin")
            assert "exceeds maximum size" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_upload_custom_ttl(self):
        """Test upload with custom TTL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))
            file = io.BytesIO(b"data")

            metadata = await store.upload(file, "temp.txt", ttl_hours=1)
            # Verify file was stored (TTL is internal)
            assert metadata.id in store._files
            assert store._files[metadata.id].expires_at is not None

    @pytest.mark.asyncio
    async def test_upload_zero_ttl_uses_default(self):
        """Test upload with TTL=0 uses default (0 is falsy in Python)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir), default_ttl_hours=24)
            file = io.BytesIO(b"data")

            # ttl_hours=0 is falsy, so default_ttl_hours is used
            metadata = await store.upload(file, "file.txt", ttl_hours=0)
            assert store._files[metadata.id].expires_at is not None

    @pytest.mark.asyncio
    async def test_upload_no_ttl_provided_uses_default(self):
        """Test upload without ttl_hours uses default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir), default_ttl_hours=48)
            file = io.BytesIO(b"data")

            metadata = await store.upload(file, "file.txt")
            # Should use default 48 hour TTL
            stored = store._files[metadata.id]
            assert stored.expires_at is not None

    @pytest.mark.asyncio
    async def test_upload_writes_to_disk(self):
        """Test upload writes file to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))
            content = b"Test content here"
            file = io.BytesIO(content)

            metadata = await store.upload(file, "test.txt")

            file_path = store._files[metadata.id].file_path
            assert file_path.exists()
            assert file_path.read_bytes() == content


class TestFileStoreGet:
    """Test FileStore get functionality."""

    @pytest.mark.asyncio
    async def test_get_existing_file(self):
        """Test getting existing file metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))
            file = io.BytesIO(b"content")
            uploaded = await store.upload(file, "test.txt")

            result = await store.get(uploaded.id)
            assert result is not None
            assert result.id == uploaded.id
            assert result.filename == "test.txt"

    @pytest.mark.asyncio
    async def test_get_nonexistent_file(self):
        """Test getting nonexistent file returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))

            result = await store.get("file_doesnotexist")
            assert result is None


class TestFileStoreGetContent:
    """Test FileStore get_content functionality."""

    @pytest.mark.asyncio
    async def test_get_content_existing(self):
        """Test getting content of existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))
            content = b"File content here"
            file = io.BytesIO(content)
            uploaded = await store.upload(file, "data.txt")

            result = await store.get_content(uploaded.id)
            assert result is not None
            file_content, filename, mime_type = result
            assert file_content == content
            assert filename == "data.txt"
            assert mime_type == "text/plain"

    @pytest.mark.asyncio
    async def test_get_content_nonexistent(self):
        """Test getting content of nonexistent file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))

            result = await store.get_content("file_notfound")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_content_file_deleted_from_disk(self):
        """Test getting content when file was deleted from disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))
            file = io.BytesIO(b"content")
            uploaded = await store.upload(file, "test.txt")

            # Delete file from disk but keep metadata
            file_path = store._files[uploaded.id].file_path
            file_path.unlink()

            result = await store.get_content(uploaded.id)
            assert result is None
            # Metadata should also be cleaned up
            assert uploaded.id not in store._files


class TestFileStoreDelete:
    """Test FileStore delete functionality."""

    @pytest.mark.asyncio
    async def test_delete_existing_file(self):
        """Test deleting an existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))
            file = io.BytesIO(b"content")
            uploaded = await store.upload(file, "test.txt")
            file_path = store._files[uploaded.id].file_path

            result = await store.delete(uploaded.id)
            assert result is True
            assert uploaded.id not in store._files
            assert not file_path.exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_file(self):
        """Test deleting nonexistent file returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))

            result = await store.delete("file_notfound")
            assert result is False

    @pytest.mark.asyncio
    async def test_delete_handles_disk_error(self):
        """Test delete handles disk errors gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))
            file = io.BytesIO(b"content")
            uploaded = await store.upload(file, "test.txt")

            # Delete file from disk first
            store._files[uploaded.id].file_path.unlink()

            # Should still succeed (missing_ok=True)
            result = await store.delete(uploaded.id)
            assert result is True
            assert uploaded.id not in store._files


class TestFileStoreList:
    """Test FileStore list functionality."""

    @pytest.mark.asyncio
    async def test_list_empty(self):
        """Test listing when no files exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))

            files, has_more = await store.list()
            assert files == []
            assert has_more is False

    @pytest.mark.asyncio
    async def test_list_all_files(self):
        """Test listing all files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))

            # Upload 3 files
            for i in range(3):
                await store.upload(io.BytesIO(f"file{i}".encode()), f"file{i}.txt")

            files, has_more = await store.list(limit=10)
            assert len(files) == 3
            assert has_more is False

    @pytest.mark.asyncio
    async def test_list_with_limit(self):
        """Test listing with limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))

            # Upload 5 files
            for i in range(5):
                await store.upload(io.BytesIO(f"file{i}".encode()), f"file{i}.txt")

            files, has_more = await store.list(limit=3)
            assert len(files) == 3
            assert has_more is True

    @pytest.mark.asyncio
    async def test_list_with_after_id(self):
        """Test listing with after_id cursor."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))

            # Upload files with slight delay to ensure ordering
            uploaded = []
            for i in range(3):
                meta = await store.upload(io.BytesIO(f"file{i}".encode()), f"file{i}.txt")
                uploaded.append(meta)

            # Get files sorted by creation (newest first)
            all_files, _ = await store.list(limit=10)

            # Get files after the first one
            cursor_id = all_files[0].id
            files, has_more = await store.list(after_id=cursor_id)

            # Should return files after the cursor
            assert len(files) <= 2
            assert all(f.id != cursor_id for f in files)

    @pytest.mark.asyncio
    async def test_list_with_before_id(self):
        """Test listing with before_id cursor."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))

            # Upload files
            for i in range(3):
                await store.upload(io.BytesIO(f"file{i}".encode()), f"file{i}.txt")

            all_files, _ = await store.list(limit=10)

            # Get files before the last one
            cursor_id = all_files[-1].id
            files, _ = await store.list(before_id=cursor_id)

            assert all(f.id != cursor_id for f in files)

    @pytest.mark.asyncio
    async def test_list_cursor_not_found(self):
        """Test listing with nonexistent cursor ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))

            await store.upload(io.BytesIO(b"content"), "file.txt")

            # Nonexistent cursor - should return all files
            files, _ = await store.list(after_id="file_nonexistent")
            assert len(files) == 1


class TestFileStoreCleanup:
    """Test FileStore cleanup functionality."""

    @pytest.mark.asyncio
    async def test_cleanup_expired_removes_old_files(self):
        """Test cleanup removes expired files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir), default_ttl_hours=1)

            # Upload a file
            file = io.BytesIO(b"content")
            meta = await store.upload(file, "test.txt")

            # Manually set expiration in the past
            store._files[meta.id].expires_at = datetime.utcnow() - timedelta(hours=1)

            # Run cleanup
            await store._cleanup_expired()

            assert meta.id not in store._files

    @pytest.mark.asyncio
    async def test_cleanup_keeps_valid_files(self):
        """Test cleanup keeps non-expired files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir), default_ttl_hours=24)

            file = io.BytesIO(b"content")
            meta = await store.upload(file, "test.txt")

            # Run cleanup
            await store._cleanup_expired()

            # File should still exist
            assert meta.id in store._files

    @pytest.mark.asyncio
    async def test_cleanup_keeps_non_expired_files(self):
        """Test cleanup keeps files that haven't expired yet."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir), default_ttl_hours=24)

            file = io.BytesIO(b"content")
            meta = await store.upload(file, "test.txt")

            # File has a future expiration
            assert store._files[meta.id].expires_at is not None

            # Run cleanup
            await store._cleanup_expired()

            # File should still exist (not expired yet)
            assert meta.id in store._files


class TestFileStoreStats:
    """Test FileStore statistics."""

    @pytest.mark.asyncio
    async def test_get_stats_empty(self):
        """Test stats with no files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))

            stats = store.get_stats()
            assert stats["file_count"] == 0
            assert stats["total_size_bytes"] == 0
            assert stats["storage_dir"] == str(Path(tmpdir))
            assert stats["default_ttl_hours"] == 24

    @pytest.mark.asyncio
    async def test_get_stats_with_files(self):
        """Test stats with files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))

            await store.upload(io.BytesIO(b"12345"), "file1.txt")  # 5 bytes
            await store.upload(io.BytesIO(b"12345678"), "file2.txt")  # 8 bytes

            stats = store.get_stats()
            assert stats["file_count"] == 2
            assert stats["total_size_bytes"] == 13


class TestFileStoreHelpers:
    """Test FileStore helper methods."""

    def test_generate_id_format(self):
        """Test ID generation format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))

            file_id = store._generate_id()
            assert file_id.startswith("file_")
            assert len(file_id) == 29  # "file_" + 24 hex chars

    def test_generate_id_uniqueness(self):
        """Test ID generation produces unique IDs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))

            ids = [store._generate_id() for _ in range(100)]
            assert len(ids) == len(set(ids))

    def test_guess_mime_type_known(self):
        """Test MIME type guessing for known extensions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))

            assert store._guess_mime_type("file.txt") == "text/plain"
            assert store._guess_mime_type("file.json") == "application/json"
            assert store._guess_mime_type("file.html") == "text/html"
            assert store._guess_mime_type("file.png") == "image/png"

    def test_guess_mime_type_unknown(self):
        """Test MIME type guessing for unknown extensions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FileStore(storage_dir=Path(tmpdir))

            # Use truly unknown extensions
            assert store._guess_mime_type("file.qwerty123") == "application/octet-stream"
            assert store._guess_mime_type("noextension") == "application/octet-stream"


class TestGlobalFileStore:
    """Test global file store functions."""

    def test_get_file_store_initially_none(self):
        """Test get_file_store returns None before init."""
        # Reset global state
        import src.sdk.file_store as module
        original = module._file_store
        module._file_store = None

        try:
            result = get_file_store()
            assert result is None
        finally:
            module._file_store = original

    def test_init_file_store(self):
        """Test init_file_store creates store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import src.sdk.file_store as module
            original = module._file_store

            try:
                store = init_file_store(tmpdir, default_ttl_hours=12)
                assert store is not None
                assert store.default_ttl_hours == 12
                assert get_file_store() is store
            finally:
                module._file_store = original

    @pytest.mark.asyncio
    async def test_shutdown_file_store(self):
        """Test shutdown_file_store cleans up."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import src.sdk.file_store as module
            original = module._file_store

            try:
                store = init_file_store(tmpdir)
                await store.start()

                await shutdown_file_store()
                assert get_file_store() is None
            finally:
                module._file_store = original

    @pytest.mark.asyncio
    async def test_shutdown_file_store_when_none(self):
        """Test shutdown_file_store when no store exists."""
        import src.sdk.file_store as module
        original = module._file_store
        module._file_store = None

        try:
            await shutdown_file_store()  # Should not raise
        finally:
            module._file_store = original
