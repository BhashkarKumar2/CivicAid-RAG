# CivicAid RAG

Explainable government scheme eligibility assistant built as a low-cost RAG MVP.

## What It Does

- Retrieves relevant government schemes from a local dataset.
- Checks eligibility using profile fields like age, state, occupation, income, category, and gender.
- Returns documents, application steps, and official source citations.
- Uses pure-Python hybrid retrieval by default, so no paid API is required.
- Optionally uses Gemini if `GEMINI_API_KEY` is set.
- Runs through an explicit project-local agent workflow with skill files.

## Stack

- FastAPI
- Static HTML/CSS/JS frontend
- Local JSON scheme dataset
- BM25-style keyword retrieval + query expansion
- Rule-based eligibility scoring
- Optional Gemini answer generation
- Optional Langfuse tracing
- Optional myScheme API-backed official source discovery

## Agent Skills

Project-local skills live in:

```text
skills/
```

Current skills:

- `skills/ingest-official-sources/SKILL.md`
- `skills/discover-official-sources/SKILL.md`
- `skills/retrieve-schemes/SKILL.md`
- `skills/check-eligibility/SKILL.md`
- `skills/corrective-retrieval/SKILL.md`
- `skills/generate-answer/SKILL.md`

The runtime agent is implemented in:

```text
app/agent.py
```

Every `/api/ask` response includes `agent_steps`, and the UI shows the skills used for that run.

## Agent Tools

Executable tool wrappers live in:

```text
tools/
```

Current tools:

- `tools/ingest_official_sources.py`
- `tools/discover_official_sources.py`
- `tools/retrieve_schemes.py`
- `tools/check_eligibility.py`
- `tools/corrective_retrieval.py`
- `tools/generate_answer.py`
- `tools/observability.py`

The agent in `app/agent.py` orchestrates these tools according to the skill descriptions.

At question time, the agent can now discover official web sources if local retrieval is weak. The discovery tool keeps only official government domains such as `.gov.in`, `myscheme.gov.in`, `india.gov.in`, and known official scheme portals.

Discovery order:

1. Query the official myScheme search API when `MYSCHEME_API_KEY` is set.
2. If myScheme has no result, fall back to web search parsing.
3. Keep only official government URLs.
4. Fetch page text and pass it into answer generation as temporary RAG context.

Example out-of-dataset query:

```text
Tell me about Ladli Behna scheme eligibility and documents
```

The agent discovers:

```text
https://www.myscheme.gov.in/schemes/cmlby
```

## Official Source Ingestion

The app prefers generated official-source data:

```text
data/official_schemes.json
```

If that file is missing, it falls back to:

```text
data/schemes.json
```

Run ingestion:

```bash
python tools/ingest_official_sources.py
```

Source registry:

```text
data/official_sources.json
```

Ingestion report:

```text
data/official_ingestion_report.json
```

The report records every official URL fetched, character counts, and any fetch errors.

## Run Locally

```bash
cd CivicAid-RAG
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

## Optional Gemini

```bash
pip install google-generativeai
$env:GEMINI_API_KEY="your_api_key"
uvicorn app.main:app --reload
```

Without Gemini, the app still works using a deterministic template answer.

## Optional myScheme Discovery

Official web discovery works without a key for seeded official sources such as PM Surya Ghar. To enable broader myScheme API search, set:

```text
MYSCHEME_API_KEY=your_myscheme_api_key
```

## Deploy

### Render

This repo includes `render.yaml` for a Python web service.

Render settings:

```text
Build Command: pip install -r requirements.txt
Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

CLI flow after installing and logging in to the Render CLI:

```bash
render services create --type web_service --name civicaid-rag --repo https://github.com/BhashkarKumar2/CivicAid-RAG --runtime python --build-command "pip install -r requirements.txt" --start-command "uvicorn app.main:app --host 0.0.0.0 --port $PORT" --plan free
```

Set production secrets in the Render dashboard or CLI environment variables, not in Git.

### Vercel

Vercel detects FastAPI from `app/app.py`, which re-exports the app from `app.main`.

CLI flow:

```bash
vercel
vercel --prod
```

Set production secrets with the Vercel dashboard or:

```bash
vercel env add LANGFUSE_PUBLIC_KEY production
vercel env add LANGFUSE_SECRET_KEY production
vercel env add LANGFUSE_BASE_URL production
vercel env add GEMINI_API_KEY production
vercel env add MYSCHEME_API_KEY production
```

## Langfuse Observability

Create `.env` from `.env.example`:

```bash
cp .env.example .env
```

Set these values:

```text
LANGFUSE_PUBLIC_KEY=<your_langfuse_public_key>
LANGFUSE_SECRET_KEY=<your_langfuse_secret_key>
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

For US cloud, use:

```text
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
```

When enabled, each `/api/ask` call records one Langfuse trace row:

- Root trace/observation: `civicaid-rag-agent`
- `skill_files_read`: the local `skills/*/SKILL.md` files used by the request
- `tool_calls`: the project tools called by the agent
- `execution_log`: per-step inputs, outputs, status, nesting, and duration
- Final answer and response summary

The API response includes `trace_url` when Langfuse credentials are active.

## API

Health:

```bash
GET /api/health
```

Ask:

```bash
POST /api/ask
```

Example body:

```json
{
  "question": "I am a 21 year old OBC student from Bihar. Which scholarship can I get?",
  "profile": {
    "age": 21,
    "state": "Bihar",
    "occupation": "student",
    "income": 180000,
    "category": "OBC"
  },
  "top_k": 3
}
```

## Next Features

- Add PDF ingestion for official documents.
- Store schemes and chunks in SQLite.
- Add Hindi/English query translation.
- Add FAISS or Chroma embeddings.
- Add admin UI for adding schemes.
- Add RAG evaluation dataset and citation-quality scoring.

## Failure Probes

Run smoke tests before pushing:

```bash
python tests_smoke.py
```

Run likely-failure probes:

```bash
python tests_failure_cases.py
```

Current probe status:

- Native Hindi scholarship query now passes through lightweight Hindi phrase expansion.
- Vague document-only question now passes through profile-aware reranking.
- Deadline questions retrieve the correct scheme, but the dataset has no deadline field yet.

Remaining limitations:

- Hindi support is phrase-based, not full translation.
- Vague follow-up questions still need proper session memory for production use.
