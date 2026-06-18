from app.langchain_pipeline import retrieve_schemes_with_langchain
from app.retrieval import HybridRetriever


def retrieve_schemes(retriever: HybridRetriever, question: str, top_k: int):
    return retrieve_schemes_with_langchain(retriever, question, top_k)
