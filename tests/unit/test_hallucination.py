import pytest

from ghostfolio_agent.verification.hallucination import (
    HallucinationResult,
    detect_hallucinations,
)


class TestDetectHallucinations:
    def test_grounded_symbols(self):
        """Symbols that appear in tool outputs should not be flagged."""
        result = detect_hallucinations(
            response_text="Your AAPL position is worth $5,000.00",
            tool_outputs=["AAPL: value $5,000.00, quantity 25"],
        )
        assert not result.has_hallucinations
        assert result.confidence == "high"
        assert result.ungrounded_symbols == []
        assert result.ungrounded_numbers == []

    def test_ungrounded_symbol(self):
        """Symbol not in any tool output should be flagged."""
        result = detect_hallucinations(
            response_text="Your TSLA position is growing fast",
            tool_outputs=["AAPL: value $5,000.00"],
        )
        assert result.has_hallucinations
        assert "TSLA" in result.ungrounded_symbols

    def test_common_words_filtered(self):
        """Common English words like I, A, THE should not be treated as tickers."""
        result = detect_hallucinations(
            response_text="I think THE AAPL stock IS A good BUY",
            tool_outputs=["AAPL: value $5,000.00"],
        )
        assert not result.has_hallucinations
        assert result.ungrounded_symbols == []

    def test_ungrounded_dollar_amount(self):
        """Dollar amounts > $100 not in tool outputs should be flagged."""
        result = detect_hallucinations(
            response_text="Your portfolio is worth $999,999.00",
            tool_outputs=["Total value: $50,000.00"],
        )
        assert result.has_hallucinations
        assert 999999.0 in result.ungrounded_numbers

    def test_small_dollar_amounts_ignored(self):
        """Dollar amounts <= $100 are not checked."""
        result = detect_hallucinations(
            response_text="The fee was $5.00",
            tool_outputs=["No fee information available"],
        )
        assert not result.has_hallucinations

    def test_grounded_dollar_amount(self):
        """Dollar amounts that appear in tool outputs should pass."""
        result = detect_hallucinations(
            response_text="Your AAPL is worth $5,000.00",
            tool_outputs=["AAPL value: $5,000.00"],
        )
        assert not result.has_hallucinations

    def test_empty_tool_outputs(self):
        """No tool outputs → can't verify, low confidence but no hallucinations flagged."""
        result = detect_hallucinations(
            response_text="AAPL is worth $10,000.00",
            tool_outputs=[],
        )
        assert not result.has_hallucinations
        assert result.confidence == "low"

    def test_multiple_ungrounded_items_low_confidence(self):
        """Many ungrounded items → low confidence."""
        result = detect_hallucinations(
            response_text="TSLA MSFT GOOG AMZN are all doing well at $500.00 and $600.00",
            tool_outputs=["AAPL: value $100.00"],
        )
        assert result.has_hallucinations
        assert result.confidence == "low"

    def test_financial_abbreviations_filtered(self):
        """Common financial terms like USD, ETF, IPO should be filtered."""
        result = detect_hallucinations(
            response_text="Your USD denominated ETF position in AAPL",
            tool_outputs=["AAPL: value $5,000.00"],
        )
        assert not result.has_hallucinations
