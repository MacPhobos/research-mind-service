"""PDF exporter for chat history.

Uses weasyprint to convert HTML to PDF for styled document output.
"""

from __future__ import annotations

import html as html_lib
import re
from typing import TYPE_CHECKING

from app.exceptions import ExportGenerationError
from app.models.chat_message import ChatRole
from app.services.export.base import ChatExporter, ExportMetadata

if TYPE_CHECKING:
    from app.models.chat_message import ChatMessage

# Conditional import - weasyprint may not be installed
try:
    from weasyprint import CSS, HTML

    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False
    HTML = None  # type: ignore[misc, assignment]
    CSS = None  # type: ignore[misc, assignment]


class PDFExporter(ChatExporter):
    """Export chat history to PDF format."""

    CSS_STYLES = """
        @page {
            size: A4;
            margin: 2cm;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            font-size: 11pt;
            line-height: 1.5;
            color: #333;
        }
        h1 {
            font-size: 18pt;
            color: #1a1a1a;
            border-bottom: 2px solid #0066cc;
            padding-bottom: 0.5em;
            margin-bottom: 1em;
        }
        .metadata {
            font-size: 10pt;
            color: #666;
            margin-bottom: 2em;
        }
        .metadata p {
            margin: 0.2em 0;
        }
        .message {
            margin-bottom: 1.5em;
            page-break-inside: avoid;
        }
        .message-header {
            font-weight: bold;
            font-size: 11pt;
            margin-bottom: 0.5em;
            padding: 0.5em;
            border-radius: 4px;
        }
        .message-header.user {
            background-color: #e3f2fd;
            color: #1565c0;
        }
        .message-header.assistant {
            background-color: #f3e5f5;
            color: #7b1fa2;
        }
        .message-content {
            padding: 0.5em 1em;
            background-color: #fafafa;
            border-left: 3px solid #ddd;
            white-space: pre-wrap;
        }
        .timestamp {
            font-size: 9pt;
            color: #888;
            font-weight: normal;
        }
        hr {
            border: none;
            border-top: 1px solid #eee;
            margin: 1em 0;
        }
        code {
            background-color: #f5f5f5;
            padding: 0.2em 0.4em;
            border-radius: 3px;
            font-family: 'SF Mono', Monaco, Consolas, monospace;
            font-size: 10pt;
        }
        pre {
            background-color: #f5f5f5;
            padding: 1em;
            border-radius: 4px;
            overflow-x: auto;
            font-family: 'SF Mono', Monaco, Consolas, monospace;
            font-size: 10pt;
        }
    """

    @property
    def content_type(self) -> str:
        """MIME type for PDF."""
        return "application/pdf"

    @property
    def file_extension(self) -> str:
        """File extension for PDF."""
        return "pdf"

    def export(
        self,
        messages: list[ChatMessage],
        metadata: ExportMetadata | None,
    ) -> bytes:
        """Generate PDF export content.

        Args:
            messages: List of chat messages to export (ordered by created_at)
            metadata: Export metadata configuration (None to skip metadata header)

        Returns:
            PDF file content as bytes

        Raises:
            ExportGenerationError: If weasyprint is not available or PDF generation fails
        """
        if not WEASYPRINT_AVAILABLE:
            raise ExportGenerationError("PDF export requires weasyprint library")

        try:
            html_content = self._generate_html(messages, metadata)
            html_doc = HTML(string=html_content)
            css = CSS(string=self.CSS_STYLES)
            pdf_bytes = html_doc.write_pdf(stylesheets=[css])
            return pdf_bytes
        except ExportGenerationError:
            raise
        except Exception as e:
            raise ExportGenerationError(f"PDF generation failed: {e!s}")

    def _generate_html(
        self,
        messages: list[ChatMessage],
        metadata: ExportMetadata | None,
    ) -> str:
        """Generate HTML content for PDF conversion.

        Args:
            messages: List of chat messages to export
            metadata: Export metadata configuration

        Returns:
            HTML string ready for PDF conversion
        """
        lines: list[str] = [
            "<!DOCTYPE html>",
            "<html>",
            "<head><meta charset='utf-8'></head>",
            "<body>",
        ]

        # Header with metadata
        if metadata:
            lines.extend(
                [
                    f"<h1>Chat Export: {html_lib.escape(metadata.session_name)}</h1>",
                    "<div class='metadata'>",
                    f"<p><strong>Session ID:</strong> <code>{metadata.session_id}</code></p>",
                    f"<p><strong>Exported:</strong> {metadata.export_date.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>",
                    f"<p><strong>Messages:</strong> {metadata.message_count}</p>",
                    "</div>",
                    "<hr>",
                ]
            )

        # Messages
        for message in messages:
            role_class = "user" if message.role == ChatRole.USER.value else "assistant"
            role_label = "User" if message.role == ChatRole.USER.value else "Assistant"

            timestamp_html = ""
            if metadata and metadata.include_timestamps and message.created_at:
                timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                timestamp_html = f" <span class='timestamp'>({timestamp})</span>"

            # Escape content but preserve some markdown-like formatting
            content = html_lib.escape(message.content)
            # Simple code block handling (``` blocks)
            content = self._convert_code_blocks(content)
            # Simple inline code handling
            content = self._convert_inline_code(content)
            # Preserve line breaks
            content = content.replace("\n", "<br>")

            lines.extend(
                [
                    "<div class='message'>",
                    f"<div class='message-header {role_class}'>{role_label}{timestamp_html}</div>",
                    f"<div class='message-content'>{content}</div>",
                    "</div>",
                ]
            )

        lines.extend(
            [
                "</body>",
                "</html>",
            ]
        )

        return "\n".join(lines)

    def _convert_code_blocks(self, text: str) -> str:
        """Convert markdown code blocks to HTML pre tags.

        Args:
            text: HTML-escaped text with markdown code blocks

        Returns:
            Text with code blocks converted to <pre><code> tags
        """
        # Match ```language\ncode\n``` (note: text is already HTML-escaped)
        pattern = r"```(\w*)\n(.*?)\n```"
        return re.sub(pattern, r"<pre><code>\2</code></pre>", text, flags=re.DOTALL)

    def _convert_inline_code(self, text: str) -> str:
        """Convert markdown inline code to HTML code tags.

        Args:
            text: Text with markdown inline code

        Returns:
            Text with inline code converted to <code> tags
        """
        # Match `code`
        pattern = r"`([^`]+)`"
        return re.sub(pattern, r"<code>\1</code>", text)
