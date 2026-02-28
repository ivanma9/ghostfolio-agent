import pytest
from unittest.mock import AsyncMock, patch

from ghostfolio_agent.verification.pipeline import (
    PipelineResult,
    run_verification_pipeline,
)
from ghostfolio_agent.verification.numerical import VerificationResult


@pytest.fixture
def mock_numerical():
    """Mock the async numerical verifier."""
    with patch(
        "ghostfolio_agent.verification.pipeline.verify_numerical_accuracy",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = VerificationResult(
            is_verified=True,
            confidence="high",
            discrepancies=[],
            details="All verified",
        )
        yield mock


class TestVerificationPipeline:
    @pytest.mark.asyncio
    async def test_clean_response(self, mock_numerical):
        """Clean response should get high confidence and no modifications."""
        result = await run_verification_pipeline(
            response_text="Your AAPL position is worth $5,000.00 in your portfolio.",
            tool_outputs=["AAPL: value $5,000.00, quantity 25"],
            client=AsyncMock(),
        )
        assert result.overall_confidence == "high"
        assert result.all_issues == []
        assert "Warning" not in result.response_text

    @pytest.mark.asyncio
    async def test_hallucination_appends_note(self, mock_numerical):
        """Ungrounded symbols should append a note to the response."""
        result = await run_verification_pipeline(
            response_text="Your TSLA and AAPL positions are doing well.",
            tool_outputs=["AAPL: value $5,000.00"],
            client=AsyncMock(),
        )
        assert "TSLA" in result.response_text
        assert "could not be verified" in result.response_text

    @pytest.mark.asyncio
    async def test_investment_advice_prepends_disclaimer(self, mock_numerical):
        """Investment advice should prepend a disclaimer."""
        result = await run_verification_pipeline(
            response_text="Based on the data, you should buy more AAPL.",
            tool_outputs=["AAPL: value $5,000.00"],
            client=AsyncMock(),
        )
        assert result.response_text.startswith("*")
        assert "not financial advice" in result.response_text.lower()

    @pytest.mark.asyncio
    async def test_low_confidence_appends_warning(self, mock_numerical):
        """Low overall confidence should append a warning."""
        mock_numerical.return_value = VerificationResult(
            is_verified=False,
            confidence="low",
            discrepancies=["AAPL: mismatch", "NVDA: mismatch", "MSFT: mismatch"],
            details="3 discrepancies",
        )
        result = await run_verification_pipeline(
            response_text="Your portfolio has several positions worth a lot.",
            tool_outputs=["AAPL: $5,000.00"],
            client=AsyncMock(),
        )
        assert result.overall_confidence == "low"
        assert "could not be fully verified" in result.response_text

    @pytest.mark.asyncio
    async def test_worst_case_confidence(self, mock_numerical):
        """Overall confidence is the worst across all verifiers."""
        mock_numerical.return_value = VerificationResult(
            is_verified=True,
            confidence="high",
            discrepancies=[],
            details="OK",
        )
        # Trigger hallucination (medium confidence) by mentioning ungrounded symbols
        result = await run_verification_pipeline(
            response_text="TSLA is performing well in your portfolio.",
            tool_outputs=["AAPL: value $5,000.00"],
            client=AsyncMock(),
        )
        # Hallucination verifier returns medium for 1 ungrounded symbol
        assert result.overall_confidence in ("medium", "low")

    @pytest.mark.asyncio
    async def test_no_client_skips_numerical(self, mock_numerical):
        """When client is None, numerical verification is skipped."""
        result = await run_verification_pipeline(
            response_text="Your AAPL position is worth $5,000.00.",
            tool_outputs=["AAPL: value $5,000.00"],
            client=None,
        )
        mock_numerical.assert_not_called()
        assert result.numerical is None

    @pytest.mark.asyncio
    async def test_performance_disclaimer_appended(self, mock_numerical):
        """Performance discussion without disclaimer gets one appended."""
        result = await run_verification_pipeline(
            response_text="Your portfolio return this year is 15.3%.",
            tool_outputs=["Portfolio performance: 15.3%"],
            client=AsyncMock(),
        )
        assert "not financial advice" in result.response_text.lower()

    @pytest.mark.asyncio
    async def test_all_verifier_results_populated(self, mock_numerical):
        """All per-verifier results should be populated."""
        result = await run_verification_pipeline(
            response_text="Your AAPL position looks good.",
            tool_outputs=["AAPL: value $5,000.00"],
            client=AsyncMock(),
        )
        assert result.numerical is not None
        assert result.hallucination is not None
        assert result.output_validation is not None
        assert result.domain_constraints is not None

    @pytest.mark.asyncio
    async def test_issues_aggregated(self, mock_numerical):
        """Issues from all verifiers should be aggregated."""
        mock_numerical.return_value = VerificationResult(
            is_verified=False,
            confidence="medium",
            discrepancies=["AAPL: price mismatch"],
            details="1 discrepancy",
        )
        # Also trigger domain constraint violation
        result = await run_verification_pipeline(
            response_text="You should buy AAPL, its returns have been excellent.",
            tool_outputs=["AAPL: value $5,000.00"],
            client=AsyncMock(),
        )
        # Should have both numerical and domain constraint issues
        assert len(result.all_issues) >= 2
