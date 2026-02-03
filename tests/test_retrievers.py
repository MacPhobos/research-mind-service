"""Unit tests for content retrievers.

Tests each retriever in isolation with filesystem mocking.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest


# --- TextRetriever Tests ---


def test_text_retriever_writes_content(tmp_path: Path) -> None:
    """Design Doc Section 15: test_text_retriever_writes_content"""
    from app.services.retrievers.text_retriever import TextRetriever

    retriever = TextRetriever()
    result = retriever.retrieve(
        source="Hello, world!",
        target_dir=tmp_path,
        title="Test Note",
    )

    assert result.success is True
    assert result.size_bytes == len("Hello, world!".encode())
    assert (tmp_path / "content.txt").read_text() == "Hello, world!"
    assert result.mime_type == "text/plain"
    assert result.title == "Test Note"


def test_text_retriever_rejects_oversized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Text exceeding max_text_bytes returns success=False."""
    from app.services.retrievers.text_retriever import TextRetriever

    # Mock settings to use a small limit for testing
    mock_settings = MagicMock()
    mock_settings.max_text_bytes = 10  # Very small limit
    monkeypatch.setattr("app.services.retrievers.text_retriever.settings", mock_settings)

    retriever = TextRetriever()
    result = retriever.retrieve(
        source="This text is definitely longer than 10 bytes",
        target_dir=tmp_path,
        title="Too Large",
    )

    assert result.success is False
    assert "exceeds maximum size" in result.error_message


def test_text_retriever_writes_metadata(tmp_path: Path) -> None:
    """metadata.json contains title and extra metadata."""
    from app.services.retrievers.text_retriever import TextRetriever

    retriever = TextRetriever()
    result = retriever.retrieve(
        source="Some text",
        target_dir=tmp_path,
        title="My Title",
        metadata={"author": "Test Author"},
    )

    assert result.success is True
    meta_file = tmp_path / "metadata.json"
    assert meta_file.exists()
    meta = json.loads(meta_file.read_text())
    assert meta["title"] == "My Title"
    assert meta["author"] == "Test Author"


def test_text_retriever_default_title(tmp_path: Path) -> None:
    """Title defaults to 'Untitled text' when not provided."""
    from app.services.retrievers.text_retriever import TextRetriever

    retriever = TextRetriever()
    result = retriever.retrieve(
        source="Some content",
        target_dir=tmp_path,
    )

    assert result.success is True
    assert result.title == "Untitled text"


# --- FileUploadRetriever Tests ---


def test_file_upload_writes_file(tmp_path: Path) -> None:
    """Uploaded bytes are written with original filename."""
    from app.services.retrievers.file_upload import FileUploadRetriever

    retriever = FileUploadRetriever()
    file_content = b"PDF file content here"

    result = retriever.retrieve(
        source=file_content,
        target_dir=tmp_path,
        metadata={"original_filename": "test.pdf"},
    )

    assert result.success is True
    assert (tmp_path / "test.pdf").read_bytes() == file_content
    assert result.size_bytes == len(file_content)


def test_file_upload_rejects_oversized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Design Doc Section 15: test_file_upload_retriever_rejects_oversized"""
    from app.services.retrievers.file_upload import FileUploadRetriever

    # Mock settings to use a small limit for testing
    mock_settings = MagicMock()
    mock_settings.max_upload_bytes = 100  # Very small limit
    monkeypatch.setattr("app.services.retrievers.file_upload.settings", mock_settings)

    retriever = FileUploadRetriever()
    big_file = b"x" * 200  # Exceeds limit

    result = retriever.retrieve(
        source=big_file,
        target_dir=tmp_path,
        metadata={"original_filename": "big.pdf"},
    )

    assert result.success is False
    assert "exceeds maximum size" in result.error_message


def test_file_upload_detects_mime_type(tmp_path: Path) -> None:
    """MIME type is guessed from filename extension."""
    from app.services.retrievers.file_upload import FileUploadRetriever

    retriever = FileUploadRetriever()

    result = retriever.retrieve(
        source=b"content",
        target_dir=tmp_path,
        metadata={"original_filename": "document.pdf"},
    )

    assert result.success is True
    assert result.mime_type == "application/pdf"


def test_file_upload_default_filename(tmp_path: Path) -> None:
    """Uses 'upload' when original_filename not in metadata."""
    from app.services.retrievers.file_upload import FileUploadRetriever

    retriever = FileUploadRetriever()

    result = retriever.retrieve(
        source=b"some data",
        target_dir=tmp_path,
    )

    assert result.success is True
    assert (tmp_path / "upload").exists()
    assert result.metadata["original_filename"] == "upload"


# --- UrlRetriever Tests ---


def test_url_retriever_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocked HTTP GET returns content, written to content.md."""
    from app.services.retrievers.url_retriever import UrlRetriever

    # Mock httpx.Client
    mock_response = MagicMock()
    mock_response.content = b"<html>Page content</html>"
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "text/html; charset=utf-8"}

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response

    monkeypatch.setattr(httpx, "Client", MagicMock(return_value=mock_client))

    retriever = UrlRetriever(timeout=10)
    result = retriever.retrieve(
        source="https://example.com/page",
        target_dir=tmp_path,
        title="Example Page",
    )

    assert result.success is True
    assert result.size_bytes == len(b"<html>Page content</html>")
    assert (tmp_path / "content.md").read_bytes() == b"<html>Page content</html>"
    assert result.mime_type == "text/html"


