from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import re
from typing import Any

from .models import AskRequest
from .retrieval import HybridRetriever, meaningful_tokens
from tools.check_eligibility import check_eligibility
from tools.corrective_retrieval import corrective_retrieve
from tools.discover_official_sources import discover_official_sources
from tools.generate_answer import generate_answer
from tools.observability import profile_for_trace, tracer
from tools.retrieve_schemes import retrieve_schemes


PROFILE_FIELDS = ("age", "state", "occupation", "income", "category", "gender")
BASE_DIR = Path(__file__).resolve().parent.parent
TRACE_SKILLS = (
    "retrieve-schemes",
    "check-eligibility",
    "corrective-retrieval",
    "discover-official-sources",
    "generate-answer",
)
TOOL_FILES = {
    "retrieve-schemes": "tools/retrieve_schemes.py",
    "check-eligibility": "tools/check_eligibility.py",
    "corrective-retrieval": "tools/corrective_retrieval.py",
    "discover-official-sources": "tools/discover_official_sources.py",
    "generate-answer": "tools/generate_answer.py",
}
TOOL_DISPLAY_NAMES = {
    "retrieve-schemes": "Retrieve Schemes",
    "check-eligibility": "Check Eligibility",
    "corrective-retrieval": "Corrective Retrieval",
    "discover-official-sources": "Discover Official Sources",
    "generate-answer": "Generate Answer",
}

TOPIC_KEYWORDS = {
    "education": {"scholarship", "student", "college", "school", "education", "matric", "छात्र", "छात्रवृत्ति"},
    "health": {"health", "hospital", "treatment", "medical", "insurance", "pmjay", "ayushman", "इलाज", "अस्पताल"},
    "agriculture": {"farmer", "farming", "agriculture", "crop", "kisan", "किसान"},
    "housing": {"house", "housing", "home", "awas", "pmay"},
    "entrepreneurship": {"business", "startup", "venture", "loan", "entrepreneur", "self-employed", "लोन", "व्यवसाय"},
    "solar": {"solar", "rooftop", "panel", "panels", "surya", "renewable"},
}

INTENT_KEYWORDS = {
    "eligibility": {"eligible", "eligibility", "qualify", "apply", "can i", "am i"},
    "documents": {"document", "documents", "paper", "papers", "certificate", "दस्तावेज"},
    "deadline": {"deadline", "last date", "closing date", "apply by", "due date", "अंतिम"},
    "application_steps": {"how to apply", "apply", "registration", "portal", "form"},
    "benefits": {"benefit", "benefits", "subsidy", "amount", "money", "support", "cover"},
}

