import json
import re
import ssl
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent.parent
SOURCE_PATH = BASE_DIR / "data" / "official_sources.json"
OUTPUT_PATH = BASE_DIR / "data" / "official_schemes.json"
REPORT_PATH = BASE_DIR / "data" / "official_ingestion_report.json"


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data):
        if self.skip_depth:
            return
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return normalize_text(" ".join(self.parts))


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _validate_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Only absolute HTTP(S) URLs can be fetched")


def _urlopen_http(request: Request, *, timeout: int, context: ssl.SSLContext):
    _validate_http_url(request.full_url)
    # Bandit B310 is acceptable here because the scheme is validated immediately above.
    return urlopen(request, timeout=timeout, context=context)  # nosec B310


def fetch_page_text(url: str, timeout: int = 45) -> tuple[str, str | None]:
    request = Request(
        url,
        headers={
            "User-Agent": "CivicAidRAG/0.1 official-source-ingestion",
            "Accept": "text/html,application/xhtml+xml,text/plain",
        },
    )
    context = ssl.create_default_context()
    last_error = None
    for _ in range(2):
        try:
            with _urlopen_http(request, timeout=timeout, context=context) as response:
                body = response.read(2_000_000)
                charset = response.headers.get_content_charset() or "utf-8"
                html = body.decode(charset, errors="replace")
                parser = TextExtractor()
                parser.feed(html)
                text = parser.text()
                if text:
                    return text, None
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
            last_error = str(error)
    return "", last_error or "empty response"


def choose_summary(name: str, fallback: dict, source_text: str) -> str:
    if source_text and len(source_text) > 120:
        sentences = re.split(r"(?<=[.!?])\s+", source_text)
        blocked = [
            "powered by",
            "sign out",
            "screen reader",
            "quick links",
            "contact us",
            "something went wrong",
            "captcha",
            "login",
        ]
        preferred_terms = [
            "scheme",
            "scholarship",
            "financial assistance",
            "income support",
            "health cover",
            "housing",
            "eligible",
            "benefit",
            "loan",
        ]
        useful = [
            sentence
            for sentence in sentences
            if len(sentence) > 60
            and not any(term in sentence.lower() for term in blocked)
            and any(term in sentence.lower() for term in preferred_terms)
        ]
        if useful:
            return normalize_text(useful[0])[:550]
    return fallback["summary"]


def build_scheme(source: dict) -> tuple[dict, dict]:
    fetched_pages = []
    combined_text_parts = []
    for url in source["source_urls"]:
        text, error = fetch_page_text(url)
        fetched_pages.append(
            {
                "url": url,
                "status": "ok" if text else "failed",
                "chars": len(text),
                "error": error,
            }
        )
        if text:
            combined_text_parts.append(text)

    official_text = normalize_text(" ".join(combined_text_parts))
    fallback = source["fallback"]
    scheme = {
        "id": source["id"],
        "name": source["name"],
        "category": source["category"],
        "states": source["rules"]["states"],
        "summary": choose_summary(source["name"], fallback, official_text),
        "benefits": fallback["benefits"],
        "eligibility": source["rules"],
        "documents": fallback["documents"],
        "apply_steps": fallback["apply_steps"],
        "source_title": source["source_title"],
        "source_url": source["source_url"],
        "official_sources": source["source_urls"],
        "official_excerpt": official_text[:2500],
    }
    report = {
        "id": source["id"],
        "name": source["name"],
        "fetched_pages": fetched_pages,
        "official_excerpt_chars": len(scheme["official_excerpt"]),
    }
    return scheme, report


def ingest() -> dict:
    sources = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    schemes = []
    reports = []
    for source in sources:
        scheme, report = build_scheme(source)
        schemes.append(scheme)
        reports.append(report)

    OUTPUT_PATH.write_text(json.dumps(schemes, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORT_PATH.write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"schemes": len(schemes), "output": str(OUTPUT_PATH), "report": str(REPORT_PATH)}


if __name__ == "__main__":
    result = ingest()
    print(json.dumps(result, indent=2))
    if any(
        page["status"] == "failed"
        for report in json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        for page in report["fetched_pages"]
    ):
        sys.exit(2)
