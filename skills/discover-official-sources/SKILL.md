# Discover Official Sources

## Purpose

Find relevant official government webpages at question time when local RAG context is weak or the user asks about a scheme not in the local dataset.

## Inputs

- `question`: User's natural-language query.

## Tool Implementation

- Python: `discover_official_sources`
- File: `tools/discover_official_sources.py`

## Behavior

1. Build official-government search queries.
2. Search the web.
3. Keep only official URLs from `.gov.in` or known government scheme portals.
4. Fetch and extract readable page text.
5. Return temporary web RAG context with source URLs.

## Output

List of official web sources:

- `title`
- `url`
- `snippet`
- `text_excerpt`

