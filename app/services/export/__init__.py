"""Chat export service module.

Provides exporters for converting chat history to different formats (PDF, Markdown).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.exceptions import InvalidExportFormatError
from app.schemas.chat import ChatExportFormat
from app.services.export.base import ChatExporter, ExportMetadata
from app.services.export.markdown import MarkdownExporter
from app.services.export.pdf import PDFExporter

if TYPE_CHECKING:
    pass


_EXPORTERS: dict[ChatExportFormat, type[ChatExporter]] = {
    ChatExportFormat.PDF: PDFExporter,
    ChatExportFormat.MARKDOWN: MarkdownExporter,
}


def get_exporter(format: ChatExportFormat) -> ChatExporter:
    """Factory function to get the appropriate exporter for a format.

    Args:
        format: The export format (pdf or markdown)

    Returns:
        An instance of the appropriate ChatExporter

    Raises:
        InvalidExportFormatError: If format is not supported
    """
    exporter_class = _EXPORTERS.get(format)
    if exporter_class is None:
        raise InvalidExportFormatError(str(format))
    return exporter_class()


__all__ = [
    "ChatExporter",
    "ExportMetadata",
    "get_exporter",
    "MarkdownExporter",
    "PDFExporter",
]
