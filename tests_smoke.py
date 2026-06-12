import os

from fastapi.testclient import TestClient

os.environ["GEMINI_API_KEY"] = ""
os.environ["LANGFUSE_PUBLIC_KEY"] = ""
os.environ["LANGFUSE_SECRET_KEY"] = ""
os.environ["LANGFUSE_BASE_URL"] = ""
os.environ["MYSCHEME_API_KEY"] = ""

from app.main import app


def make_client() -> TestClient:
    return TestClient(app)


def test_health():
    response = make_client().get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["schemes"] >= 1
    assert data["data_source"] in {"official", "seed"}


def test_ask_returns_answer_and_agent_steps():
    response = make_client().post(
        "/api/ask",
        json={
            "question": "Can I apply for PMAY?",
            "profile": {
                "age": 30,
                "state": "Delhi",
                "occupation": "worker",
                "income": 400000,
                "category": "EWS",
            },
            "top_k": 3,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["answer"]
    assert data["results"]
    assert data["agent_steps"]
    assert data["results"][0]["scheme"]["id"] == "pmay-urban"


def test_solar_query_uses_official_web_discovery():
    response = make_client().post(
        "/api/ask",
        json={
            "question": "how much is the subsidy on solar panels by state and center?",
            "profile": {
                "age": 21,
                "state": "uttar pradesh",
                "occupation": "student",
                "income": 20000,
                "category": "General",
                "gender": "male",
            },
            "top_k": 3,
        },
    )
    assert response.status_code == 200
    data = response.json()
    discovery_step = next(step for step in data["agent_steps"] if step["skill"] == "discover-official-sources")
    assert discovery_step["status"] == "completed"
    assert data["web_sources"]
    assert data["web_sources"][0]["url"] == "https://www.pmsuryaghar.gov.in/"
    assert "PM Surya Ghar" in data["answer"]


if __name__ == "__main__":
    test_health()
    test_ask_returns_answer_and_agent_steps()
    test_solar_query_uses_official_web_discovery()
    print("Smoke tests passed")
