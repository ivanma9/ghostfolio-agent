import re
from dataclasses import dataclass, field

import structlog

# Common English words that look like ticker symbols

logger = structlog.get_logger()
_COMMON_WORDS = frozenset({
    "I", "A", "THE", "TO", "IN", "IS", "IT", "OF", "ON", "AT", "BY", "OR",
    "AN", "AS", "IF", "SO", "UP", "DO", "GO", "NO", "AM", "BE", "HE", "ME",
    "MY", "US", "WE", "ALL", "AND", "ARE", "BUT", "CAN", "FOR", "GET", "HAS",
    "HAD", "HER", "HIM", "HIS", "HOW", "ITS", "LET", "MAY", "NEW", "NOT",
    "NOW", "OLD", "OUR", "OUT", "OWN", "SAY", "SHE", "TOO", "USE", "WAY",
    "WHO", "BOY", "DID", "ANY", "DAY", "FEW", "GOT", "WAS", "SET", "TOP",
    "RUN", "RED", "SEE", "YES", "YET", "BIG", "END", "FAR", "LOW", "PUT",
    "NET", "PER", "TWO", "TEN", "ALSO", "BACK", "BEEN", "CALL", "CAME",
    "COME", "EACH", "EVEN", "FIND", "FIVE", "FOUR", "FROM", "GIVE", "GOOD",
    "HAVE", "HERE", "HIGH", "JUST", "KEEP", "KNOW", "LAST", "LONG", "LOOK",
    "MADE", "MAKE", "MANY", "MORE", "MOST", "MUCH", "MUST", "NAME", "NEXT",
    "ONLY", "OVER", "PART", "SAID", "SAME", "SOME", "SUCH", "TAKE", "THAN",
    "THAT", "THEM", "THEN", "THIS", "TIME", "VERY", "WANT", "WELL", "WENT",
    "WERE", "WHAT", "WHEN", "WILL", "WITH", "WORK", "YEAR", "YOUR", "ZERO",
    "ALSO", "INTO", "LIKE", "LINE", "REAL", "FREE", "FULL", "HALF", "HELP",
    "HOME", "LESS", "LIFE", "LIVE", "MOVE", "NEAR", "NEED", "ONCE", "OPEN",
    "PLAY", "SELF", "SHOW", "SIDE", "TELL", "TRUE", "TURN", "UPON", "USED",
    "FUND", "BEST", "BOTH", "DOWN", "EVER", "GOES", "HARD", "IDEA", "KIND",
    "LEFT", "RATE", "RISK", "SURE", "UNIT",
    # Common financial terms that are not tickers
    "BUY", "SELL", "HOLD", "CALL", "NOTE", "GAIN", "LOSS", "CASH", "DEBT",
    "BOND", "COST", "PAYS", "PAID", "FEES", "PLAN",
    # Common abbreviations
    "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "ETF", "IPO", "CEO", "CFO",
    "API", "USA", "GDP", "CPI", "SEC", "FED", "FAQ", "PDF",
})

# Regex for uppercase letter sequences that look like ticker symbols (1-5 chars)
_TICKER_RE = re.compile(r'\b([A-Z]{1,5})\b')

# Dollar amounts > $100
_DOLLAR_RE = re.compile(r'\$([0-9,]+\.?\d*)')


@dataclass
class HallucinationResult:
    has_hallucinations: bool
    confidence: str  # "high", "medium", "low"
    ungrounded_symbols: list[str] = field(default_factory=list)
    ungrounded_numbers: list[float] = field(default_factory=list)


def detect_hallucinations(
    response_text: str,
    tool_outputs: list[str],
) -> HallucinationResult:
    """Detect LLM claims not grounded in tool outputs. Pure string comparison."""
    if not tool_outputs:
        # No tool outputs to check against — can't verify
        return HallucinationResult(
            has_hallucinations=False,
            confidence="low",
        )

    combined_tool_text = " ".join(tool_outputs)

    # --- Check ticker symbols ---
    response_symbols = set(_TICKER_RE.findall(response_text))
    # Filter out common English words
    response_symbols -= _COMMON_WORDS

    ungrounded_symbols = []
    for sym in sorted(response_symbols):
        if sym not in combined_tool_text:
            ungrounded_symbols.append(sym)

    # --- Check dollar amounts > $100 ---
    ungrounded_numbers = []
    for match in _DOLLAR_RE.findall(response_text):
        value = float(match.replace(",", ""))
        if value <= 100:
            continue
        # Check if this number appears in any tool output
        if match not in combined_tool_text and match.replace(",", "") not in combined_tool_text:
            ungrounded_numbers.append(value)

    has_hallucinations = bool(ungrounded_symbols or ungrounded_numbers)

    if has_hallucinations:
        confidence = "low" if (len(ungrounded_symbols) + len(ungrounded_numbers)) > 3 else "medium"
    else:
        confidence = "high"

    return HallucinationResult(
        has_hallucinations=has_hallucinations,
        confidence=confidence,
        ungrounded_symbols=ungrounded_symbols,
        ungrounded_numbers=ungrounded_numbers,
    )
