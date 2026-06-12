from app.retrieval import HybridRetriever


def build_corrective_query(question: str) -> str:
    return f"{question} government scheme eligibility benefits documents"


def corrective_retrieve(retriever: HybridRetriever, question: str, top_k: int):
    rewritten_query = build_corrective_query(question)
    return rewritten_query, retriever.search(rewritten_query, top_k)

