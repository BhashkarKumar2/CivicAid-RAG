from app.generator import build_answer


def generate_answer(
    question: str,
    results: list[dict],
    web_sources: list[dict] | None = None,
    guidance: dict | None = None,
    tracer=None,
) -> str:
    return build_answer(question, results, web_sources=web_sources or [], guidance=guidance or {}, tracer=tracer)
