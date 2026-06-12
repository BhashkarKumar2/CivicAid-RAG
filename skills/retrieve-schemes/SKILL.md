# Retrieve Schemes

## Purpose

Find candidate government schemes relevant to a citizen question.

## Inputs

- `question`: User's natural-language query.
- `top_k`: Number of candidate schemes to retrieve.

## Tool Implementation

- Python: `retrieve_schemes`
- File: `tools/retrieve_schemes.py`
- Core retrieval engine: `app/retrieval.py`

## Behavior

1. Normalize query text.
2. Expand Hindi phrases and known synonyms.
3. Score schemes using BM25-style lexical retrieval plus token overlap.
4. Return candidates with retrieval score and matched terms.

## Output

Candidate schemes:

- `scheme`
- `retrieval_score`
- `matched_terms`
