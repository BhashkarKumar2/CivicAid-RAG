import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from .models import Scheme

TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")

STOPWORDS = {
    "a",
    "am",
    "and",
    "are",
    "as",
    "at",
    "by",
    "can",
    "center",
    "central",
    "centre",
    "do",
    "does",
    "for",
    "from",
    "get",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "much",
    "my",
    "need",
    "of",
    "on",
    "or",
    "state",
    "the",
    "to",
    "what",
    "which",
    "with",
}

SYNONYMS = {
    "scholarship": ["student", "education", "college", "school", "financial"],
    "health": ["hospital", "medical", "insurance", "treatment"],
    "farmer": ["agriculture", "crop", "land", "kisan"],
    "business": ["entrepreneur", "loan", "startup", "self-employed"],
    "house": ["housing", "home", "awas", "property"],
    "documents": ["aadhaar", "certificate", "proof", "application", "eligibility"],
    "pmay": ["awas", "housing", "house", "urban"],
    "pmjay": ["ayushman", "health", "hospital", "treatment", "insurance"],
    "ab": ["ayushman", "health", "hospital", "treatment", "insurance"],
    "solar": ["rooftop", "panel", "panels", "renewable", "energy", "subsidy", "incentive"],
    "panel": ["solar", "rooftop", "renewable", "energy", "subsidy"],
    "panels": ["solar", "rooftop", "renewable", "energy", "subsidy"],
    "subsidy": ["assistance", "incentive", "benefit"],
}

HINDI_PHRASES = {
    "छात्रवृत्ति": "scholarship education student financial",
    "छात्र": "student education",
    "बिहार": "bihar",
    "ओबीसी": "obc",
    "किसान": "farmer agriculture kisan",
    "इलाज": "health hospital treatment medical",
    "अस्पताल": "health hospital treatment",
    "घर": "house housing awas",
    "लोन": "loan business entrepreneur",
    "व्यवसाय": "business entrepreneur",
    "दस्तावेज": "documents aadhaar certificate proof",
}


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def meaningful_tokens(text: str) -> list[str]:
    return [token for token in tokenize(text) if token not in STOPWORDS and len(token) > 1]


def expand_query(query: str) -> str:
    normalized_query = normalize_query(query)
    tokens = meaningful_tokens(normalized_query)
    additions: list[str] = []
    for token in tokens:
        additions.extend(SYNONYMS.get(token, []))
    return f"{normalized_query} {' '.join(additions)}"


def normalize_query(query: str) -> str:
    additions = [english for hindi, english in HINDI_PHRASES.items() if hindi in query]
    return f"{query} {' '.join(additions)}"


def scheme_text(scheme: Scheme) -> str:
    eligibility = scheme.eligibility
    return " ".join(
        [
            scheme.name,
            scheme.category,
            scheme.summary,
            " ".join(scheme.states),
            " ".join(scheme.benefits),
            " ".join(scheme.documents),
            " ".join(scheme.apply_steps),
            " ".join(eligibility.get("occupation", [])),
            " ".join(eligibility.get("categories", [])),
            " ".join(scheme.official_sources),
            scheme.official_excerpt,
        ]
    )


class HybridRetriever:
    def __init__(self, schemes: list[Scheme]):
        self.schemes = schemes
        self.documents = [tokenize(scheme_text(scheme)) for scheme in schemes]
        self.doc_freq: defaultdict[str, int] = defaultdict(int)
        for doc in self.documents:
            for token in set(doc):
                self.doc_freq[token] += 1
        self.avg_doc_len = sum(len(doc) for doc in self.documents) / max(len(self.documents), 1)

    @classmethod
    def from_json(cls, path: Path) -> "HybridRetriever":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls([Scheme(**item) for item in data])

    def search(self, query: str, top_k: int = 3) -> list[tuple[Scheme, float, list[str]]]:
        expanded = expand_query(query)
        query_tokens = meaningful_tokens(expanded)
        if not query_tokens:
            return []

        scored: list[tuple[Scheme, float, list[str]]] = []
        for scheme, doc in zip(self.schemes, self.documents):
            bm25 = self._bm25(query_tokens, doc)
            overlap = self._semantic_overlap(query_tokens, doc)
            score = bm25 + overlap
            matched = sorted(set(query_tokens).intersection(doc))[:8]
            scored.append((scheme, score, matched))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]

    def _bm25(self, query_tokens: list[str], doc: list[str]) -> float:
        counts = Counter(doc)
        score = 0.0
        k1 = 1.5
        b = 0.75
        total_docs = len(self.documents)
        for token in query_tokens:
            if token not in counts:
                continue
            idf = math.log((total_docs - self.doc_freq[token] + 0.5) / (self.doc_freq[token] + 0.5) + 1)
            tf = counts[token]
            denom = tf + k1 * (1 - b + b * len(doc) / max(self.avg_doc_len, 1))
            score += idf * (tf * (k1 + 1)) / denom
        return score

    def _semantic_overlap(self, query_tokens: list[str], doc: list[str]) -> float:
        query_set = set(query_tokens)
        doc_set = set(doc)
        if not query_set or not doc_set:
            return 0.0
        return len(query_set.intersection(doc_set)) / len(query_set.union(doc_set))
