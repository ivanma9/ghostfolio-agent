import re
from dataclasses import dataclass, field

from ghostfolio_agent.clients.ghostfolio import GhostfolioClient


@dataclass
class VerificationResult:
    is_verified: bool
    confidence: str  # "high", "medium", "low"
    discrepancies: list[str] = field(default_factory=list)
    details: str = ""


async def verify_numerical_accuracy(
    response_text: str,
    client: GhostfolioClient,
    tolerance: float = 0.02,  # 2% tolerance for market price fluctuations
) -> VerificationResult:
    """Verify that numerical values in the agent's response match Ghostfolio data."""
    discrepancies = []

    # Fetch actual portfolio data
    try:
        data = await client.get_portfolio_holdings()
    except Exception as e:
        return VerificationResult(
            is_verified=False,
            confidence="low",
            discrepancies=[f"Could not fetch portfolio data: {e}"],
            details="Verification skipped due to API error",
        )

    holdings = data.get("holdings", [])
    if isinstance(holdings, dict):
        holdings = list(holdings.values())

    # Build lookup of actual values keyed by symbol
    actual: dict[str, dict] = {}
    for h in holdings:
        symbol = h.get("symbol", "")
        if not symbol:
            continue
        actual[symbol] = {
            "value": h.get("valueInBaseCurrency", 0) or 0,
            "quantity": h.get("quantity", 0) or 0,
            "price": h.get("marketPrice", 0) or 0,
            # allocationInPercentage is a fraction (0–1); multiply by 100 for %
            "allocation": (h.get("allocationInPercentage", 0) or 0) * 100,
        }

    if not actual:
        # No holdings to verify against — treat as unverifiable but not an error
        return VerificationResult(
            is_verified=True,
            confidence="medium",
            discrepancies=[],
            details="No holdings returned from API; numerical verification skipped",
        )

    # ------------------------------------------------------------------
    # Cross-reference dollar amounts mentioned near each symbol
    # Pattern: <SYMBOL> ... $1,234.56  (up to ~120 chars after the symbol)
    # ------------------------------------------------------------------
    for symbol, vals in actual.items():
        # Only check symbols that are actually mentioned in the response
        if symbol not in response_text:
            continue

        pattern = re.compile(
            rf'{re.escape(symbol)}[^$\n]{{0,120}}\$([0-9,]+\.?\d*)',
            re.IGNORECASE,
        )
        for match in pattern.findall(response_text):
            reported = float(match.replace(",", ""))

            # A reported value is acceptable if it is within tolerance of:
            #   • the holding's total value in base currency
            #   • the current market price per share
            #   • quantity × price  (same as value for most cases, but kept explicit)
            known_amounts = [
                vals["value"],
                vals["price"],
                vals["quantity"] * vals["price"],
            ]
            if any(_within_tolerance(reported, known, tolerance) for known in known_amounts):
                continue  # value checks out

            # Be lenient: only flag amounts above $100 to avoid noise from
            # small rounding differences on fractional shares / FX rates
            if reported > 100:
                discrepancies.append(
                    f"{symbol}: reported ${reported:,.2f} doesn't match "
                    f"current value ${vals['value']:,.2f} "
                    f"or price ${vals['price']:,.2f}"
                )

    # ------------------------------------------------------------------
    # Cross-reference percentage allocations mentioned near each symbol
    # Match standalone percentages like "12.9%" — must have at least one
    # digit before the decimal to avoid matching partial numbers from
    # dollar amounts like "$3,539.25"
    # ------------------------------------------------------------------
    for symbol, vals in actual.items():
        if symbol not in response_text:
            continue
        if vals["allocation"] == 0:
            continue

        # Find all standalone percentage values (e.g., "12.9%", "24.7%")
        # that appear on the same line as the symbol
        for line in response_text.split("\n"):
            if symbol not in line:
                continue
            # Match numbers immediately followed by % (e.g., "12.9%")
            # but not preceded by $ or digits (to avoid "$3,539.25|" artifacts)
            pct_matches = re.findall(r'(?<!\$)(?<!\d)(\d{1,3}\.\d+)%', line)
            for match in pct_matches:
                reported_pct = float(match)
                # Skip values that look like prices or quantities, not allocations
                if reported_pct > 100:
                    continue
                if not _within_tolerance(reported_pct, vals["allocation"], tolerance):
                    discrepancies.append(
                        f"{symbol}: reported allocation {reported_pct:.1f}% doesn't match "
                        f"actual {vals['allocation']:.1f}%"
                    )

    # ------------------------------------------------------------------
    # Build result
    # ------------------------------------------------------------------
    if not discrepancies:
        return VerificationResult(
            is_verified=True,
            confidence="high",
            discrepancies=[],
            details="All numerical values verified against Ghostfolio data",
        )

    return VerificationResult(
        is_verified=False,
        confidence="medium" if len(discrepancies) <= 2 else "low",
        discrepancies=discrepancies,
        details=f"Found {len(discrepancies)} discrepanc{'y' if len(discrepancies) == 1 else 'ies'}",
    )


def _within_tolerance(reported: float, actual: float, tolerance: float) -> bool:
    """Return True if *reported* is within *tolerance* fraction of *actual*."""
    if actual == 0:
        return reported == 0
    return abs(reported - actual) / abs(actual) <= tolerance
