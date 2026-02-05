"""Factory for selecting the appropriate content retriever."""

from __future__ import annotations

from app.models.content_item import ContentType
from app.services.retrievers.base import ContentRetriever
from app.services.retrievers.document import DocumentRetriever
from app.services.retrievers.file_upload import FileUploadRetriever
from app.services.retrievers.git_repo import GitRepoRetriever
from app.services.retrievers.mcp_source import McpSourceRetriever
from app.services.retrievers.text_retriever import TextRetriever
from app.services.retrievers.url_retriever import UrlRetriever


_REGISTRY: dict[str, type] = {
    ContentType.FILE_UPLOAD.value: FileUploadRetriever,
    ContentType.TEXT.value: TextRetriever,
    ContentType.URL.value: UrlRetriever,
    ContentType.GIT_REPO.value: GitRepoRetriever,
    ContentType.MCP_SOURCE.value: McpSourceRetriever,
    ContentType.DOCUMENT.value: DocumentRetriever,
}


def get_retriever(content_type: str) -> ContentRetriever:
    """Return an instantiated retriever for the given content type.

    Raises:
        ValueError: If content_type is not recognized.
    """
    cls = _REGISTRY.get(content_type)
    if cls is None:
        raise ValueError(f"Unknown content type: {content_type}")
    return cls()
