# Corrective Retrieval

## Purpose

Retry retrieval when the first search has weak evidence.

## Inputs

- `question`: Original user question.
- `top_result_score`: Retrieval score of the strongest candidate.

## Tool Implementation

- Python: `corrective_retrieve`
- File: `tools/corrective_retrieval.py`

## Behavior

1. Detect weak retrieval score.
2. Rewrite the query with government-scheme-specific terms.
3. Rerun scheme retrieval.

## Output

- `rewritten_query`
- new candidate scheme list
