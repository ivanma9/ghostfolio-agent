#!/usr/bin/env python3
"""
Eval runner for the ghostfolio-agent.

Usage:
    python tests/eval/run_evals.py [--url http://localhost:8000] [--dataset path/to/test_cases.json]

Each test case is sent to the agent's /api/chat endpoint. The runner checks:
  1. expected_tools     — tool names that must appear in the response's tool_calls list
  2. expected_output_contains     — strings that must be present in the response text (case-insensitive)
  3. expected_output_not_contains — strings that must NOT be present in the response text (case-insensitive)
"""

import argparse
import json
import sys
import uuid
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package is required. Install with: pip install requests")
    sys.exit(1)

DEFAULT_DATASET = Path(__file__).parent / "datasets" / "mvp_test_cases.json"
FULL_DATASET = Path(__file__).parent / "datasets" / "full_eval_suite.json"
DEFAULT_BASE_URL = "http://localhost:8000"


# ---------------------------------------------------------------------------
# Evaluation logic
# ---------------------------------------------------------------------------

def check_test_case(test_case: dict, base_url: str) -> dict:
    """
    Send the query to the agent and evaluate the response against expectations.

    Returns a result dict with keys:
        id, passed, failures, response, tool_calls
    """
    tc_id = test_case["id"]
    user_input = test_case["input"]
    expected_tools: list[str] = test_case.get("expected_tools", [])
    must_contain: list[str] = test_case.get("expected_output_contains", [])
    must_not_contain: list[str] = test_case.get("expected_output_not_contains", [])

    failures: list[str] = []
    response_text = ""
    actual_tools: list[str] = []

    # --- Send request ---
    try:
        resp = requests.post(
            f"{base_url}/api/chat",
            json={"message": user_input, "session_id": f"eval-{uuid.uuid4()}"},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        response_text = data.get("response", "")
        actual_tools = data.get("tool_calls", [])
    except requests.exceptions.ConnectionError:
        failures.append(f"Connection refused — is the server running at {base_url}?")
        return {
            "id": tc_id,
            "passed": False,
            "failures": failures,
            "response": response_text,
            "tool_calls": actual_tools,
        }
    except requests.exceptions.HTTPError as exc:
        failures.append(f"HTTP error: {exc}")
        return {
            "id": tc_id,
            "passed": False,
            "failures": failures,
            "response": response_text,
            "tool_calls": actual_tools,
        }
    except Exception as exc:  # noqa: BLE001
        failures.append(f"Unexpected error: {exc}")
        return {
            "id": tc_id,
            "passed": False,
            "failures": failures,
            "response": response_text,
            "tool_calls": actual_tools,
        }

    response_lower = response_text.lower()

    # --- Check 1: expected tools were called ---
    for tool in expected_tools:
        if tool not in actual_tools:
            failures.append(f"Expected tool '{tool}' was not called. Actual tools: {actual_tools}")

    # --- Check 2: response must contain these strings ---
    for phrase in must_contain:
        if phrase.lower() not in response_lower:
            failures.append(f"Response missing required string: '{phrase}'")

    # --- Check 3: response must NOT contain these strings ---
    for phrase in must_not_contain:
        if phrase.lower() in response_lower:
            failures.append(f"Response contains forbidden string: '{phrase}'")

    return {
        "id": tc_id,
        "passed": len(failures) == 0,
        "failures": failures,
        "response": response_text,
        "tool_calls": actual_tools,
    }


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"


def print_result(result: dict, test_case: dict) -> None:
    status = PASS if result["passed"] else FAIL
    category = test_case.get("category", "unknown")
    print(f"  [{status}] {result['id']}  ({category})")
    if not result["passed"]:
        for failure in result["failures"]:
            print(f"         - {failure}")
    print(f"         tools called : {result['tool_calls']}")
    # Truncate long responses for readability
    preview = result["response"][:120].replace("\n", " ")
    if len(result["response"]) > 120:
        preview += "..."
    print(f"         response     : {preview}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Run ghostfolio-agent evals")
    parser.add_argument(
        "--url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL of the running agent API (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET),
        help=f"Path to the test cases JSON file (default: {DEFAULT_DATASET})",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run the full 50-case eval suite instead of the golden-set",
    )
    parser.add_argument(
        "--category",
        default=None,
        help="Only run test cases matching this category (e.g. happy_path, edge_case, adversarial, multi_step)",
    )
    args = parser.parse_args()

    # --full overrides --dataset to use the full 50-case suite
    if args.full:
        dataset_path = FULL_DATASET
    else:
        dataset_path = Path(args.dataset)

    if not dataset_path.exists():
        print(f"ERROR: Dataset file not found: {dataset_path}")
        sys.exit(1)

    with dataset_path.open() as fh:
        test_cases = json.load(fh)

    # Optional category filter
    if args.category:
        test_cases = [tc for tc in test_cases if tc.get("category") == args.category]
        if not test_cases:
            print(f"ERROR: No test cases found for category '{args.category}'")
            sys.exit(1)

    print(f"\nGhostfolio Agent Eval Runner")
    print(f"  API  : {args.url}")
    print(f"  File : {dataset_path}")
    print(f"  Cases: {len(test_cases)}\n")
    print("=" * 60)

    results = []
    for tc in test_cases:
        result = check_test_case(tc, args.url)
        print_result(result, tc)
        results.append(result)

    # --- Summary ---
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    score_pct = int(passed / total * 100) if total else 0

    print("=" * 60)
    print(f"SCORE: {passed}/{total} passed ({score_pct}%)")

    # Breakdown by category
    categories: dict[str, dict[str, int]] = {}
    for r, tc in zip(results, test_cases):
        cat = tc.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"passed": 0, "total": 0}
        categories[cat]["total"] += 1
        if r["passed"]:
            categories[cat]["passed"] += 1

    print("\nBreakdown by category:")
    for cat, counts in sorted(categories.items()):
        cat_pct = int(counts["passed"] / counts["total"] * 100)
        print(f"  {cat:<20} {counts['passed']}/{counts['total']}  ({cat_pct}%)")

    print()
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
