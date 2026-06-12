# Check Eligibility

## Purpose

Evaluate whether the citizen profile appears eligible for each retrieved scheme.

## Inputs

- `profile`: Age, state, occupation, income, category, and gender.
- `scheme`: Candidate scheme record.

## Tool Implementation

- Python: `check_eligibility`
- File: `tools/check_eligibility.py`
- Core rule engine: `app/eligibility.py`

## Behavior

1. Check age rules.
2. Check income ceiling.
3. Check state coverage.
4. Check occupation match.
5. Check category or gender match.
6. Produce a profile match score and status.

## Output

- `status`: `likely eligible`, `possibly eligible`, or `unlikely`.
- `score`: Percentage profile match.
- `checks`: Explainable rule checks.
- `missing_fields`: Fields needed for stronger confidence.
