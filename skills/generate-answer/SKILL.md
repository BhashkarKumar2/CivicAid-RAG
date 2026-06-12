# Generate Answer

## Purpose

Generate the final grounded answer using retrieved schemes, eligibility checks, documents, steps, and citations.

## Inputs

- `question`: User question.
- `results`: Retrieved and eligibility-scored schemes.

## Tool Implementation

- Python: `generate_answer`
- File: `tools/generate_answer.py`
- Core answer builder: `app/generator.py`

## Behavior

1. If `GEMINI_API_KEY` is set, try Gemini with an 8-second timeout.
2. If Gemini is unavailable, invalid, or slow, fall back to deterministic template output.
3. Include source links and explainable eligibility reasoning.

## Output

- Final user-facing answer.
