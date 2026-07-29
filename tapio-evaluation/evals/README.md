# DeepEval — RAG Evaluation Suite

This directory contains DeepEval-based tests that evaluate Tapio's RAG
pipeline against the datasets in `tapio-evaluation/datasets/`.

## Prerequisites

- Ollama running with the model specified in [`conftest.py`](conftest.py) (default: `llama3.2`)
- ChromaDB populated (run `mise run vectorize` or `uv run -m tapio.cli vectorize`)

## Running

```bash
# Full suite (parallel via deepeval CLI)
mise run eval

# Individual metric suites
mise run eval-correctness   # GEval × correctness rubric
mise run eval-retrieval     # Faithfulness + AnswerRelevancy
mise run eval-safety        # GEval × safety rubric

# List all 162 test cases
mise run eval-list

# Run a single dataset domain
uv run pytest tapio-evaluation/evals/test_correctness.py \
  -m deepeval -k "citizenship" -v

# Run a single test case
uv run pytest tapio-evaluation/evals/test_retrieval.py \
  -m deepeval -k "cz_001" -v
```

## Tests

| File | Metric | What it measures |
|------|--------|-----------------|
| `test_correctness.py` | `GEval` (correctness rubric) | Factual alignment between `actual_output` and `expected_output` |
| `test_retrieval.py` | `GEval` (retrieval rubric) | Retrieval quality: topic match, agency precision, noise level |
| `test_safety.py` | `GEval` (safety rubric) | Legal safety: right-to-work, overstay, benefit revocation, disclaimers |

Each test is parametrized over all 54 dataset cases (9 domains × 6 cases),
for a total of 162 individual evaluations.

## Adding a new dataset

1. Add a JSONL file to `tapio-evaluation/datasets/`
2. Add the dataset name to `DATASET_NAMES` in [`conftest.py`](conftest.py) (the
   parametrized `case` fixture automatically picks it up)

## CI

These tests are **not** part of the regular `pytest` suite — they require
Ollama + ChromaDB. Run them manually or as a separate CI job when those
services are available.
