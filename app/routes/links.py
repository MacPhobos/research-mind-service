"""Link extraction REST endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.schemas.links import ExtractLinksRequest, ExtractedLinksResponse, ExtractedLinkSchema, CategorizedLinksSchema
from app.services.link_extractor import LinkExtractor, LinkExtractionError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/content", tags=["content"])


@router.post("/extract-links", response_model=ExtractedLinksResponse)
async def extract_links(request: ExtractLinksRequest) -> ExtractedLinksResponse:
    """Extract and categorize links from a web page.

    Fetches the specified URL and extracts all links, categorizing them by
    their source element (main content, navigation, sidebar, footer, other).

    Args:
        request: Contains the URL to extract links from and options.

    Returns:
        ExtractedLinksResponse with categorized links and metadata.

    Raises:
        HTTPException: 400 if URL is invalid or extraction fails.
    """
    extractor = LinkExtractor()

    try:
        # Convert HttpUrl to string for the extractor
        url_str = str(request.url)
        result = await extractor.extract(url_str, include_external=request.include_external)

        # Convert service result to response schema
        return ExtractedLinksResponse(
            source_url=result.source_url,
            page_title=result.page_title,
            extracted_at=result.extracted_at,
            link_count=result.link_count,
            categories=CategorizedLinksSchema(
                main_content=[
                    ExtractedLinkSchema(
                        url=link.url,
                        text=link.text or None,
                        is_external=link.is_external,
                        source_element=link.source_element,
                    )
                    for link in result.categories.main_content
                ],
                navigation=[
                    ExtractedLinkSchema(
                        url=link.url,
                        text=link.text or None,
                        is_external=link.is_external,
                        source_element=link.source_element,
                    )
                    for link in result.categories.navigation
                ],
                sidebar=[
                    ExtractedLinkSchema(
                        url=link.url,
                        text=link.text or None,
                        is_external=link.is_external,
                        source_element=link.source_element,
                    )
                    for link in result.categories.sidebar
                ],
                footer=[
                    ExtractedLinkSchema(
                        url=link.url,
                        text=link.text or None,
                        is_external=link.is_external,
                        source_element=link.source_element,
                    )
                    for link in result.categories.footer
                ],
                other=[
                    ExtractedLinkSchema(
                        url=link.url,
                        text=link.text or None,
                        is_external=link.is_external,
                        source_element=link.source_element,
                    )
                    for link in result.categories.other
                ],
            ),
        )

    except LinkExtractionError as e:
        # Determine error code based on cause
        error_code = "EXTRACTION_FAILED"
        if e.cause is not None:
            cause_type = type(e.cause).__name__
            if "Timeout" in cause_type:
                error_code = "TIMEOUT"

        logger.warning("Link extraction failed for %s: %s", e.url, str(e))
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": error_code,
                    "message": str(e),
                }
            },
        )
    except ValidationError as e:
        logger.warning("Invalid URL provided: %s", str(e))
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_URL",
                    "message": "Invalid URL format",
                }
            },
        )
