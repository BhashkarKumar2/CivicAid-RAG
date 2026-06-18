import os

from fastapi.testclient import TestClient

os.environ["GEMINI_API_KEY"] = ""
os.environ["LANGFUSE_PUBLIC_KEY"] = ""
os.environ["LANGFUSE_SECRET_KEY"] = ""
os.environ["LANGFUSE_BASE_URL"] = ""
os.environ["MYSCHEME_API_KEY"] = ""

from app.main import app


CASE_SUITE = [
    {
        "name": "Bihar OBC scholarship",
        "question": "I am a 21 year old OBC student from Bihar. Which scholarship can I get?",
        "profile": {"age": 21, "state": "Bihar", "occupation": "student", "income": 180000, "category": "OBC"},
        "expected_top": "bihar-post-matric-scholarship",
        "expected_status": "likely eligible",
        "expected_topic": "education",
    },
    {
        "name": "PMAY acronym housing",
        "question": "Can I apply for PMAY?",
        "profile": {"age": 30, "state": "Delhi", "occupation": "worker", "income": 400000, "category": "EWS"},
        "expected_top": "pmay-urban",
        "expected_status": "likely eligible",
        "expected_topic": "housing",
    },
    {
        "name": "AB PMJAY acronym health",
        "question": "Am I eligible for AB-PMJAY?",
        "profile": {"age": 40, "state": "Bihar", "occupation": "worker", "income": 100000, "category": "SC"},
        "expected_top": "ayushman-bharat-pmjay",
        "expected_status": "likely eligible",
        "expected_topic": "health",
    },
    {
        "name": "Hospital treatment support",
        "question": "My family income is low. Which health scheme can help with hospital treatment?",
        "profile": {"age": 52, "state": "Uttar Pradesh", "occupation": "worker", "income": 90000, "category": "General"},
        "expected_top": "ayushman-bharat-pmjay",
        "expected_status": "likely eligible",
        "expected_topic": "health",
    },
    {
        "name": "Farmer income support",
        "question": "I am a farmer and need government income support.",
        "profile": {"age": 38, "state": "Punjab", "occupation": "farmer", "income": 220000, "category": "General"},
        "expected_top": "pm-kisan",
        "expected_status": "likely eligible",
        "expected_topic": "agriculture",
    },
    {
        "name": "Conflicting farmer question and student profile",
        "question": "I am a farmer. Can I get PM-KISAN?",
        "profile": {"age": 17, "state": "Punjab", "occupation": "student", "income": 200000, "category": "General"},
        "expected_top": "pm-kisan",
        "expected_status": "unlikely",
        "expected_conflict": "occupation",
    },
    {
        "name": "Woman entrepreneur loan",
        "question": "I am a woman entrepreneur and need a business loan.",
        "profile": {"age": 29, "state": "Kerala", "occupation": "entrepreneur", "income": 500000, "category": "SC", "gender": "female"},
        "expected_top": "stand-up-india",
        "expected_status": "likely eligible",
        "expected_topic": "entrepreneurship",
    },
    {
        "name": "SC startup venture",
        "question": "I need money for my startup venture.",
        "profile": {"age": 27, "state": "Kerala", "occupation": "entrepreneur", "income": 500000, "category": "SC"},
        "expected_top": "stand-up-india",
        "expected_status": "likely eligible",
        "expected_topic": "entrepreneurship",
    },
    {
        "name": "PMAY income too high",
        "question": "Can I apply for PMAY housing support?",
        "profile": {"age": 35, "state": "Delhi", "occupation": "worker", "income": 1200000, "category": "General"},
        "expected_top": "pmay-urban",
        "expected_status": "unlikely",
    },
    {
        "name": "Cross-state scholarship rejection",
        "question": "I am an OBC student from Delhi and need scholarship support.",
        "profile": {"age": 21, "state": "Delhi", "occupation": "student", "income": 180000, "category": "OBC"},
        "expected_top": "bihar-post-matric-scholarship",
        "expected_status": "unlikely",
        "expected_topic": "education",
    },
    {
        "name": "Documents only with full profile",
        "question": "Which documents do I need?",
        "profile": {"age": 21, "state": "Bihar", "occupation": "student", "income": 180000, "category": "OBC"},
        "expected_top": "bihar-post-matric-scholarship",
        "expected_intent": "documents",
    },
    {
        "name": "Deadline needs verification",
        "question": "What is the last date to apply for Bihar scholarship?",
        "profile": {"age": 21, "state": "Bihar", "occupation": "student", "income": 180000, "category": "OBC"},
        "expected_top": "bihar-post-matric-scholarship",
        "expected_intent": "deadline",
        "answer_contains": "deadline field",
    },
    {
        "name": "Hindi scholarship query",
        "question": "मैं बिहार का ओबीसी छात्र हूं, मुझे कौन सी छात्रवृत्ति मिल सकती है?",
        "profile": {"age": 21, "state": "Bihar", "occupation": "student", "income": 180000, "category": "OBC"},
        "expected_top": "bihar-post-matric-scholarship",
        "expected_status": "likely eligible",
        "expected_topic": "education",
    },
    {
        "name": "Solar subsidy official discovery",
        "question": "How much is the subsidy on rooftop solar panels by state and center?",
        "profile": {"age": 35, "state": "Uttar Pradesh", "occupation": "worker", "income": 300000, "category": "General"},
        "expected_web_source": "https://www.pmsuryaghar.gov.in/",
        "expected_topic": "solar",
    },
    {
        "name": "Housing documents",
        "question": "What documents are needed for PMAY Urban?",
        "profile": {"age": 33, "state": "Maharashtra", "occupation": "self-employed", "income": 450000, "category": "OBC"},
        "expected_top": "pmay-urban",
        "expected_intent": "documents",
    },
    {
        "name": "Sparse health profile",
        "question": "Can I get treatment cover under Ayushman Bharat?",
        "profile": {"age": 44, "income": 90000},
        "expected_top": "ayushman-bharat-pmjay",
        "expected_missing": ["state", "occupation", "category", "gender"],
    },
    {
        "name": "General male business loan not eligible",
        "question": "I need a government business loan for a new enterprise.",
        "profile": {"age": 32, "state": "Karnataka", "occupation": "entrepreneur", "income": 600000, "category": "General", "gender": "male"},
        "expected_top": "stand-up-india",
        "expected_status": "unlikely",
    },
    {
        "name": "All India farmer state",
        "question": "Does PM-KISAN work for farmers in Tamil Nadu?",
        "profile": {"age": 45, "state": "Tamil Nadu", "occupation": "farmer", "income": 240000, "category": "OBC"},
        "expected_top": "pm-kisan",
        "expected_status": "likely eligible",
    },
    {
        "name": "Category conflict surfaced",
        "question": "I am an SC entrepreneur. Can I get Stand-Up India loan?",
        "profile": {"age": 26, "state": "Delhi", "occupation": "entrepreneur", "income": 400000, "category": "OBC"},
        "expected_top": "stand-up-india",
        "expected_conflict": "category",
    },
    {
        "name": "Sparse scholarship profile",
        "question": "Can I get scholarship help?",
        "profile": {"occupation": "student"},
        "expected_top": "bihar-post-matric-scholarship",
        "expected_missing": ["age", "state", "income", "category", "gender"],
        "expected_topic": "education",
    },
]


