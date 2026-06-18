# CivicAid RAG

CivicAid RAG is an explainable government-scheme eligibility assistant. It combines a small official-source scheme dataset, LangChain-backed retrieval, deterministic eligibility checks, optional Gemini answer generation, and single-row Langfuse tracing.

Production URLs:

- Vercel: `https://civicaid-rag.vercel.app`
- Render: `https://civicaid-rag.onrender.com`

## What It Does

- Finds relevant government schemes for a citizen question.
- Checks eligibility from profile fields: age, state, occupation, income, category, and gender.
- Returns documents, application steps, confidence signals, and official source citations.
- Uses LangChain for the RAG retrieval adapter and answer-template runnable.
- Uses deterministic rule checks for eligibility so results are explainable.
- Optionally uses Gemini when `GEMINI_API_KEY` is set; otherwise it falls back to template generation.
- Records one Langfuse trace row per `/api/ask` request when Langfuse credentials are configured.

## Architecture

Runtime entry points:

- FastAPI app: `app/main.py`
- Vercel adapter: `app/app.py`
- Frontend: `static/index.html`, `static/app.js`, `static/styles.css`
- Agent orchestration: `app/agent.py`
- LangChain pipeline: `app/langchain_pipeline.py`
- Observability wrapper: `app/observability.py`

RAG and tool flow:

1. `retrieve-schemes` uses `SchemeLangChainRetriever`, a LangChain `BaseRetriever` adapter over the local hybrid retriever.
2. `check-eligibility` applies deterministic profile rules to retrieved schemes.
3. `corrective-retrieval` reruns retrieval only when the first result is weak.
4. `discover-official-sources` searches official government sources when local context is weak or off-topic.
5. `generate-answer` uses Gemini if configured, otherwise a LangChain `PromptTemplate` runnable builds the template answer.

LangGraph is not currently used because this is still a predictable fixed RAG workflow. Add LangGraph only when the app needs stateful branching, multi-turn memory, retries across graph nodes, or human-in-the-loop control.

## Agent Skills And Tools

Project-local skill docs live in `skills/`:

- `skills/ingest-official-sources/SKILL.md`
- `skills/discover-official-sources/SKILL.md`
- `skills/retrieve-schemes/SKILL.md`
- `skills/check-eligibility/SKILL.md`
- `skills/corrective-retrieval/SKILL.md`
- `skills/generate-answer/SKILL.md`

Executable wrappers live in `tools/`:

- `tools/ingest_official_sources.py`
- `tools/discover_official_sources.py`
- `tools/retrieve_schemes.py`
- `tools/check_eligibility.py`
- `tools/corrective_retrieval.py`
- `tools/generate_answer.py`
- `tools/observability.py`

Every `/api/ask` response includes `agent_steps`, and the UI shows the skills used for that run.

## Data

The app prefers generated official-source data:

```text
data/official_schemes.json
```

If missing, it falls back to:

```text
data/schemes.json
```

Run official-source ingestion:

```bash
python tools/ingest_official_sources.py
```

The source registry is `data/official_sources.json`, and the ingestion report is written to `data/official_ingestion_report.json`.

## Local Setup

```bash
cd CivicAid-RAG
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

## Environment Variables

Required for Langfuse tracing:

```text
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
```

Optional:

```text
GEMINI_API_KEY=
MYSCHEME_API_KEY=
CIVICAID_CORS_ORIGINS=http://127.0.0.1:8000,http://localhost:8000
```

Notes:

- Keep `.env` local only. It is ignored by git.
- Set production secrets in Vercel/Render dashboards or CLIs, not in git.
- `CIVICAID_CORS_ORIGINS` is comma-separated. Keep it narrow in production.

## Langfuse Tracing

When enabled, each `/api/ask` call records one Langfuse trace row:

- Root observation: `civicaid-rag-agent`
- `input.skill_files_read`: skill filenames and hashes
- `metadata.skill_files_read`: full `skills/*/SKILL.md` contents
- `output.tools_used`: top-level tool list with status, inputs, outputs, and duration
- `output.tool_usage_summary`: readable one-line-per-tool summary
- `output.model_tool_usage`: whether the LLM provider itself made native tool calls
- `output.tool_calls`: project tool call details
- `output.execution_log`: collapsed per-step log
- `output.answer`: final answer

Important distinction:

- The CivicAid agent calls project tools.
- The Gemini provider currently does not make native tool calls. `model_tool_usage.provider_native_tool_calls` is therefore empty unless provider-native tool calling is added later.

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

Example:

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

## Deployment

### Vercel

Vercel uses `app/app.py`, which re-exports `app.main:app`.

```bash
vercel
vercel deploy --prod --yes
```

Set production env vars:

```bash
vercel env add LANGFUSE_PUBLIC_KEY production
vercel env add LANGFUSE_SECRET_KEY production
vercel env add LANGFUSE_BASE_URL production
vercel env add GEMINI_API_KEY production
vercel env add MYSCHEME_API_KEY production
vercel env add CIVICAID_CORS_ORIGINS production
```

### Render

`render.yaml` defines the web service.

```text
Build Command: pip install -r requirements.txt
Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Set secrets in Render dashboard or CLI. Do not commit secrets.

## Tests

Run all current checks:

```bash
python -m compileall app tools
python tests_smoke.py
python tests_case_suite.py
python tests_failure_cases.py
```

The case suite covers 20 behavior cases. The failure probe suite covers 8 risk cases.

## Security Posture

Current controls:

- `.env`, `.venv`, `.vercel`, caches, and bytecode are git-ignored.
- Render secret values are declared with `sync: false`.
- Vercel/Render secrets must be configured outside git.
- CORS is restricted to configured origins and browser credentials are disabled.
- Frontend-rendered API values are escaped before insertion into HTML.
- Official-source discovery filters to government or known official scheme URLs.
- Langfuse traces are single-row and include tool visibility without creating extra child observations.

Known residual risks:

- `/api/ask` is public and unauthenticated. Add rate limiting and abuse protection before real production use.
- Langfuse can store user question/profile fields. Do not submit sensitive personal data unless the Langfuse project access and retention policy are acceptable.
- Dependency ranges for `langfuse` and `langchain` allow upgrades. Pin exact versions for reproducible production builds if needed.
- Hindi support is phrase-based, not full translation.
- The dataset is small; out-of-dataset questions still need official verification.

## Next Work

- Add rate limiting for `/api/ask`.
- Add auth or admin-only controls for ingestion if ingestion becomes remotely exposed.
- Add full Hindi/English translation.
- Add vector search with FAISS/Chroma.
- Add an evaluation dataset with citation-quality scoring.
- Add trace redaction or masking if handling real citizen PII.
