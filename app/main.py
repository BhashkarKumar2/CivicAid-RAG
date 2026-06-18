from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
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


@app.get("/api/meta")
def meta():
    occupations = set()
    categories = set()
    states = set()
    scheme_categories = set()
    for scheme in retriever.schemes:
        states.update(scheme.states)
        scheme_categories.add(scheme.category)
        occupations.update(scheme.eligibility.get("occupation", []))
        categories.update(scheme.eligibility.get("categories", []))

    return {
        "scheme_count": len(retriever.schemes),
        "data_source": "official" if DATA_PATH == OFFICIAL_DATA_PATH else "seed",
        "profile_options": {
            "states": sorted(states),
            "occupations": sorted(occupations),
            "categories": sorted(categories),
            "genders": ["female", "male", "other"],
        },
        "scheme_categories": sorted(scheme_categories),
        "examples": [
            {
                "label": "Scholarship",
                "question": "I am a 21 year old OBC student from Bihar. Which scholarship can I get?",
                "profile": {"age": 21, "state": "Bihar", "occupation": "student", "income": 180000, "category": "OBC"},
            },
            {
                "label": "Health cover",
                "question": "My family income is low. Which health scheme can help with hospital treatment?",
                "profile": {"age": 40, "state": "Bihar", "occupation": "worker", "income": 100000, "category": "SC"},
            },
            {
                "label": "Farmer support",
                "question": "I am a farmer and need government income support.",
                "profile": {"age": 38, "state": "Punjab", "occupation": "farmer", "income": 220000, "category": "General"},
            },
            {
                "label": "Business loan",
                "question": "I am a woman entrepreneur and need a business loan.",
                "profile": {"age": 29, "state": "Kerala", "occupation": "entrepreneur", "income": 500000, "category": "SC", "gender": "female"},
            },
            {
                "label": "Deadline",
                "question": "What is the last date to apply for Bihar scholarship?",
                "profile": {"age": 21, "state": "Bihar", "occupation": "student", "income": 180000, "category": "OBC"},
            },
            {
                "label": "Solar subsidy",
                "question": "How much is the subsidy on rooftop solar panels by state and center?",
                "profile": {"age": 35, "state": "Uttar Pradesh", "occupation": "worker", "income": 300000, "category": "General"},
            },
        ],
    }


@app.post("/api/ask")
def ask(request: AskRequest):
    return agent.run(request)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)
