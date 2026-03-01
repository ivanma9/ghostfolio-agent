from dataclasses import dataclass, field

import structlog

from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.verification.hallucination import (
    HallucinationResult,
    detect_hallucinations,
)
from ghostfolio_agent.verification.numerical import (
    VerificationResult,
    verify_numerical_accuracy,
)
from ghostfolio_agent.verification.output_validation import (
    OutputValidationResult,
    validate_output,
)
from ghostfolio_agent.verification.domain_constraints import (
    DomainConstraintResult,
    check_domain_constraints,
    get_disclaimer,
    needs_disclaimer,
)

logger = structlog.get_logger()

# Confidence ranking for worst-case computation
_CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}


@dataclass
class PipelineResult:
    overall_confidence: str
    response_text: str
    all_issues: list[str] = field(default_factory=list)
    numerical: VerificationResult | None = None
    hallucination: HallucinationResult | None = None
    output_validation: OutputValidationResult | None = None
    domain_constraints: DomainConstraintResult | None = None


async def run_verification_pipeline(
    response_text: str,
    tool_outputs: list[str],
    client: GhostfolioClient | None = None,
    portfolio_value: float | None = None,
) -> PipelineResult:
    """Run all verifiers and return aggregated results with modified response text."""
    all_issues: list[str] = []
    confidences: list[str] = []
    modified_response = response_text

    # --- 1. Numerical accuracy (async, hits API) ---
    numerical_result = None
    if client and response_text:
        try:
            numerical_result = await verify_numerical_accuracy(response_text, client)
            logger.info("verification_numerical_complete", confidence=numerical_result.confidence)
        except Exception as e:
            logger.error("verification_numerical_failed", error=str(e))

    if numerical_result is not None:
        confidences.append(numerical_result.confidence)
        all_issues.extend(numerical_result.discrepancies)

    # --- 2. Hallucination detection (sync) ---
    hallucination_result = None
    try:
        hallucination_result = detect_hallucinations(response_text, tool_outputs)
        logger.info("verification_hallucination_complete", confidence=hallucination_result.confidence)
    except Exception as e:
        logger.error("verification_hallucination_failed", error=str(e))

    if hallucination_result is not None:
        confidences.append(hallucination_result.confidence)
        if hallucination_result.ungrounded_symbols:
            all_issues.append(
                f"Unverified symbols: {', '.join(hallucination_result.ungrounded_symbols)}"
            )
        if hallucination_result.ungrounded_numbers:
            nums = [f"${n:,.2f}" for n in hallucination_result.ungrounded_numbers]
            all_issues.append(f"Unverified amounts: {', '.join(nums)}")

    # --- 3. Output validation (sync) ---
    output_result = None
    try:
        output_result = validate_output(response_text, tool_outputs)
        logger.info("verification_output_complete", confidence=output_result.confidence)
    except Exception as e:
        logger.error("verification_output_failed", error=str(e))

    if output_result is not None:
        confidences.append(output_result.confidence)
        all_issues.extend(output_result.issues)

    # --- 4. Domain constraints (sync) ---
    domain_result = None
    try:
        domain_result = check_domain_constraints(
            response_text, tool_outputs, portfolio_value
        )
        logger.info("verification_domain_complete", confidence=domain_result.confidence)
    except Exception as e:
        logger.error("verification_domain_failed", error=str(e))

    if domain_result is not None:
        confidences.append(domain_result.confidence)
        all_issues.extend(domain_result.violations)

    # --- Compute overall confidence (worst-case) ---
    if confidences:
        overall = min(confidences, key=lambda c: _CONFIDENCE_RANK.get(c, 0))
    else:
        overall = "medium"

    # --- Make verification actionable: modify response ---

    # Prepend disclaimer if needed
    if domain_result is not None and not domain_result.passes:
        for v in domain_result.violations:
            if "advice" in v.lower():
                # Prepend disclaimer for investment advice
                modified_response = f"*{get_disclaimer()}*\n\n{modified_response}"
                break

    if needs_disclaimer(modified_response):
        modified_response = f"{modified_response}\n\n*{get_disclaimer()}*"

    # Append hallucination warning
    if hallucination_result is not None and hallucination_result.has_hallucinations:
        syms = hallucination_result.ungrounded_symbols
        if syms:
            modified_response += (
                f"\n\n> Note: The following references could not be verified "
                f"against tool data: {', '.join(syms)}"
            )

    # Append low-confidence warning
    if overall == "low":
        modified_response += (
            "\n\n> Warning: Some data in this response could not be fully verified."
        )

    logger.info(
        "verification_pipeline_complete",
        overall_confidence=overall,
        total_issues=len(all_issues),
    )

    return PipelineResult(
        overall_confidence=overall,
        response_text=modified_response,
        all_issues=all_issues,
        numerical=numerical_result,
        hallucination=hallucination_result,
        output_validation=output_result,
        domain_constraints=domain_result,
    )