def test_url_retriever_http_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP 404 returns success=False with status code in error."""
    from app.services.retrievers.url_retriever import UrlRetriever

    # Mock httpx.Client to raise HTTPStatusError
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.reason_phrase = "Not Found"

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.side_effect = httpx.HTTPStatusError(
        "Not Found",
        request=MagicMock(),
        response=mock_response,
    )

    monkeypatch.setattr(httpx, "Client", MagicMock(return_value=mock_client))

    retriever = UrlRetriever(timeout=10)
    result = retriever.retrieve(
        source="https://example.com/notfound",
        target_dir=tmp_path,
    )

    assert result.success is False
    assert "HTTP 404" in result.error_message


def test_url_retriever_connection_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Connection failure returns success=False."""
    from app.services.retrievers.url_retriever import UrlRetriever

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.side_effect = httpx.RequestError("Connection failed")

    monkeypatch.setattr(httpx, "Client", MagicMock(return_value=mock_client))

    retriever = UrlRetriever(timeout=10)
    result = retriever.retrieve(
        source="https://unreachable.example.com",
        target_dir=tmp_path,
    )

    assert result.success is False
    assert "Request failed" in result.error_message


def test_url_retriever_oversized_response(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Response exceeding max_url_response_bytes returns success=False."""
    from app.services.retrievers.url_retriever import UrlRetriever

    # Mock settings to use a small limit
    mock_settings = MagicMock()
    mock_settings.url_fetch_timeout = 10
    mock_settings.max_url_response_bytes = 50
    monkeypatch.setattr("app.services.retrievers.url_retriever.settings", mock_settings)

    mock_response = MagicMock()
    mock_response.content = b"x" * 100  # Exceeds limit
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "text/html"}

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response

    monkeypatch.setattr(httpx, "Client", MagicMock(return_value=mock_client))

    retriever = UrlRetriever()
    result = retriever.retrieve(
        source="https://example.com/large",
        target_dir=tmp_path,
    )

    assert result.success is False
    assert "exceeds maximum size" in result.error_message


# --- GitRepoRetriever Tests ---


def test_git_repo_handles_missing_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Design Doc Section 15: monkeypatch subprocess.run to raise FileNotFoundError"""
    from app.services.retrievers.git_repo import GitRepoRetriever

    monkeypatch.setattr(
        subprocess,
        "run",
        MagicMock(side_effect=FileNotFoundError("git not found")),
    )

    retriever = GitRepoRetriever(timeout=10, depth=1)
    result = retriever.retrieve(
        source="https://github.com/test/repo.git",
        target_dir=tmp_path,
    )

    assert result.success is False
    assert "git CLI not found" in result.error_message


def test_git_repo_handles_clone_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-zero exit code returns success=False with stderr."""
    from app.services.retrievers.git_repo import GitRepoRetriever

    mock_result = MagicMock()
    mock_result.returncode = 128
    mock_result.stderr = "fatal: repository not found"

    monkeypatch.setattr(subprocess, "run", MagicMock(return_value=mock_result))

    retriever = GitRepoRetriever(timeout=10, depth=1)
    result = retriever.retrieve(
        source="https://github.com/nonexistent/repo.git",
        target_dir=tmp_path,
    )

    assert result.success is False
    assert "git clone failed" in result.error_message
    assert "repository not found" in result.error_message


def test_git_repo_handles_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TimeoutExpired returns success=False."""
    from app.services.retrievers.git_repo import GitRepoRetriever

    monkeypatch.setattr(
        subprocess,
        "run",
        MagicMock(side_effect=subprocess.TimeoutExpired(cmd="git clone", timeout=10)),
    )

    retriever = GitRepoRetriever(timeout=10, depth=1)
    result = retriever.retrieve(
        source="https://github.com/slow/repo.git",
        target_dir=tmp_path,
    )

    assert result.success is False
    assert "timed out" in result.error_message


def test_git_repo_derives_title_from_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Title derived from clone URL when not provided."""
    from app.services.retrievers.git_repo import GitRepoRetriever

    # Mock successful clone
    mock_result = MagicMock()
    mock_result.returncode = 0

    def mock_run(*args, **kwargs):
        # Create a fake repo directory with a file
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / "README.md").write_text("# Test")
        return mock_result

    monkeypatch.setattr(subprocess, "run", mock_run)

    retriever = GitRepoRetriever(timeout=10, depth=1)
    result = retriever.retrieve(
        source="https://github.com/user/my-project.git",
        target_dir=tmp_path,
    )

    assert result.success is True
    assert result.title == "my-project"


def test_git_repo_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Successful clone creates repo directory and metadata."""
    from app.services.retrievers.git_repo import GitRepoRetriever

    mock_result = MagicMock()
    mock_result.returncode = 0

    def mock_run(*args, **kwargs):
        # Create a fake repo with files
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / "README.md").write_text("# Test Repo")
        (repo_dir / "src").mkdir()
        (repo_dir / "src" / "main.py").write_text("print('hello')")
        return mock_result

    monkeypatch.setattr(subprocess, "run", mock_run)

    retriever = GitRepoRetriever(timeout=120, depth=1)
    result = retriever.retrieve(
        source="https://github.com/test/repo.git",
        target_dir=tmp_path,
        title="Custom Title",
    )

    assert result.success is True
    assert result.title == "Custom Title"
    assert result.size_bytes > 0
    assert (tmp_path / "metadata.json").exists()

    meta = json.loads((tmp_path / "metadata.json").read_text())
    assert meta["clone_url"] == "https://github.com/test/repo.git"
    assert meta["depth"] == 1


