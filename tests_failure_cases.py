import os

from fastapi.testclient import TestClient

os.environ["GEMINI_API_KEY"] = ""
os.environ["LANGFUSE_PUBLIC_KEY"] = ""
os.environ["LANGFUSE_SECRET_KEY"] = ""
os.environ["LANGFUSE_BASE_URL"] = ""

from app.main import app


FAILURE_PROBES = [
    {
        "name": "Hindi native scholarship query",
        "question": "मैं बिहार का ओबीसी छात्र हूं, मुझे कौन सी छात्रवृत्ति मिल सकती है?",
        "profile": {"age": 21, "state": "Bihar", "occupation": "student", "income": 180000, "category": "OBC"},
        "desired_top": "bihar-post-matric-scholarship",
        "risk": "Covered by lightweight Hindi phrase expansion; full translation is still needed for broader Hindi.",
    },
    {
        "name": "Acronym query for housing",
        "question": "Can I apply for PMAY?",
        "profile": {"age": 30, "state": "Delhi", "occupation": "worker", "income": 400000, "category": "EWS"},
        "desired_top": "pmay-urban",
        "risk": "Acronyms are not expanded unless present in the scheme text.",
    },
    {
        "name": "Acronym query for health",
        "question": "Am I eligible for AB-PMJAY?",
        "profile": {"age": 40, "state": "Bihar", "occupation": "worker", "income": 100000, "category": "SC"},
        "desired_top": "ayushman-bharat-pmjay",
        "risk": "Hyphenated acronyms may tokenize poorly.",
    },
    {
        "name": "Cross-state scholarship mismatch",
        "question": "I am an OBC student from Delhi and need scholarship support.",
        "profile": {"age": 21, "state": "Delhi", "occupation": "student", "income": 180000, "category": "OBC"},
        "desired_top": "bihar-post-matric-scholarship",
        "risk": "Retrieval may find the scheme, but eligibility should reject state.",
    },
    {
        "name": "Synonym not in index",
        "question": "I need money for my startup venture.",
        "profile": {"age": 27, "state": "Kerala", "occupation": "entrepreneur", "income": 500000, "category": "SC"},
        "desired_top": "stand-up-india",
        "risk": "Vocabulary is small; startup/venture may not map to entrepreneurship.",
    },
    {
        "name": "Deadline question",
        "question": "What is the last date to apply for Bihar scholarship?",
        "profile": {"age": 21, "state": "Bihar", "occupation": "student", "income": 180000, "category": "OBC"},
        "desired_top": "bihar-post-matric-scholarship",
        "risk": "Dataset has no deadlines, so answer quality should mention missing data.",
    },
    {
        "name": "Documents-only vague query",
        "question": "Which documents do I need?",
        "profile": {"age": 21, "state": "Bihar", "occupation": "student", "income": 180000, "category": "OBC"},
        "desired_top": "bihar-post-matric-scholarship",
        "risk": "Covered by profile-aware reranking; true multi-turn memory is still needed.",
    },
    {
        "name": "Conflicting user profile and question",
        "question": "I am a farmer. Can I get PM-KISAN?",
        "profile": {"age": 17, "state": "Punjab", "occupation": "student", "income": 200000, "category": "General"},
        "desired_top": "pm-kisan",
        "risk": "The agent does not reconcile conflicts between free text and structured profile.",
    },
]


def run():
    client = TestClient(app)
    failures = []
    for index, probe in enumerate(FAILURE_PROBES, start=1):
        response = client.post(
            "/api/ask",
            json={"question": probe["question"], "profile": probe["profile"], "top_k": 3},
        )
        data = response.json()
        if not data["results"]:
            top_id = "none"
            eligibility = "none"
            retrieval_score = 0
        else:
            top = data["results"][0]
            top_id = top["scheme"]["id"]
            eligibility = top["eligibility"]["status"]
            retrieval_score = top["retrieval_score"]
        ok = top_id == probe["desired_top"]
        if not ok:
            failures.append(probe["name"])
        marker = "OK" if ok else "RISK"
        print(
            f"{index:02d}. {marker} | {probe['name']} | "
            f"top={top_id} | desired={probe['desired_top']} | "
            f"eligibility={eligibility} | retrieval={retrieval_score}"
        )
        print(f"    risk: {probe['risk']}")
    print(f"\nPotential failures observed: {len(failures)}/{len(FAILURE_PROBES)}")
    if failures:
        print("Failing probes:", ", ".join(failures))


if __name__ == "__main__":
    run()
