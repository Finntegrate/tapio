# Ragas Evaluation

[Ragas](https://docs.ragas.io/) evaluation tests sit alongside the existing DeepEval suite. They measure retrieval and generation quality using Ragas metrics.

## Metrics

| Metric | What it measures | Threshold | Requires |
|--------|-----------------|-----------|----------|
| Faithfulness | Answer is grounded in retrieved context | ≥0.70 | LLM |
| AnswerRelevancy | Answer is relevant to the question | ≥0.70 | Embeddings |
| ContextPrecision | Signal-to-noise in retrieved docs | ≥0.50 | LLM |
| ContextRecall | Retrieved docs cover the ground truth | ≥0.50 | LLM |
| AnswerCorrectness | Answer matches ground truth | ≥0.50 | LLM + Embeddings |
| AnswerSimilarity | Semantic similarity to ground truth | ≥0.70 | Embeddings |

## Prerequisites

- Ollama running with `llama3.2` pulled
- ChromaDB populated (run `tapio vectorize`)
- All dev dependencies installed (`uv sync`)

## Running

```bash
mise run eval-ragas                 # all 7 ragas tests
mise run eval-ragas-comprehensive   # single run with all 6 metrics
mise run eval-ragas-retrieval       # context precision + recall
mise run eval-ragas-answer          # faithfulness + relevancy + correctness + similarity
mise run eval-ragas-list            # list registered test cases
```

Or with pytest directly:

```bash
uv run pytest tapio-evaluation/ragas_eval/ -m ragas -v --no-header
```

## How it works

1. `conftest.py` applies a compatibility patch so Ragas 0.3.x can import alongside the installed `langchain-community` version, then sets up session-scoped fixtures:

   - `ragas_llm` — wraps `ChatOllama(llama3.2)` in a `LangchainLLMWrapper`
   - `ragas_embeddings` — wraps `HuggingFaceEmbeddings(all-MiniLM-L6-v2)` in a `LangchainEmbeddingsWrapper`
   - `evaluation_dataset` — runs the RAG pipeline on all 54 test cases (9 datasets × 6 queries), collecting `user_input`, `response`, `retrieved_contexts`, and `reference` into a HuggingFace `Dataset`

2. Each test calls `ragas.evaluate(dataset, metrics, llm, embeddings)` and asserts the aggregate score meets the threshold.

## Adding new test cases

Add a JSONL entry to any file in `tapio-evaluation/datasets/`. The dataset fixture automatically picks up new cases on the next run.
