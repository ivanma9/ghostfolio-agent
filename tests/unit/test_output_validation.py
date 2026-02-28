import pytest

from ghostfolio_agent.verification.output_validation import (
    OutputValidationResult,
    validate_output,
)


class TestValidateOutput:
    def test_valid_response(self):
        """Clean response with proper formatting passes."""
        result = validate_output(
            response_text="Your portfolio has AAPL worth $5,000.00 with 12.5% allocation.",
            tool_outputs=["AAPL: $5,000.00"],
        )
        assert result.is_valid
        assert result.confidence == "high"

    def test_empty_response(self):
        """Empty response should fail."""
        result = validate_output(
            response_text="",
            tool_outputs=["AAPL: $5,000.00"],
        )
        assert not result.is_valid
        assert result.confidence == "low"
        assert any("empty" in issue.lower() for issue in result.issues)

    def test_truncated_response(self):
        """Very short response should be flagged."""
        result = validate_output(
            response_text="Hi",
            tool_outputs=[],
        )
        assert not result.is_valid
        assert any("truncated" in issue.lower() for issue in result.issues)

    def test_dollar_format_wrong_decimals(self):
        """Dollar amounts with wrong decimal places should be flagged."""
        result = validate_output(
            response_text="Your position is worth $5,000.5 today.",
            tool_outputs=[],
        )
        assert not result.is_valid
        assert any("decimal" in issue.lower() for issue in result.issues)

    def test_dollar_format_correct(self):
        """Dollar amounts with exactly 2 decimal places pass."""
        result = validate_output(
            response_text="Your position is worth $5,000.50 today, great job!",
            tool_outputs=[],
        )
        assert result.is_valid

    def test_tool_error_not_surfaced(self):
        """Tool errors not mentioned in response should be flagged."""
        result = validate_output(
            response_text="Your portfolio looks great with strong performance!",
            tool_outputs=["Sorry, could not fetch data for AAPL"],
        )
        assert not result.is_valid
        assert any("error" in issue.lower() for issue in result.issues)

    def test_tool_error_surfaced(self):
        """Tool errors acknowledged in response should pass."""
        result = validate_output(
            response_text="I was unable to fetch data for AAPL, sorry about that.",
            tool_outputs=["Sorry, could not fetch data for AAPL"],
        )
        assert result.is_valid

    def test_failed_tool_output(self):
        """Tool output starting with 'Failed' should be checked."""
        result = validate_output(
            response_text="Everything looks fine in your portfolio.",
            tool_outputs=["Failed to connect to the API"],
        )
        assert not result.is_valid

    def test_whitespace_only_response(self):
        """Whitespace-only response should be caught as empty."""
        result = validate_output(
            response_text="   \n\t  ",
            tool_outputs=[],
        )
        assert not result.is_valid
