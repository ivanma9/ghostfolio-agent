"""
LangSmith deterministic golden-set evaluations for the Ghostfolio agent.

These evals use langsmith.evaluation.evaluate() to run the agent against
the "ghostfolio-golden-sets" dataset and check results with 3 deterministic
evaluators:

  1. tools_called  — correct tools were invoked
  2. output_contains — required strings appear in response
  3. output_not_contains — forbidden strings are absent

Setup:
  1. Set LANGSMITH_API_KEY in .env or environment
  2. Upload dataset:  python tests/eval/langsmith_upload_dataset.py
  3. Start the agent:  uvicorn ghostfolio_agent.main:app
  4. Run evals:        pytest tests/eval/test_langsmith_evals.py -v

Or run directly:  python tests/eval/test_langsmith_evals.py
"""

import os
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import httpx
from langsmith import Client
from langsmith.evaluation import EvaluationResult, evaluate

DATASET_NAME = "ghostfolio-golden-sets"
BASE_URL = os.environ.get("AGENT_BASE_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# Target function: calls the agent's /api/chat endpoint
# ---------------------------------------------------------------------------

def agent_target(inputs: dict) -> dict:
    """Send a message to the agent and return the response + tool_calls."""
    with httpx.Client(timeout=60) as client:
        resp = client.post(
            f"{BASE_URL}/api/chat",
            json={
                "message": inputs["message"],
                "session_id": f"eval-{uuid.uuid4()}",
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return {
        "response": data.get("response", ""),
        "tool_calls": data.get("tool_calls", []),
    }


# ---------------------------------------------------------------------------
# Deterministic evaluators
# ---------------------------------------------------------------------------

def tools_called(run, example) -> EvaluationResult:
    """Check that all expected tools were called."""
    expected = example.outputs.get("expected_tools", [])
    actual = run.outputs.get("tool_calls", [])
    missing = [t for t in expected if t not in actual]
    return EvaluationResult(
        key="tools_called",
        score=1.0 if not missing else 0.0,
        comment=f"Missing tools: {missing}" if missing else "All expected tools called",
    )


def output_contains(run, example) -> EvaluationResult:
    """Check that required strings appear in the response (case-insensitive)."""
    expected = example.outputs.get("expected_output_contains", [])
    response_lower = run.outputs.get("response", "").lower()
    missing = [s for s in expected if s.lower() not in response_lower]
    return EvaluationResult(
        key="output_contains",
        score=1.0 if not missing else 0.0,
        comment=f"Missing strings: {missing}" if missing else "All required strings found",
    )


def output_not_contains(run, example) -> EvaluationResult:
    """Check that forbidden strings are absent from the response (case-insensitive)."""
    forbidden = example.outputs.get("expected_output_not_contains", [])
    response_lower = run.outputs.get("response", "").lower()
    found = [s for s in forbidden if s.lower() in response_lower]
    return EvaluationResult(
        key="output_not_contains",
        score=1.0 if not found else 0.0,
        comment=f"Forbidden strings found: {found}" if found else "No forbidden strings present",
    )


# ---------------------------------------------------------------------------
# Pytest entry point
# ---------------------------------------------------------------------------

def test_golden_sets():
    """Run all 5 golden-set evals via LangSmith evaluate()."""
    results = evaluate(
        agent_target,
        data=DATASET_NAME,
        evaluators=[tools_called, output_contains, output_not_contains],
        experiment_prefix="ghostfolio-golden",
        num_repetitions=1,
    )

    # Assert all examples passed all evaluators
    for result in results:
        feedback = result.get("evaluation_results", {}).get("results", [])
        for ev in feedback:
            assert ev.score == 1.0, (
                f"Evaluator '{ev.key}' failed: {ev.comment}"
            )


# ---------------------------------------------------------------------------
# Direct run (outside pytest)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Running golden-set evals against {BASE_URL}")
    print(f"Dataset: {DATASET_NAME}\n")

    results = evaluate(
        agent_target,
        data=DATASET_NAME,
        evaluators=[tools_called, output_contains, output_not_contains],
        experiment_prefix="ghostfolio-golden",
        num_repetitions=1,
    )

    print("\nDone. View results at: https://smith.langchain.com → Datasets → Experiments")
