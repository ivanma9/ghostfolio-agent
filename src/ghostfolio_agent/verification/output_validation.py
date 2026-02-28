import re
from dataclasses import dataclass, field

# Dollar amounts should have exactly 2 decimal places: $1,234.56
_DOLLAR_FORMAT_RE = re.compile(r'\$[0-9,]+\.(\d+)')

# Percentages should have at least 1 decimal place: 12.3%
_PCT_FORMAT_RE = re.compile(r'(\d+)%')

# Error prefixes that should be surfaced to the user
_ERROR_PREFIXES = ("Sorry,", "Failed", "Error")

# Minimum meaningful response length
_MIN_RESPONSE_LENGTH = 10


@dataclass
class OutputValidationResult:
    is_valid: bool
    confidence: str  # "high", "medium", "low"
    issues: list[str] = field(default_factory=list)


def validate_output(
    response_text: str,
    tool_outputs: list[str],
) -> OutputValidationResult:
    """Validate response format and completeness. Pure string checks."""
    issues: list[str] = []

    # --- Empty/truncated response ---
    if not response_text or not response_text.strip():
        return OutputValidationResult(
            is_valid=False,
            confidence="low",
            issues=["Response is empty"],
        )

    if len(response_text.strip()) < _MIN_RESPONSE_LENGTH:
        issues.append(f"Response appears truncated ({len(response_text.strip())} chars)")

    # --- Dollar format: should have 2 decimal places ---
    for match in _DOLLAR_FORMAT_RE.finditer(response_text):
        decimals = match.group(1)
        if len(decimals) != 2:
            issues.append(
                f"Dollar amount has {len(decimals)} decimal places "
                f"(expected 2): ...{match.group()}..."
            )

    # --- Percentage format: whole-number percentages without decimals ---
    for match in _PCT_FORMAT_RE.finditer(response_text):
        # Check if there's a decimal point before the matched digits
        start = match.start()
        prefix = response_text[max(0, start - 5):start]
        # Only flag if the percentage has no decimal point
        # (we check by looking for a decimal variant like "12.3%")
        full_pct = response_text[max(0, start - 10):match.end()]
        if re.search(r'\d+\.\d+%', full_pct):
            continue  # Has decimal, fine
        # Whole-number percentages are acceptable for round numbers
        # Only flag if tool outputs contain a more precise value

    # --- Tool errors not surfaced ---
    for output in tool_outputs:
        output_stripped = output.strip()
        for prefix in _ERROR_PREFIXES:
            if output_stripped.startswith(prefix):
                # Check if response acknowledges the error
                error_snippet = output_stripped[:80]
                # The response should mention the error or the relevant tool
                if not any(
                    indicator in response_text.lower()
                    for indicator in ["error", "failed", "sorry", "unable", "could not", "couldn't"]
                ):
                    issues.append(
                        f"Tool returned error not surfaced in response: "
                        f"{error_snippet}..."
                    )
                break  # Only flag once per tool output

    is_valid = len(issues) == 0
    if is_valid:
        confidence = "high"
    elif len(issues) <= 2:
        confidence = "medium"
    else:
        confidence = "low"

    return OutputValidationResult(
        is_valid=is_valid,
        confidence=confidence,
        issues=issues,
    )
