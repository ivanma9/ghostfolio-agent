#!/usr/bin/env python3
"""
Eval runner for the ghostfolio-agent.

Usage:
    python tests/eval/run_evals.py                       # run golden set (20 cases, default)
    python tests/eval/run_evals.py --scenarios            # run labeled scenarios (30 cases)
    python tests/eval/run_evals.py --full                 # run all 50 cases (golden + scenarios)
    python tests/eval/run_evals.py --category safety      # filter by category
    python tests/eval/run_evals.py --stage golden_set     # filter by stage

Each test case is sent to the agent's /api/chat endpoint. The runner checks:
  1. expected_tools                — tool names that must appear in tool_calls
  2. expected_tool_output_contains — strings that must be present in raw tool outputs
  3. expected_output_contains      — strings that must be present in the LLM response (case-insensitive)
  4. expected_output_not_contains  — strings that must NOT be present in the LLM response (case-insensitive)
"""

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

import yaml

try:
    import aiohttp
except ImportError:
    print("ERROR: 'aiohttp' package is required. Install with: pip install aiohttp")
    sys.exit(1)

DATASETS_DIR = Path(__file__).parent / "datasets"
GOLDEN_DATASET = DATASETS_DIR / "golden_set.yaml"
SCENARIOS_DATASET = DATASETS_DIR / "labeled_scenarios.yaml"
DEFAULT_BASE_URL = "http://localhost:8000"


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------

def load_dataset(path: Path) -> list[dict]:
    with path.open() as fh:
        if path.suffix in (".yaml", ".yml"):
            return yaml.safe_load(fh)
        return json.load(fh)


# ---------------------------------------------------------------------------
# Evaluation logic
# ---------------------------------------------------------------------------

