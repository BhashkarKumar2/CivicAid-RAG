from app.retrieval import HybridRetriever


def retrieve_schemes(retriever: HybridRetriever, question: str, top_k: int):
    return retriever.search(question, top_k)