def assert_case(data: dict, case: dict):
    assert "summary" in data, "missing summary"
    assert "profile_summary" in data, "missing profile_summary"
    assert "query_insights" in data, "missing query_insights"
    assert "next_actions" in data, "missing next_actions"
    assert data["agent_steps"], "missing agent steps"

    if case.get("expected_top"):
        assert data["results"], "expected local results"
        assert data["results"][0]["scheme"]["id"] == case["expected_top"]
        assert data["summary"]["top_scheme_id"] == case["expected_top"]

    if case.get("expected_status"):
        assert data["results"][0]["eligibility"]["status"] == case["expected_status"]

    if case.get("expected_topic"):
        assert case["expected_topic"] in data["query_insights"]["topics"]

    if case.get("expected_intent"):
        assert case["expected_intent"] in data["query_insights"]["intents"]

    if case.get("expected_missing"):
        missing = set(data["profile_summary"]["missing_fields"])
        assert set(case["expected_missing"]).issubset(missing)

    if case.get("expected_conflict"):
        fields = {item["field"] for item in data["query_insights"]["profile_conflicts"]}
        assert case["expected_conflict"] in fields

    if case.get("answer_contains"):
        assert case["answer_contains"].lower() in data["answer"].lower()

    if case.get("expected_web_source"):
        urls = {source["url"] for source in data["web_sources"]}
        assert case["expected_web_source"] in urls


def run():
    client = TestClient(app)
    failures = []
    for index, case in enumerate(CASE_SUITE, start=1):
        response = client.post(
            "/api/ask",
            json={"question": case["question"], "profile": case["profile"], "top_k": 3, "session_id": "case-suite"},
        )
        try:
            assert response.status_code == 200, response.text
            data = response.json()
            assert_case(data, case)
            top_id = data["results"][0]["scheme"]["id"] if data["results"] else "none"
            status = data["results"][0]["eligibility"]["status"] if data["results"] else "none"
            print(f"{index:02d}. OK | {case['name']} | top={top_id} | status={status}")
        except AssertionError as exc:
            failures.append(f"{case['name']}: {exc}")
            print(f"{index:02d}. FAIL | {case['name']} | {exc}")

    print(f"\nCase suite failures: {len(failures)}/{len(CASE_SUITE)}")
    if failures:
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)


if __name__ == "__main__":
    run()
