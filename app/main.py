from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

from .agent import CivicAidAgent
from .models import AskRequest
from .observability import tracer
from .retrieval import HybridRetriever

OFFICIAL_DATA_PATH = BASE_DIR / "data" / "official_schemes.json"
SEED_DATA_PATH = BASE_DIR / "data" / "schemes.json"
DATA_PATH = OFFICIAL_DATA_PATH if OFFICIAL_DATA_PATH.exists() else SEED_DATA_PATH
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="CivicAid RAG", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

retriever = HybridRetriever.from_json(DATA_PATH)
agent = CivicAidAgent(retriever)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "schemes": len(retriever.schemes),
        "data_source": "official" if DATA_PATH == OFFICIAL_DATA_PATH else "seed",
        "langfuse": "enabled" if tracer.enabled else "disabled",
    }


@app.get("/api/schemes")
def schemes():
    return [scheme.model_dump() for scheme in retriever.schemes]


@app.post("/api/ask")
def ask(request: AskRequest):
    return agent.run(request)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
