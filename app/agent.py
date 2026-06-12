from dataclasses import dataclass, field
from typing import Any

from .models import AskRequest
from .retrieval import HybridRetriever, meaningful_tokens
from tools.check_eligibility import check_eligibility
from tools.corrective_retrieval import corrective_retrieve
from tools.discover_official_sources import discover_official_sources
from tools.generate_answer import generate_answer
from tools.observability import profile_for_trace, tracer
from tools.retrieve_schemes import retrieve_schemes


@dataclass
class AgentStep:
    skill: str
    status: str
    detail: dict[str, Any] = field(default_factory=dict)

    def model_dump(self) -> dict[str, Any]:
        return {"skill": self.skill, "status": self.status, "detail": self.detail}


class CivicAidAgent:
    def __init__(self, retriever: HybridRetriever):
        self.retriever = retriever

    def run(self, request: AskRequest) -> dict[str, Any]:
        steps: list[AgentStep] = []
        trace_input = {
            "question": request.question,
            "top_k": request.top_k,
            "profile": profile_for_trace(request.profile),
            "session_id": request.session_id,
            "user_id": request.user_id,
        }

        with tracer.observation(
            "civicaid-rag-agent",
            input=trace_input,
            metadata={
                "feature": "agentic-scheme-eligibility-rag",
                "session_id": request.session_id,
                "user_id": request.user_id,
                "skills": [
                    "retrieve-schemes",
                    "discover-official-sources",
                    "check-eligibility",
                    "corrective-retrieval",
                    "generate-answer",
                ],
            },
        ):
            raw_results = self._retrieve(request, steps)
            results = self._check_eligibility(raw_results, request, steps)
            web_sources = []

            if results and results[0]["retrieval_score"] < 0.05:
                raw_results = self._corrective_retrieval(request, steps)
                results = self._check_eligibility(raw_results, request, steps)
            else:
                steps.append(
                    AgentStep(
                        "corrective-retrieval",
                        "skipped",
                        {"reason": "top retrieval score was strong enough" if results else "no candidates"},
                    )
                )

            should_discover, discovery_reason = self._should_discover_web_sources(request.question, results)
            if should_discover:
                web_sources = self._discover_official_sources(request, steps)
                steps[-1].detail["reason"] = discovery_reason
            else:
                steps.append(
                    AgentStep(
                        "discover-official-sources",
                        "skipped",
                        {"reason": discovery_reason},
                    )
                )

            answer = self._generate_answer(request, results, web_sources, steps)
            trace_url = tracer.trace_url()
            tracer.update_current(
                output={
                    "top_scheme": results[0]["scheme"]["id"] if results else None,
                    "web_source_count": len(web_sources),
                    "agent_steps": [step.model_dump() for step in steps],
                    "answer_preview": answer[:500],
                }
            )
            tracer.flush()

            return {
                "question": request.question,
                "answer": answer,
                "results": results,
                "web_sources": web_sources,
                "agent_steps": [step.model_dump() for step in steps],
                "trace_url": trace_url,
            }

    def _retrieve(self, request: AskRequest, steps: list[AgentStep]):
        with tracer.observation("skill:retrieve-schemes", input={"question": request.question, "top_k": request.top_k}):
            raw_results = retrieve_schemes(self.retriever, request.question, request.top_k)
            top_ids = [scheme.id for scheme, _, _ in raw_results]
            top_scores = [round(score, 4) for _, score, _ in raw_results]
            tracer.update_current(output={"top_ids": top_ids, "top_scores": top_scores})
            steps.append(
                AgentStep(
                    "retrieve-schemes",
                    "completed",
                    {"top_ids": top_ids, "top_scores": top_scores},
                )
            )
            return raw_results

    def _discover_official_sources(self, request: AskRequest, steps: list[AgentStep]):
        with tracer.observation("skill:discover-official-sources", input={"question": request.question}):
            sources = discover_official_sources(request.question, max_results=3)
            tracer.update_current(output={"urls": [source["url"] for source in sources]})
            steps.append(
                AgentStep(
                    "discover-official-sources",
                    "completed",
                    {"urls": [source["url"] for source in sources], "count": len(sources)},
                )
            )
            return sources

    def _corrective_retrieval(self, request: AskRequest, steps: list[AgentStep]):
        with tracer.observation("skill:corrective-retrieval", input={"question": request.question}):
            rewritten, raw_results = corrective_retrieve(self.retriever, request.question, request.top_k)
            top_ids = [scheme.id for scheme, _, _ in raw_results]
            tracer.update_current(output={"rewritten_query": rewritten, "top_ids": top_ids})
            steps.append(
                AgentStep(
                    "corrective-retrieval",
                    "completed",
                    {"rewritten_query": rewritten, "top_ids": top_ids},
                )
            )
            return raw_results

    def _check_eligibility(self, raw_results, request: AskRequest, steps: list[AgentStep]):
        results = []
        with tracer.observation("skill:check-eligibility", input={"candidate_count": len(raw_results)}):
            for scheme, score, matched_terms in raw_results:
                eligibility = check_eligibility(request.profile, scheme)
                adjusted_score = self._profile_adjusted_score(score, eligibility)
                results.append(
                    {
                        "scheme": scheme.model_dump(),
                        "retrieval_score": round(score, 4),
                        "adjusted_score": round(adjusted_score, 4),
                        "matched_terms": matched_terms,
                        "eligibility": eligibility,
                        "citation": {
                            "title": scheme.source_title,
                            "url": scheme.source_url,
                        },
                    }
                )

            results.sort(key=lambda item: item["adjusted_score"], reverse=True)
            eligibility_summary = [
                {
                    "scheme": item["scheme"]["id"],
                    "eligibility": item["eligibility"]["status"],
                    "score": item["eligibility"]["score"],
                }
                for item in results
            ]
            tracer.update_current(output=eligibility_summary)
            steps.append(
                AgentStep(
                    "check-eligibility",
                    "completed",
                    {"results": eligibility_summary},
                )
            )
        return results

    def _generate_answer(self, request: AskRequest, results: list[dict], web_sources: list[dict], steps: list[AgentStep]) -> str:
        with tracer.observation("skill:generate-answer", input={"result_count": len(results), "web_source_count": len(web_sources)}):
            answer = generate_answer(request.question, results, web_sources=web_sources, tracer=tracer)
            steps.append(
                AgentStep(
                    "generate-answer",
                    "completed",
                    {
                        "answer_type": "gemini-or-template",
                        "answer_preview": answer[:220],
                    },
                )
            )
            tracer.update_current(output={"answer_preview": answer[:500]})
        return answer

    @staticmethod
    def _should_discover_web_sources(question: str, results: list[dict]) -> tuple[bool, str]:
        if not results:
            return True, "no local candidates were retrieved"
        top = results[0]
        if top["retrieval_score"] < 1.0:
            return True, "top retrieval score was weak"
        if top["eligibility"]["status"] == "unlikely":
            return True, "top local match was unlikely for the citizen profile"

        query_terms = set(meaningful_tokens(question))
        matched_terms = set(top.get("matched_terms", []))
        if query_terms and len(matched_terms.intersection(query_terms)) < 2:
            return True, "local match used too few meaningful query terms"

        domain_terms = {"solar", "panel", "panels", "renewable", "energy", "rooftop"}
        if query_terms.intersection(domain_terms):
            scheme = top["scheme"]
            scheme_text = " ".join(
                [
                    scheme.get("name", ""),
                    scheme.get("category", ""),
                    scheme.get("summary", ""),
                    " ".join(scheme.get("benefits", [])),
                ]
            ).lower()
            if not any(term in scheme_text for term in domain_terms):
                return True, "question is about solar/renewable energy but top local match is off-topic"

        return False, "local official dataset had sufficient topical retrieval confidence"

    @staticmethod
    def _profile_adjusted_score(retrieval_score: float, eligibility: dict) -> float:
        status_bonus = {
            "likely eligible": 1.2,
            "possibly eligible": 0.45,
            "unlikely": -0.6,
        }.get(eligibility["status"], 0)
        return retrieval_score + status_bonus + (eligibility["score"] / 100) * 0.6
