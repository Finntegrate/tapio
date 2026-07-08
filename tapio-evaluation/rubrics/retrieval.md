# Evaluation Rubric: Retrieval Quality & Context Relevance

This rubric evaluates the quality, relevance, and source attribution of the retrieved context chunks before they are sent to the generation step. This directly measures your chunking and embedding pipeline.

## Grading Scale (1–4)

### Score 4: Highly Relevant & Precise (Excellent)

- **Topic Matching:** All retrieved chunks directly address the core question and the specific user persona.
- **Authority Precision:** The retriever fetched documents from the correct official agency (e.g., DVV for address registrations, Vero for tax cards, Kela for social benefits). No mismatched administrative contexts.
- **Noise Level:** The chunks are compact, highly dense with information, and contain minimal irrelevant text.

### Score 3: Partially Relevant with Some Noise (Good)

- **Topic Matching:** The correct target documents are retrieved, but the chunking has introduced significant irrelevant surrounding text (noise).
- **Authority Precision:** The correct agency source is present, but chunks from irrelevant agencies are also ranked highly in the top results.

### Score 2: Insufficient or Misaligned Context (Poor)

- **Missing Information:** The retriever missed the specific section or exception required to answer the query (e.g., retrieved general student permit rules but missed the specific EUR 800 income threshold chunk).
- **Cross-Agency Confusion:** The retriever fetched information from the wrong agency (e.g., returning Migri documents for a query that specifically asks about registering a local address, which is handled by DVV).

### Score 1: Entirely Irrelevant or Empty (Fail)

- **Topic Matching:** The retrieved chunks have no relationship to the query.
- **Missing Targets:** None of the expected gold-standard URLs or document IDs specified in `expected_documents.json` were retrieved in the top K results.

---

## Evaluation Guidance for LLM Judge

```json
{
  "instruction": "Compare the retrieved [Context Chunks] against the [User Query]. Assess whether the chunks provide the specific answers required without administrative confusion.",
  "json_schema": {
    "retrieval_relevance_score": "integer (1-4)",
    "detected_noise_level": "string (None/Low/High)",
    "wrong_agency_flag": "boolean",
    "reasoning": "string"
  }
}
```
