import pytest

from ghostfolio_agent.verification.domain_constraints import (
    DomainConstraintResult,
    check_domain_constraints,
    needs_disclaimer,
    get_disclaimer,
)


class TestDomainConstraints:
    def test_clean_response_passes(self):
        """Response without advice or performance topics passes."""
        result = check_domain_constraints(
            response_text="Your portfolio has 5 holdings across 3 sectors.",
            tool_outputs=[],
        )
        assert result.passes
        assert result.confidence == "high"

    def test_investment_advice_detected(self):
        """'you should buy' triggers advice detection."""
        result = check_domain_constraints(
            response_text="Based on the data, you should buy more AAPL shares.",
            tool_outputs=[],
        )
        assert not result.passes
        assert any("advice" in v.lower() for v in result.violations)

    def test_recommend_buying_detected(self):
        """'I recommend buying' triggers advice detection."""
        result = check_domain_constraints(
            response_text="I recommend buying NVDA given its momentum.",
            tool_outputs=[],
        )
        assert not result.passes

    def test_suggest_selling_detected(self):
        """'I suggest selling' triggers advice detection."""
        result = check_domain_constraints(
            response_text="I suggest selling your bonds.",
            tool_outputs=[],
        )
        assert not result.passes

    def test_performance_without_disclaimer(self):
        """Discussing returns without disclaimer should be flagged."""
        result = check_domain_constraints(
            response_text="Your portfolio return this year has been 15.3%.",
            tool_outputs=[],
        )
        assert not result.passes
        assert any("disclaimer" in v.lower() for v in result.violations)

    def test_performance_with_disclaimer(self):
        """Discussing returns with a disclaimer should pass."""
        result = check_domain_constraints(
            response_text=(
                "Your portfolio return this year has been 15.3%. "
                "Note: Past performance does not guarantee future results."
            ),
            tool_outputs=[],
        )
        assert result.passes

    def test_large_paper_trade_flagged(self):
        """Trade > 50% of portfolio value should be flagged."""
        result = check_domain_constraints(
            response_text="Paper trade executed.",
            tool_outputs=["Simulated BUY: total $60,000.00 of AAPL"],
            portfolio_value=100_000.0,
        )
        assert not result.passes
        assert any("large" in v.lower() for v in result.violations)

    def test_normal_paper_trade_passes(self):
        """Trade < 50% of portfolio should pass."""
        result = check_domain_constraints(
            response_text="Paper trade executed.",
            tool_outputs=["Simulated BUY: total $5,000.00 of AAPL"],
            portfolio_value=100_000.0,
        )
        assert result.passes

    def test_rapid_fire_trades_flagged(self):
        """More than 3 buy trades in one turn should be flagged."""
        tool_outputs = [
            "Paper trade simulated: bought 10 AAPL",
            "Paper trade simulated: bought 5 NVDA",
            "Paper trade simulated: bought 20 MSFT",
            "Paper trade simulated: bought 15 GOOG",
        ]
        result = check_domain_constraints(
            response_text="Executed 4 trades.",
            tool_outputs=tool_outputs,
        )
        assert not result.passes
        assert any("rapid" in v.lower() for v in result.violations)

    def test_needs_disclaimer_true(self):
        """needs_disclaimer returns True for performance text without disclaimer."""
        assert needs_disclaimer("Your returns have been great this year!")

    def test_needs_disclaimer_false_with_disclaimer(self):
        """needs_disclaimer returns False when disclaimer is present."""
        assert not needs_disclaimer(
            "Your returns were 10%. This is not financial advice."
        )

    def test_needs_disclaimer_false_no_performance(self):
        """needs_disclaimer returns False when no performance topics discussed."""
        assert not needs_disclaimer("You have 5 holdings in your portfolio.")

    def test_get_disclaimer_not_empty(self):
        """get_disclaimer returns non-empty string."""
        assert len(get_disclaimer()) > 10
