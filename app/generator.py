import os


def build_answer(question: str, results: list[dict], web_sources: list[dict] | None = None, tracer=None) -> str:
    web_sources = web_sources or []
    if os.getenv("GEMINI_API_KEY"):
        generated = _gemini_answer(question, results, web_sources, tracer=tracer)
        if generated:
            return generated
    with (tracer.observation("template-answer", input={"result_count": len(results), "web_source_count": len(web_sources)}) if tracer else _null_observation()):
        answer = _template_answer(results, web_sources)
        if tracer:
            tracer.update_current(output={"answer_preview": answer[:500]})
        return answer


def _gemini_answer(question: str, results: list[dict], web_sources: list[dict], tracer=None) -> str | None:
    try:
        import google.generativeai as genai

        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        model_name = "gemini-1.5-flash"
        model = genai.GenerativeModel(model_name)
        context = "\n\n".join(
            f"Scheme: {item['scheme']['name']}\n"
            f"Summary: {item['scheme']['summary']}\n"
            f"Eligibility status: {item['eligibility']['status']}\n"
            f"Documents: {', '.join(item['scheme']['documents'])}\n"
            f"Apply steps: {'; '.join(item['scheme']['apply_steps'])}\n"
            f"Source: {item['scheme']['source_url']}"
            for item in results
        )
        web_context = "\n\n".join(
            f"Official web source: {source['title']}\n"
            f"URL: {source['url']}\n"
            f"Snippet: {source.get('snippet', '')}\n"
            f"Extract: {source.get('text_excerpt', '')}"
            for source in web_sources
        )
        prompt = (
            "You are CivicAid, a careful government scheme assistant. "
            "Answer only from the provided context. Include eligibility reasoning, documents, steps, and citations. "
            "When discovered official web context is present, prioritize it over local scheme matches that are not on the same topic.\n\n"
            f"Question: {question}\n\nLocal scheme context:\n{context or 'No strong local scheme context.'}"
            f"\n\nDiscovered official web context:\n{web_context or 'No web sources discovered.'}"
        )
        observation = tracer.observation(
            "gemini-answer",
            as_type="generation",
            model=model_name,
            input={"question": question, "context_scheme_count": len(results), "web_source_count": len(web_sources)},
        ) if tracer else _null_observation()
        with observation:
            response = model.generate_content(prompt, request_options={"timeout": 8})
            if tracer:
                tracer.update_current(output={"answer": response.text})
        return response.text
    except Exception:
        return None


def _template_answer(results: list[dict], web_sources: list[dict]) -> str:
    if not results and not web_sources:
        return "I could not find a matching scheme in the current dataset. Try adding your state, occupation, age, income, and category."

    weak_local = bool(results) and results[0]["eligibility"]["status"] == "unlikely"
    lines = []
    if web_sources:
        if weak_local:
            lines.append("The local official dataset did not find a likely eligible match, so I discovered these official web sources at question time:")
        else:
            lines.append("I found these official web sources at question time. Use these first for this topic:")
        for index, source in enumerate(web_sources, start=1):
            lines.append("")
            lines.append(f"{index}. {source['title']}")
            lines.append(f"   URL: {source['url']}")
            if source.get("snippet"):
                lines.append(f"   What it says: {source['snippet']}")
        lines.append("")
        lines.append("Closest local dataset matches are listed below, but treat them as lower confidence if they are not on the same topic:")
    else:
        lines.append("Based on the current official scheme dataset, these are the strongest matches:")

    for index, item in enumerate(results, start=1):
        scheme = item["scheme"]
        eligibility = item["eligibility"]
        lines.append("")
        lines.append(f"{index}. {scheme['name']} - {eligibility['status']} ({eligibility['score']}% profile match)")
        lines.append(f"   Why: {scheme['summary']}")
        lines.append(f"   Documents: {', '.join(scheme['documents'][:5])}")
        lines.append(f"   How to apply: {'; '.join(scheme['apply_steps'][:4])}")
        lines.append(f"   Source: {scheme['source_title']} ({scheme['source_url']})")
    return "\n".join(lines)


class _null_observation:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, traceback):
        return False
