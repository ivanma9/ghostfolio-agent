import re
from dataclasses import dataclass, field

# Investment advice patterns (case-insensitive)
_ADVICE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\byou should (buy|sell|invest|trade|hold)\b",
        r"\bI recommend (buying|selling|investing|trading|holding)\b",
        r"\bI suggest (buying|selling|investing|trading|holding)\b",
        r"\bI advise (you to )?(buy|sell|invest|trade|hold)\b",
        r"\bmy recommendation is to (buy|sell|invest|trade|hold)\b",
        r"\byou (need|ought|must) to (buy|sell|invest|trade|hold)\b",
        r"\b(definitely|absolutely) (buy|sell|invest in|trade)\b",
    ]
]

# Performance/returns topics that warrant a disclaimer
_PERFORMANCE_KEYWORDS = [
    "return", "returns", "performance", "gain", "gains", "loss", "losses",
    "profit", "appreciation", "growth", "yield", "outperform", "underperform",
    "beat the market", "annualized",
]

_DISCLAIMER_TEXT = (
    "Note: Past performance does not guarantee future results. "
    "This is not financial advice."
)

# Paper trade pattern: "buy" or "sell" actions
_PAPER_TRADE_BUY_RE = re.compile(r'\b(buy|bought|purchasing)\b', re.IGNORECASE)


@dataclass
class DomainConstraintResult:
    passes: bool
    confidence: str  # "high", "medium", "low"
    violations: list[str] = field(default_factory=list)


def check_domain_constraints(
    response_text: str,
    tool_outputs: list[str],
    portfolio_value: float | None = None,
) -> DomainConstraintResult:
    """Enforce financial domain rules. Pure string matching."""
    violations: list[str] = []
    response_lower = response_text.lower()

    # --- Investment advice detection ---
    for pattern in _ADVICE_PATTERNS:
        match = pattern.search(response_text)
        if match:
            violations.append(
                f"Investment advice detected: \"{match.group()}\""
            )

    # --- Disclaimer check for performance topics ---
    discusses_performance = any(kw in response_lower for kw in _PERFORMANCE_KEYWORDS)
    has_disclaimer = any(
        phrase in response_lower
        for phrase in [
            "not financial advice",
            "past performance",
            "does not guarantee",
            "consult a financial",
            "not a recommendation",
            "for informational purposes",
        ]
    )
    if discusses_performance and not has_disclaimer:
        violations.append("Response discusses performance without disclaimer")

    # --- Large paper trade detection ---
    if portfolio_value and portfolio_value > 0:
        for output in tool_outputs:
            # Look for paper trade results with large dollar amounts
            total_match = re.search(r'total.*?\$([0-9,]+\.?\d*)', output, re.IGNORECASE)
            if total_match:
                trade_value = float(total_match.group(1).replace(",", ""))
                ratio = trade_value / portfolio_value
                if ratio > 0.5:
                    violations.append(
                        f"Large paper trade: ${trade_value:,.2f} is "
                        f"{ratio:.0%} of portfolio value ${portfolio_value:,.2f}"
                    )

    # --- Rapid-fire paper trade detection ---
    buy_count = 0
    for output in tool_outputs:
        if "paper trade" in output.lower() or "simulated" in output.lower():
            if _PAPER_TRADE_BUY_RE.search(output):
                buy_count += 1
    if buy_count > 3:
        violations.append(
            f"Rapid-fire trading: {buy_count} buy trades in a single turn"
        )

    passes = len(violations) == 0
    if passes:
        confidence = "high"
    elif len(violations) <= 1:
        confidence = "medium"
    else:
        confidence = "low"

    return DomainConstraintResult(
        passes=passes,
        confidence=confidence,
        violations=violations,
    )


def needs_disclaimer(response_text: str) -> bool:
    """Check if the response discusses performance but lacks a disclaimer."""
    response_lower = response_text.lower()
    discusses_performance = any(kw in response_lower for kw in _PERFORMANCE_KEYWORDS)
    has_disclaimer = any(
        phrase in response_lower
        for phrase in [
            "not financial advice",
            "past performance",
            "does not guarantee",
            "consult a financial",
            "not a recommendation",
            "for informational purposes",
        ]
    )
    return discusses_performance and not has_disclaimer


def get_disclaimer() -> str:
    """Return the standard financial disclaimer text."""
    return _DISCLAIMER_TEXT
