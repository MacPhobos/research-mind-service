"""Tests for base extraction classes."""

from __future__ import annotations

from app.services.extractors.base import ExtractionConfig, ExtractionResult


class TestExtractionConfig:
    """Test suite for ExtractionConfig dataclass."""

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        config = ExtractionConfig()

        assert config.timeout_seconds == 30
        assert config.max_retries == 3
        assert config.max_content_size_mb == 50
        assert config.min_content_length == 100
        assert config.retry_with_js is True
        assert config.playwright_headless is True
        assert "research-mind" in config.user_agent

    def test_custom_values(self) -> None:
        """Test that custom values can be set."""
        config = ExtractionConfig(
            timeout_seconds=60,
            max_retries=5,
            max_content_size_mb=100,
            min_content_length=200,
            retry_with_js=False,
            playwright_headless=False,
            user_agent="custom-agent/1.0",
        )

        assert config.timeout_seconds == 60
        assert config.max_retries == 5
        assert config.max_content_size_mb == 100
        assert config.min_content_length == 200
        assert config.retry_with_js is False
        assert config.playwright_headless is False
        assert config.user_agent == "custom-agent/1.0"

    def test_is_frozen(self) -> None:
        """Test that config is immutable (frozen dataclass)."""
        config = ExtractionConfig()

        # Should raise FrozenInstanceError or similar
        try:
            config.timeout_seconds = 60  # type: ignore[misc]
            assert False, "Expected frozen dataclass to raise error"
        except AttributeError:
            pass  # Expected behavior


class TestExtractionResult:
    """Test suite for ExtractionResult dataclass."""

    def test_basic_creation(self) -> None:
        """Test basic result creation."""
        result = ExtractionResult(
            content="This is test content with multiple words.",
            title="Test Title",
        )

        assert result.content == "This is test content with multiple words."
        assert result.title == "Test Title"

    def test_word_count_auto_calculated(self) -> None:
        """Test that word count is automatically calculated."""
        content = "One two three four five"
        result = ExtractionResult(content=content, title="Test")

        assert result.word_count == 5

    def test_word_count_can_be_overridden(self) -> None:
        """Test that word count can be explicitly set."""
        result = ExtractionResult(
            content="One two three",
            title="Test",
            word_count=100,  # Override auto-calculation
        )

        # When word_count is explicitly set to non-zero, it should be preserved
        # But our implementation recalculates if word_count == 0
        # So non-zero values are preserved
        assert result.word_count == 100

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        result = ExtractionResult(content="Test content", title="Test")

        assert result.extraction_method == ""
        assert result.extraction_time_ms == 0.0
        assert result.warnings == []

    def test_full_result(self) -> None:
        """Test result with all fields populated."""
        result = ExtractionResult(
            content="Full content here",
            title="Full Title",
            word_count=3,
            extraction_method="trafilatura",
            extraction_time_ms=45.67,
            warnings=["Warning 1", "Warning 2"],
        )

        assert result.content == "Full content here"
        assert result.title == "Full Title"
        assert result.word_count == 3
        assert result.extraction_method == "trafilatura"
        assert result.extraction_time_ms == 45.67
        assert len(result.warnings) == 2

    def test_empty_content_word_count(self) -> None:
        """Test word count for empty content."""
        result = ExtractionResult(content="", title="Empty")

        # Empty string split gives [''], which has length 1
        # This is Python's behavior: "".split() returns []
        assert result.word_count == 0

    def test_warnings_list_is_mutable(self) -> None:
        """Test that warnings list can be modified after creation."""
        result = ExtractionResult(content="Test", title="Test")

        result.warnings.append("New warning")
        assert "New warning" in result.warnings