async def check_test_case(test_case: dict, base_url: str, session: aiohttp.ClientSession) -> dict:
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
    tool_must_contain: list[str] = test_case.get("expected_tool_output_contains", [])

    failures: list[str] = []
    response_text = ""
    actual_tools: list[str] = []

    # --- Send request ---
    try:
        async with session.post(
            f"{base_url}/api/chat",
            json={"message": user_input, "session_id": f"eval-{uuid.uuid4()}"},
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            response_text = data.get("response", "")
            actual_tools = data.get("tool_calls", [])
            tool_outputs = data.get("tool_outputs", [])
    except aiohttp.ClientConnectionError:
        failures.append(f"Connection refused — is the server running at {base_url}?")
        return {
            "id": tc_id,
            "passed": False,
            "failures": failures,
            "response": response_text,
            "tool_calls": actual_tools,
        }
    except aiohttp.ClientResponseError as exc:
        failures.append(f"HTTP error: {exc.status} {exc.message}")
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
    tool_output_text = "\n".join(tool_outputs).lower()

    # --- Check 1: expected tools were called ---
    for tool in expected_tools:
        if tool not in actual_tools:
            failures.append(f"Expected tool '{tool}' was not called. Actual tools: {actual_tools}")

    # --- Check 2: response must contain these strings ---
    for phrase in must_contain:
        if phrase.lower() not in response_lower:
            failures.append(f"Response missing required string: '{phrase}'")

    # --- Check 3: tool output must contain these strings ---
    for phrase in tool_must_contain:
        if phrase.lower() not in tool_output_text:
            failures.append(f"Tool output missing required string: '{phrase}'")

    # --- Check 4: response must NOT contain these strings ---
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
    complexity = test_case.get("complexity", "unknown")
    difficulty = test_case.get("difficulty", "unknown")
    stage = test_case.get("stage", "unknown")
    print(f"  [{status}] {result['id']}  ({category} / {complexity} / {difficulty} / {stage})")
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

async def run_batch(test_cases: list[dict], base_url: str, concurrency: int) -> list[tuple[dict, dict]]:
    """Run all test cases with bounded concurrency. Returns (result, test_case) pairs in order."""
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded(tc: dict, session: aiohttp.ClientSession) -> tuple[dict, dict]:
        async with semaphore:
            result = await check_test_case(tc, base_url, session)
            return result, tc

    async with aiohttp.ClientSession() as session:
        tasks = [bounded(tc, session) for tc in test_cases]
        return list(await asyncio.gather(*tasks))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ghostfolio-agent evals")
    parser.add_argument(
        "--url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL of the running agent API (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help="Path to a custom test cases YAML/JSON file",
    )

    # Stage selectors (mutually exclusive shortcuts)
    stage_group = parser.add_mutually_exclusive_group()
    stage_group.add_argument(
        "--scenarios",
        action="store_true",
        help="Run labeled scenarios only (30 coverage-focused cases)",
    )
    stage_group.add_argument(
        "--full",
        action="store_true",
        help="Run all 50 cases (golden set + labeled scenarios)",
    )

    # Filters
    parser.add_argument(
        "--category",
        default=None,
        help="Only run test cases matching this category (e.g. portfolio, risk, safety, market_data)",
    )
    parser.add_argument(
        "--complexity",
        default=None,
        help="Only run test cases matching this complexity (single_tool, multi_tool, synthesis)",
    )
    parser.add_argument(
        "--difficulty",
        default=None,
        help="Only run test cases matching this difficulty (straightforward, ambiguous, edge_case)",
    )
    parser.add_argument(
        "--stage",
        default=None,
        help="Only run test cases matching this stage (golden_set, labeled_scenario)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Max parallel requests to the agent API (default: 5)",
    )
    args = parser.parse_args()

    # Determine which dataset(s) to load
    if args.dataset:
        dataset_path = Path(args.dataset)
        if not dataset_path.exists():
            print(f"ERROR: Dataset file not found: {dataset_path}")
            sys.exit(1)
        test_cases = load_dataset(dataset_path)
        source_label = str(dataset_path)
    elif args.scenarios:
        test_cases = load_dataset(SCENARIOS_DATASET)
        source_label = str(SCENARIOS_DATASET)
    elif args.full:
        test_cases = load_dataset(GOLDEN_DATASET) + load_dataset(SCENARIOS_DATASET)
        source_label = "golden_set.yaml + labeled_scenarios.yaml"
    else:
        # Default: golden set (run on every commit)
        test_cases = load_dataset(GOLDEN_DATASET)
        source_label = str(GOLDEN_DATASET)

    # Optional filters
    if args.category:
        test_cases = [tc for tc in test_cases if tc.get("category") == args.category]
    if args.complexity:
        test_cases = [tc for tc in test_cases if tc.get("complexity") == args.complexity]
    if args.difficulty:
        test_cases = [tc for tc in test_cases if tc.get("difficulty") == args.difficulty]
    if args.stage:
        test_cases = [tc for tc in test_cases if tc.get("stage") == args.stage]
    if not test_cases:
        print("ERROR: No test cases match the given filters")
        sys.exit(1)

    print(f"\nGhostfolio Agent Eval Runner")
    print(f"  API        : {args.url}")
    print(f"  Source     : {source_label}")
    print(f"  Cases      : {len(test_cases)}")
    print(f"  Concurrency: {args.concurrency}\n")
    print("=" * 60)

    t0 = time.monotonic()
    pairs = asyncio.run(run_batch(test_cases, args.url, args.concurrency))
    elapsed = time.monotonic() - t0

    results = []
    for result, tc in pairs:
        print_result(result, tc)
        results.append(result)

    # --- Summary ---
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    score_pct = int(passed / total * 100) if total else 0

    print("=" * 60)
    print(f"SCORE: {passed}/{total} passed ({score_pct}%)")
    print(f"TIME : {elapsed:.1f}s ({elapsed / total:.1f}s avg per case)")

    # Breakdown by dimension
    def _breakdown(label: str, key: str) -> None:
        buckets: dict[str, dict[str, int]] = {}
        for result, tc in pairs:
            val = tc.get(key, "unknown")
            if val not in buckets:
                buckets[val] = {"passed": 0, "total": 0}
            buckets[val]["total"] += 1
            if result["passed"]:
                buckets[val]["passed"] += 1
        print(f"\n{label}:")
        for val, counts in sorted(buckets.items()):
            pct = int(counts["passed"] / counts["total"] * 100)
            print(f"  {val:<20} {counts['passed']}/{counts['total']}  ({pct}%)")

    _breakdown("By category", "category")
    _breakdown("By complexity", "complexity")
    _breakdown("By difficulty", "difficulty")
    _breakdown("By stage", "stage")

    print()
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
