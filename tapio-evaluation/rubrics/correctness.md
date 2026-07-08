# Evaluation Rubric: Factual Correctness

This rubric evaluates how accurately the assistant's response reflects the provided ground-truth reference answer. Given the legal and bureaucratic nature of immigration in Finland, precise numbers, dates, thresholds, and conditions are critical.

## Grading Scale (1–5)

### Score 5: Excellent / Completely Correct

- **Factual Alignment:** The generated response is entirely accurate, fully aligns with the reference answer, and contains no contradictions.
- **Precision:** All key numbers, fees, thresholds (e.g., "EUR 800 per month" or "average of 30 hours"), and processing timelines match the reference exactly.
- **Completeness:** No vital conditions or caveats mentioned in the reference are missing.

### Score 4: Good / Mostly Correct

- **Factual Alignment:** The core answer is accurate, but it has minor omissions that do not compromise the overall advice.
- **Precision:** Primary figures are correct, but secondary conditions or exceptions might be slightly understated or generalized.
- **Hallucinations:** No false information or incorrect statistics are introduced.

### Score 3: Partially Correct

- **Factual Alignment:** The response captures some correct elements but misses crucial legal caveats or secondary requirements.
- **Omissions:** Fails to state an important condition (e.g., fails to mention that the student working limit is an _average_ of 30 hours, or fails to state the 3-month submission window for refugee family ties).
- **Inaccuracies:** Minor factual confusion is present but is not immediately harmful to the user's status.

### Score 2: Poor / Minor Factual Errors

- **Factual Alignment:** The response contains at least one significant factual error or major legal misstatement (e.g., citing a residency period of 5 years instead of the updated 8 years for standard citizenship).
- **Contradiction:** Contradicts the reference on essential facts, putting the user at risk of making incorrect administrative assumptions.

### Score 1: Fail / Highly Incorrect or Hallucinated

- **Factual Alignment:** The response is completely wrong, heavily hallucinated, or irrelevant.
- **Severe Inaccuracy:** Cites incorrect numbers, non-existent pathways, or completely wrong official authorities.

---

## Evaluation Guidance for LLM Judge

```json
{
  "instruction": "Compare the [Generated Answer] to the [Reference Answer]. Check specifically for numeric thresholds, processing timelines, and exceptions. Output your evaluation in JSON format.",
  "json_schema": {
    "factual_correctness_score": "integer (1-5)",
    "reasoning": "string"
  }
}
```
