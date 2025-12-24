"""Unit tests for Files API models."""

import pytest
from pydantic import ValidationError

from src.models.files import (
    FileMetadata,
    FileDeletedResponse,
    FilesListResponse,
)


class TestFileMetadata:
    """Test FileMetadata model."""

    def test_create_with_all_fields(self):
        """Test creating FileMetadata with all fields."""
        metadata = FileMetadata(
            id="file_abc123",
            filename="document.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            created_at="2024-01-15T12:00:00Z",
        )

        assert metadata.id == "file_abc123"
        assert metadata.filename == "document.pdf"
        assert metadata.mime_type == "application/pdf"
        assert metadata.size_bytes == 1024
        assert metadata.created_at == "2024-01-15T12:00:00Z"

    def test_default_type(self):
        """Test default type is 'file'."""
        metadata = FileMetadata(
            id="file_123",
            filename="test.txt",
            mime_type="text/plain",
            size_bytes=100,
            created_at="2024-01-15T12:00:00Z",
        )

        assert metadata.type == "file"

    def test_default_downloadable(self):
        """Test default downloadable is True."""
        metadata = FileMetadata(
            id="file_123",
            filename="test.txt",
            mime_type="text/plain",
            size_bytes=100,
            created_at="2024-01-15T12:00:00Z",
        )

        assert metadata.downloadable is True

    def test_explicit_downloadable_false(self):
        """Test explicitly setting downloadable to False."""
        metadata = FileMetadata(
            id="file_123",
            filename="test.txt",
            mime_type="text/plain",
            size_bytes=100,
            created_at="2024-01-15T12:00:00Z",
            downloadable=False,
        )

        assert metadata.downloadable is False

    def test_model_dump(self):
        """Test model serialization."""
        metadata = FileMetadata(
            id="file_xyz",
            filename="data.json",
            mime_type="application/json",
            size_bytes=500,
            created_at="2024-01-15T12:00:00Z",
        )

        data = metadata.model_dump()
        assert data["id"] == "file_xyz"
        assert data["type"] == "file"
        assert data["filename"] == "data.json"
        assert data["downloadable"] is True

    def test_required_fields(self):
        """Test that required fields must be provided."""
        with pytest.raises(ValidationError):
            FileMetadata(
                id="file_123",
                # missing filename, mime_type, size_bytes, created_at
            )

    def test_large_size_bytes(self):
        """Test handling large file sizes."""
        metadata = FileMetadata(
            id="file_large",
            filename="bigfile.bin",
            mime_type="application/octet-stream",
            size_bytes=500 * 1024 * 1024,  # 500 MB
            created_at="2024-01-15T12:00:00Z",
        )

        assert metadata.size_bytes == 500 * 1024 * 1024


class TestFileDeletedResponse:
    """Test FileDeletedResponse model."""

    def test_create_response(self):
        """Test creating FileDeletedResponse."""
        response = FileDeletedResponse(id="file_deleted123")

        assert response.id == "file_deleted123"
        assert response.type == "file_deleted"

    def test_default_type(self):
        """Test default type is 'file_deleted'."""
        response = FileDeletedResponse(id="file_abc")
        assert response.type == "file_deleted"

    def test_model_dump(self):
        """Test model serialization."""
        response = FileDeletedResponse(id="file_xyz")

        data = response.model_dump()
        assert data["id"] == "file_xyz"
        assert data["type"] == "file_deleted"

    def test_required_id(self):
        """Test that id is required."""
        with pytest.raises(ValidationError):
            FileDeletedResponse()  # missing id


class TestFilesListResponse:
    """Test FilesListResponse model."""

    def test_empty_list(self):
        """Test response with empty list."""
        response = FilesListResponse(data=[])

        assert response.data == []
        assert response.first_id is None
        assert response.last_id is None
        assert response.has_more is False

    def test_with_files(self):
        """Test response with files."""
        files = [
            FileMetadata(
                id="file_1",
                filename="file1.txt",
                mime_type="text/plain",
                size_bytes=100,
                created_at="2024-01-15T12:00:00Z",
            ),
            FileMetadata(
                id="file_2",
                filename="file2.txt",
                mime_type="text/plain",
                size_bytes=200,
                created_at="2024-01-15T12:01:00Z",
            ),
        ]

        response = FilesListResponse(
            data=files,
            first_id="file_1",
            last_id="file_2",
            has_more=True,
        )

        assert len(response.data) == 2
        assert response.first_id == "file_1"
        assert response.last_id == "file_2"
        assert response.has_more is True

    def test_default_has_more(self):
        """Test default has_more is False."""
        response = FilesListResponse(data=[])
        assert response.has_more is False

    def test_model_dump(self):
        """Test model serialization."""
        response = FilesListResponse(
            data=[
                FileMetadata(
                    id="file_1",
                    filename="test.txt",
                    mime_type="text/plain",
                    size_bytes=50,
                    created_at="2024-01-15T12:00:00Z",
                )
            ],
            first_id="file_1",
            last_id="file_1",
        )

        data = response.model_dump()
        assert "data" in data
        assert len(data["data"]) == 1
        assert data["first_id"] == "file_1"
        assert data["last_id"] == "file_1"
        assert data["has_more"] is False

    def test_required_data(self):
        """Test that data is required."""
        with pytest.raises(ValidationError):
            FilesListResponse()  # missing data
