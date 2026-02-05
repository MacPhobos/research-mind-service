"""Markdown exporter for chat history.

Exports chat messages to GitHub-flavored Markdown format.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.chat_message import ChatRole
from app.services.export.base import ChatExporter, ExportMetadata

if TYPE_CHECKING:
    from app.models.chat_message import ChatMessage


class MarkdownExporter(ChatExporter):
    """Export chat history to Markdown format."""

    @property
    def content_type(self) -> str:
        """MIME type for Markdown."""
        return "text/markdown"

    @property
    def file_extension(self) -> str:
        """File extension for Markdown."""
        return "md"

    def export(
        self,
        messages: list[ChatMessage],
        metadata: ExportMetadata | None,
    ) -> bytes:
        """Generate Markdown export content.

        Args:
            messages: List of chat messages to export (ordered by created_at)
            metadata: Export metadata configuration (None to skip metadata header)

        Returns:
            UTF-8 encoded Markdown content
        """
        lines: list[str] = []

        # Header with metadata
        if metadata:
            lines.extend(
                [
                    f"# Chat Export: {metadata.session_name}",
                    "",
                    f"**Session ID**: `{metadata.session_id}`  ",
                    f"**Exported**: {metadata.export_date.strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
                    f"**Messages**: {metadata.message_count}",
                    "",
                    "---",
                    "",
                ]
            )

        # Messages
        for message in messages:
            role_label = (
                "**User**" if message.role == ChatRole.USER.value else "**Assistant**"
            )

            # Timestamp line
            if metadata and metadata.include_timestamps and message.created_at:
                timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                lines.append(f"### {role_label} ({timestamp})")
            else:
                lines.append(f"### {role_label}")

            lines.append("")

            # Message content (already markdown, preserve as-is)
            lines.append(message.content)
            lines.append("")
            lines.append("---")
            lines.append("")

        content = "\n".join(lines)
        return content.encode("utf-8")
