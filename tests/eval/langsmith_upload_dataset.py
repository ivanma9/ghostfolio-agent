#!/usr/bin/env python3
"""
Upload golden test cases to LangSmith as a dataset.

Usage:
    python tests/eval/langsmith_upload_dataset.py

Requires:
    LANGSMITH_API_KEY env var (or set in .env)

This creates (or updates) a LangSmith dataset called "ghostfolio-golden-sets"
with 5 deterministic test cases from mvp_test_cases.json.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from langsmith import Client

DATASET_NAME = "ghostfolio-golden-sets"
DATASET_FILE = Path(__file__).parent / "datasets" / "mvp_test_cases.json"


def upload_dataset() -> None:
    client = Client()

    # Load golden test cases
    with DATASET_FILE.open() as f:
        test_cases = json.load(f)

    # Create or fetch existing dataset
    try:
        dataset = client.create_dataset(
            dataset_name=DATASET_NAME,
            description="5 deterministic golden-set evals for the Ghostfolio AI agent",
        )
        print(f"Created dataset: {DATASET_NAME} (id={dataset.id})")
    except Exception:
        # Dataset already exists — fetch it
        dataset = client.read_dataset(dataset_name=DATASET_NAME)
        print(f"Dataset already exists: {DATASET_NAME} (id={dataset.id})")

        # Delete existing examples to avoid duplicates on re-upload
        existing = list(client.list_examples(dataset_id=dataset.id))
        if existing:
            client.delete_examples([ex.id for ex in existing])
            print(f"  Cleared {len(existing)} existing examples")

    # Upload each test case as an example
    inputs = []
    outputs = []
    metadata_list = []

    for tc in test_cases:
        inputs.append({"message": tc["input"]})
        outputs.append({
            "expected_tools": tc.get("expected_tools", []),
            "expected_output_contains": tc.get("expected_output_contains", []),
            "expected_output_not_contains": tc.get("expected_output_not_contains", []),
        })
        metadata_list.append({
            "id": tc["id"],
            "category": tc.get("category", "unknown"),
            "description": tc.get("description", ""),
        })

    client.create_examples(
        inputs=inputs,
        outputs=outputs,
        metadata=metadata_list,
        dataset_id=dataset.id,
    )
    print(f"  Uploaded {len(test_cases)} golden-set examples")
    print(f"\nView at: https://smith.langchain.com → Datasets → {DATASET_NAME}")


if __name__ == "__main__":
    upload_dataset()