OCCUPATION_SIGNALS = {
    "farmer": {"farmer", "farming", "kisan", "किसान"},
    "student": {"student", "scholarship", "college", "school", "छात्र", "छात्रवृत्ति"},
    "entrepreneur": {"entrepreneur", "startup", "venture", "business owner"},
    "worker": {"worker", "labour", "labor", "employee"},
    "unemployed": {"unemployed", "jobless"},
    "self-employed": {"self-employed", "self employed"},
}


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
        profile_summary = self._profile_summary(request.profile)
        query_insights = self._query_insights(request.question, profile_summary)
        skill_files_read = self._skill_files_for_trace()
        trace_input = {
            "question": request.question,
            "top_k": request.top_k,
            "profile": profile_for_trace(request.profile),
            "query_insights": query_insights,
            "session_id": request.session_id,
            "user_id": request.user_id,
            "skill_files_read": [
                {"skill": item["skill"], "path": item["path"], "sha256": item["sha256"]}
                for item in skill_files_read
            ],
        }

        with tracer.observation(
            "civicaid-rag-agent",
            input=trace_input,
            metadata={
                "feature": "agentic-scheme-eligibility-rag",
                "session_id": request.session_id,
                "user_id": request.user_id,
                "single_row_trace": True,
                "skills": list(TRACE_SKILLS),
                "skill_files_read": skill_files_read,
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

            guidance = self._answer_guidance(profile_summary, query_insights, results, web_sources)
            answer = self._generate_answer(request, results, web_sources, guidance, steps)
            summary = self._response_summary(results, web_sources, query_insights)
            next_actions = self._next_actions(profile_summary, query_insights, results, web_sources)
            trace_url = tracer.trace_url()
            execution_log = tracer.execution_log()
            tools_used = self._tools_used_for_trace(steps, execution_log)
            model_tool_usage = self._model_tool_usage_for_trace(execution_log)
            response_payload = {
                "question": request.question,
                "answer": answer,
                "results": results,
                "web_sources": web_sources,
                "agent_steps": [step.model_dump() for step in steps],
                "summary": summary,
                "profile_summary": profile_summary,
                "query_insights": query_insights,
                "next_actions": next_actions,
                "trace_url": trace_url,
                "session_id": request.session_id,
            }
            tracer.update_current(
                output={
                    "tools_used": tools_used,
                    "tool_usage_summary": self._tool_usage_summary(tools_used),
                    "model_tool_usage": model_tool_usage,
                    "top_scheme": results[0]["scheme"]["id"] if results else None,
                    "web_source_count": len(web_sources),
                    "summary": summary,
                    "agent_steps": [step.model_dump() for step in steps],
                    "tool_calls": self._tool_calls_for_trace(steps),
                    "execution_log": execution_log,
                    "answer": answer,
                }
            )

        tracer.flush()
        return response_payload

    @staticmethod
    def _skill_files_for_trace() -> list[dict[str, Any]]:
        records = []
        for skill in TRACE_SKILLS:
            relative_path = Path("skills") / skill / "SKILL.md"
            path = BASE_DIR / relative_path
            try:
                content = path.read_text(encoding="utf-8")
                status = "read"
            except OSError as exc:
                content = ""
                status = "error"
                error = str(exc)
            else:
                error = None

            record = {
                "skill": skill,
                "path": relative_path.as_posix(),
                "status": status,
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest() if content else None,
                "content": content,
            }
            if error:
                record["error"] = error
            records.append(record)
        return records

    @staticmethod
    def _tool_calls_for_trace(steps: list[AgentStep]) -> list[dict[str, Any]]:
        return [
            {
                "skill": step.skill,
                "tool_file": TOOL_FILES.get(step.skill),
                "status": step.status,
                "detail": step.detail,
            }
            for step in steps
        ]

    @staticmethod
    def _tools_used_for_trace(steps: list[AgentStep], execution_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
        executed_by_name = {
            str(entry.get("name", "")).removeprefix("skill:"): entry
            for entry in execution_log
            if str(entry.get("name", "")).startswith("skill:")
        }
        return [
            {
                "name": step.skill,
                "display_name": TOOL_DISPLAY_NAMES.get(step.skill, step.skill),
                "tool_file": TOOL_FILES.get(step.skill),
                "called": step.status != "skipped",
                "status": step.status,
                "duration_ms": executed_by_name.get(step.skill, {}).get("duration_ms"),
                "input": executed_by_name.get(step.skill, {}).get("input"),
                "output": step.detail,
            }
            for step in steps
        ]

    @staticmethod
    def _tool_usage_summary(tools_used: list[dict[str, Any]]) -> str:
        lines = ["Agent tools used in this request:"]
        for tool in tools_used:
            state = "called" if tool["called"] else "skipped"
            duration = f" in {tool['duration_ms']} ms" if tool.get("duration_ms") is not None else ""
            lines.append(f"- {tool['display_name']} ({tool['name']}): {state}, {tool['status']}{duration}")
        return "\n".join(lines)

    @staticmethod
    def _model_tool_usage_for_trace(execution_log: list[dict[str, Any]]) -> dict[str, Any]:
        answer_engine = "gemini" if any(entry.get("name") == "gemini-answer" for entry in execution_log) else "template"
        return {
            "answer_engine": answer_engine,
            "provider_native_tool_calls": [],
            "note": (
                "The LLM provider did not call tools directly. CivicAid's agent called the project tools listed "
                "in tools_used before answer generation."
            ),
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

    def _generate_answer(
        self,
        request: AskRequest,
        results: list[dict],
        web_sources: list[dict],
        guidance: dict,
        steps: list[AgentStep],
    ) -> str:
        with tracer.observation("skill:generate-answer", input={"result_count": len(results), "web_source_count": len(web_sources)}):
            answer = generate_answer(request.question, results, web_sources=web_sources, guidance=guidance, tracer=tracer)
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
    def _profile_summary(profile) -> dict[str, Any]:
        raw = profile.model_dump()
        provided = {}
        missing = []
        for field in PROFILE_FIELDS:
            value = raw.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(field)
                continue
            provided[field] = value.strip() if isinstance(value, str) else value

        completeness = round((len(provided) / len(PROFILE_FIELDS)) * 100)
        if completeness >= 85:
            label = "complete"
        elif completeness >= 50:
            label = "partial"
        else:
            label = "sparse"

        return {
            "provided": provided,
            "missing_fields": missing,
            "completeness": completeness,
            "label": label,
        }

    @staticmethod
    def _query_insights(question: str, profile_summary: dict[str, Any]) -> dict[str, Any]:
        normalized = question.lower()
        token_set = set(re.findall(r"[\w-]+", normalized))

        topics = [
            topic
            for topic, keywords in TOPIC_KEYWORDS.items()
            if any(keyword in normalized or keyword in token_set for keyword in keywords)
        ]
        intents = [
            intent
            for intent, keywords in INTENT_KEYWORDS.items()
            if any(keyword in normalized or keyword in token_set for keyword in keywords)
        ]

        conflicts = []
        provided = profile_summary.get("provided", {})
        profile_occupation = str(provided.get("occupation", "")).lower()
        for expected, signals in OCCUPATION_SIGNALS.items():
            if profile_occupation and profile_occupation != expected and any(signal in normalized for signal in signals):
                conflicts.append(
                    {
                        "field": "occupation",
                        "question_value": expected,
                        "profile_value": profile_occupation,
                        "message": f"The question sounds like {expected}, but the profile occupation is {profile_occupation}.",
                    }
                )
                break

        profile_gender = str(provided.get("gender", "")).lower()
        if profile_gender and profile_gender != "female" and any(term in normalized for term in ("woman", "women", "female")):
            conflicts.append(
                {
                    "field": "gender",
                    "question_value": "female",
                    "profile_value": profile_gender,
                    "message": f"The question mentions a woman/female applicant, but the profile gender is {profile_gender}.",
                }
            )

        profile_category = str(provided.get("category", "")).lower()
        for category in ("obc", "sc", "st", "ews", "general", "ebc"):
            if profile_category and profile_category != category and re.search(rf"\b{category}\b", normalized):
                conflicts.append(
                    {
                        "field": "category",
                        "question_value": category.upper() if category != "general" else "General",
                        "profile_value": provided.get("category"),
                        "message": f"The question mentions {category.upper()}, but the profile category is {provided.get('category')}.",
                    }
                )
                break

        return {
            "topics": topics or ["general"],
            "intents": intents or ["scheme_search"],
            "profile_conflicts": conflicts,
            "needs_deadline_verification": "deadline" in intents,
            "needs_document_focus": "documents" in intents,
        }

    @staticmethod
    def _answer_guidance(
        profile_summary: dict[str, Any],
        query_insights: dict[str, Any],
        results: list[dict],
        web_sources: list[dict],
    ) -> dict[str, Any]:
        guidance: list[str] = []
        if query_insights.get("profile_conflicts"):
            guidance.append("Resolve the mismatch between the written question and the structured profile before applying.")
        if query_insights.get("needs_deadline_verification"):
            guidance.append("The local dataset does not have a verified deadline field; open the official source for the latest last date.")
        if profile_summary.get("missing_fields") and (not results or results[0]["eligibility"]["status"] != "likely eligible"):
            missing = ", ".join(profile_summary["missing_fields"][:4])
            guidance.append(f"Add missing profile fields ({missing}) to improve the eligibility check.")
        if web_sources:
            guidance.append("Use the discovered official web sources first when they are more topical than local matches.")
        return {"answer_guidance": guidance}

    @staticmethod
    def _response_summary(results: list[dict], web_sources: list[dict], query_insights: dict[str, Any]) -> dict[str, Any]:
        if not results:
            return {
                "top_scheme_id": None,
                "top_scheme_name": None,
                "eligibility_status": "no local match",
                "profile_match": 0,
                "confidence_label": "Low",
                "confidence_reason": "No local scheme matched the question.",
                "local_result_count": 0,
                "web_source_count": len(web_sources),
            }

        top = results[0]
        retrieval_score = top.get("retrieval_score", 0)
        eligibility = top["eligibility"]
        if eligibility["status"] == "likely eligible" and retrieval_score >= 5:
            confidence_label = "Strong"
            confidence_reason = "The top local source matched the query and profile checks."
        elif eligibility["status"] == "unlikely":
            confidence_label = "Needs review"
            confidence_reason = "The scheme matched the query, but at least one profile rule failed."
        elif web_sources:
            confidence_label = "Verify official source"
            confidence_reason = "Official web sources were discovered to supplement local matches."
        else:
            confidence_label = "Moderate"
            confidence_reason = "The scheme matched, but some profile details or source coverage are incomplete."

        if query_insights.get("needs_deadline_verification"):
            confidence_reason = f"{confidence_reason} Deadline data must be checked on the official source."

        return {
            "top_scheme_id": top["scheme"]["id"],
            "top_scheme_name": top["scheme"]["name"],
            "eligibility_status": eligibility["status"],
            "profile_match": eligibility["score"],
            "retrieval_score": retrieval_score,
            "adjusted_score": top.get("adjusted_score", 0),
            "confidence_label": confidence_label,
            "confidence_reason": confidence_reason,
            "local_result_count": len(results),
            "web_source_count": len(web_sources),
        }

    @staticmethod
    def _next_actions(
        profile_summary: dict[str, Any],
        query_insights: dict[str, Any],
        results: list[dict],
        web_sources: list[dict],
    ) -> list[str]:
        actions: list[str] = []
        if query_insights.get("profile_conflicts"):
            actions.append("Correct the conflicting profile field and ask again.")
        if profile_summary.get("missing_fields"):
            actions.append(f"Fill missing profile fields: {', '.join(profile_summary['missing_fields'][:4])}.")
        if query_insights.get("needs_deadline_verification"):
            actions.append("Check the official portal for the latest deadline before submitting.")
        if web_sources:
            actions.append("Open the discovered official source and compare its eligibility text with your profile.")
        if results:
            top_scheme = results[0]["scheme"]
            actions.append(f"Prepare documents for {top_scheme['name']}: {', '.join(top_scheme['documents'][:3])}.")
            actions.append(f"Start from the official source: {top_scheme['source_url']}")
        return actions[:5]

    @staticmethod
    def _should_discover_web_sources(question: str, results: list[dict]) -> tuple[bool, str]:
        if not results:
            return True, "no local candidates were retrieved"
        top = results[0]
        if top["retrieval_score"] < 1.0:
            return True, "top retrieval score was weak"
        if top["eligibility"]["status"] == "unlikely" and top["retrieval_score"] < 2.0:
            return True, "top local match was weak and unlikely for the citizen profile"

        domain_terms = {"solar", "panel", "panels", "renewable", "energy", "rooftop"}
        query_terms = set(meaningful_tokens(question))
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

        matched_terms = set(top.get("matched_terms", []))
        if (
            query_terms
            and len(matched_terms.intersection(query_terms)) < 2
            and top["retrieval_score"] < 2.0
            and top["eligibility"]["status"] != "likely eligible"
        ):
            return True, "local match used too few meaningful query terms"

        if top["eligibility"]["status"] == "unlikely":
            return False, "local dataset found a topical scheme, but profile rules made it unlikely"

        return False, "local official dataset had sufficient topical retrieval confidence"

    @staticmethod
    def _profile_adjusted_score(retrieval_score: float, eligibility: dict) -> float:
        status_bonus = {
            "likely eligible": 1.2,
            "possibly eligible": 0.45,
            "unlikely": -0.6,
        }.get(eligibility["status"], 0)
        return retrieval_score + status_bonus + (eligibility["score"] / 100) * 0.6
