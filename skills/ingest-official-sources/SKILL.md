# Ingest Official Sources

## Purpose

Build the retriever dataset from official government scheme pages instead of relying only on static seed data.

## Inputs

- `data/official_sources.json`: Registry of official URLs and structured eligibility rules.

## Tool Implementation

- Python: `ingest`
- File: `tools/ingest_official_sources.py`

## Behavior

1. Fetch each official source URL.
2. Extract readable page text from HTML.
3. Build `data/official_schemes.json`.
4. Write `data/official_ingestion_report.json` with fetch status for every URL.
5. Keep explicit eligibility rules from the source registry for deterministic rule checking.

## Output

- `data/official_schemes.json`
- `data/official_ingestion_report.json`

