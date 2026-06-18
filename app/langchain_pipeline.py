from typing import Any

from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnableLambda
from pydantic import ConfigDict

from .models import Scheme
from .retrieval import HybridRetriever


class SchemeLangChainRetriever(BaseRetriever):
    """LangChain retriever adapter over the project-local hybrid scheme index."""

    retriever: HybridRetriever
    top_k: int = 3

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get_relevant_documents(self, query: str, *, run_manager: Any = None) -> list[Document]:
        return [
            scheme_to_document(scheme, score, matched_terms)
            for scheme, score, matched_terms in self.retriever.search(query, self.top_k)
        ]


def scheme_to_document(scheme: Scheme, score: float, matched_terms: list[str]) -> Document:
    content = "\n".join(
        [
            f"Scheme: {scheme.name}",
            f"Category: {scheme.category}",
            f"States: {', '.join(scheme.states)}",
            f"Summary: {scheme.summary}",
            f"Benefits: {'; '.join(scheme.benefits)}",
            f"Documents: {'; '.join(scheme.documents)}",
            f"Apply steps: {'; '.join(scheme.apply_steps)}",
            f"Official excerpt: {scheme.official_excerpt[:1200]}",
        ]
    )
    return Document(
        page_content=content,
        metadata={
            "scheme": scheme.model_dump(),
            "retrieval_score": score,
            "matched_terms": matched_terms,
            "source": scheme.source_url,
            "source_title": scheme.source_title,
        },
    )


def document_to_retrieval_result(document: Document) -> tuple[Scheme, float, list[str]]:
    metadata = document.metadata
    return (
        Scheme(**metadata["scheme"]),
        float(metadata.get("retrieval_score", 0)),
        list(metadata.get("matched_terms", [])),
    )


def retrieve_schemes_with_langchain(
    retriever: HybridRetriever,
    question: str,
    top_k: int,
) -> list[tuple[Scheme, float, list[str]]]:
    langchain_retriever = SchemeLangChainRetriever(retriever=retriever, top_k=top_k)
    documents = langchain_retriever.invoke(question)
    return [document_to_retrieval_result(document) for document in documents]


ANSWER_PROMPT = PromptTemplate.from_template("{guidance_block}{source_block}{local_block}")
ANSWER_CHAIN = ANSWER_PROMPT | RunnableLambda(lambda prompt_value: prompt_value.to_string())


def build_template_answer_with_langchain(
    guidance_block: str,
    source_block: str,
    local_block: str,
) -> str:
    return ANSWER_CHAIN.invoke(
        {
            "guidance_block": guidance_block,
            "source_block": source_block,
            "local_block": local_block,
        }
    )