# --- McpSourceRetriever Tests ---


def test_mcp_source_returns_not_implemented(tmp_path: Path) -> None:
    """Always returns success=False with not-implemented message."""
    from app.services.retrievers.mcp_source import McpSourceRetriever

    retriever = McpSourceRetriever()
    result = retriever.retrieve(
        source="mcp://some-resource",
        target_dir=tmp_path,
        title="MCP Resource",
    )

    assert result.success is False
    assert "not yet implemented" in result.error_message
    assert result.metadata["source_uri"] == "mcp://some-resource"


def test_mcp_source_uses_source_as_default_title(tmp_path: Path) -> None:
    """Title defaults to source when not provided."""
    from app.services.retrievers.mcp_source import McpSourceRetriever

    retriever = McpSourceRetriever()
    result = retriever.retrieve(
        source="mcp://default-title-test",
        target_dir=tmp_path,
    )

    assert result.title == "mcp://default-title-test"


# --- Factory Tests ---


def test_factory_returns_correct_retriever() -> None:
    """get_retriever() returns correct class for each content type."""
    from app.services.retrievers.factory import get_retriever
    from app.services.retrievers.file_upload import FileUploadRetriever
    from app.services.retrievers.git_repo import GitRepoRetriever
    from app.services.retrievers.mcp_source import McpSourceRetriever
    from app.services.retrievers.text_retriever import TextRetriever
    from app.services.retrievers.url_retriever import UrlRetriever

    assert isinstance(get_retriever("text"), TextRetriever)
    assert isinstance(get_retriever("file_upload"), FileUploadRetriever)
    assert isinstance(get_retriever("url"), UrlRetriever)
    assert isinstance(get_retriever("git_repo"), GitRepoRetriever)
    assert isinstance(get_retriever("mcp_source"), McpSourceRetriever)


def test_factory_raises_for_unknown_type() -> None:
    """get_retriever('unknown') raises ValueError."""
    from app.services.retrievers.factory import get_retriever

    with pytest.raises(ValueError, match="Unknown content type"):
        get_retriever("unknown_type")
