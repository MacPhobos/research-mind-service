"""Abstract base class for chat exporters.

Defines the interface that all chat exporter implementations must follow.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.chat_message import ChatMessage


@dataclass
class ExportMetadata:
    """Metadata to include in export."""

    session_name: str
    session_id: str
    export_date: datetime
    message_count: int
    include_timestamps: bool


class ChatExporter(ABC):
    """Abstract base class for chat exporters."""

    @property
    @abstractmethod
    def content_type(self) -> str:
        """MIME type for the export format."""
        pass

    @property
    @abstractmethod
    def file_extension(self) -> str:
        """File extension for the export format."""
        pass

    @abstractmethod
    def export(
        self,
        messages: list[ChatMessage],
        metadata: ExportMetadata | None,
    ) -> bytes:
        """Generate export content from chat messages.

        Args:
            messages: List of chat messages to export (ordered by created_at)
            metadata: Export metadata configuration (None to skip metadata header)

        Returns:
            Binary content of the export file

        Raises:
            ExportGenerationError: If export generation fails
        """
        pass

    def generate_filename(self, identifier: str) -> str:
        """Generate filename for the export.

        Args:
            identifier: Unique identifier for the export (e.g., session_id)

        Returns:
            Filename with timestamp and proper extension
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        # Use first 8 chars of identifier for brevity
        short_id = identifier[:8] if len(identifier) > 8 else identifier
        return f"chat-export-{short_id}-{timestamp}.{self.file_extension}"
