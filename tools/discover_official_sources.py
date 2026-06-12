import re
import ssl
import json
import os
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen


OFFICIAL_HOST_ALLOWLIST = {
    "myscheme.gov.in",
    "www.myscheme.gov.in",
    "india.gov.in",
    "www.india.gov.in",
    "pmkisan.gov.in",
    "www.pmkisan.gov.in",
    "pmjay.gov.in",
    "www.pmjay.gov.in",
    "nha.gov.in",
    "www.nha.gov.in",
    "pmaymis.gov.in",
    "www.pmaymis.gov.in",
    "standupmitra.in",
    "www.standupmitra.in",
    "pmsonline.bihar.gov.in",
    "instpmsonline.bihar.gov.in",
    "cmladlibahna.mp.gov.in",
    "pmsuryaghar.gov.in",
    "www.pmsuryaghar.gov.in",
    "solarrooftop.gov.in",
    "www.solarrooftop.gov.in",
}
MYSCHEME_API_KEY = os.getenv("MYSCHEME_API_KEY")

BLOCKED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".zip", ".mp4", ".mp3")


@dataclass
class WebSource:
    title: str
    url: str
    snippet: str
    text: str

    def model_dump(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "text_excerpt": self.text[:1200],
        }


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
        text = normalize_text(data)
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return normalize_text(" ".join(self.parts))


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text)).strip()


def is_official_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if not parsed.scheme.startswith("http") or not host:
        return False
    if parsed.path.lower().endswith(BLOCKED_EXTENSIONS):
        return False
    return host.endswith(".gov.in") or host in OFFICIAL_HOST_ALLOWLIST


def discover_official_sources(question: str, max_results: int = 3) -> list[dict]:
    seeded_sources = seed_official_sources(question)
    if len(seeded_sources) >= max_results:
        return seeded_sources[:max_results]

    myscheme_sources = search_myscheme(question, max_results=max_results)
    merged_sources = merge_sources(seeded_sources, myscheme_sources, max_results)
    if merged_sources:
        return merged_sources

    candidates = []
    seen = set()
    for query in build_search_queries(question):
        search_results = []
        duck_html = fetch_duckduckgo_html(query)
        search_results.extend(parse_duckduckgo_results(duck_html))
        if not search_results:
            bing_html = fetch_bing_html(query)
            search_results.extend(parse_bing_results(bing_html))
        for title, url, snippet in search_results:
            if url in seen or not is_official_url(url):
                continue
            seen.add(url)
            text = fetch_page_text(url)
            if len(text) < 120:
                continue
            candidates.append(WebSource(title=title or url, url=url, snippet=snippet, text=text).model_dump())
            if len(candidates) >= max_results:
                return candidates
    return candidates


def seed_official_sources(question: str) -> list[dict]:
    normalized = question.lower()
    solar_terms = {"solar", "rooftop", "panel", "panels", "surya", "ghar"}
    if not any(term in normalized for term in solar_terms):
        return []

    url = "https://www.pmsuryaghar.gov.in/"
    text = fetch_page_text(url)
    if not text:
        text = "National Portal for Rooftop Solar - Ministry of New and Renewable Energy"
    return [
        WebSource(
            title="PM Surya Ghar / National Portal for Rooftop Solar",
            url=url,
            snippet=(
                "Official national rooftop solar portal from the Ministry of New and Renewable Energy. "
                "Use this source for central rooftop solar subsidy, application tracking, and consumer guidance."
            ),
            text=text,
        ).model_dump()
    ]


def merge_sources(seed_sources: list[dict], discovered_sources: list[dict], max_results: int) -> list[dict]:
    merged = []
    seen = set()
    for source in [*seed_sources, *discovered_sources]:
        url = source.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        merged.append(source)
        if len(merged) >= max_results:
            break
    return merged


def search_myscheme(question: str, max_results: int = 3) -> list[dict]:
    if not MYSCHEME_API_KEY:
        return []

    keyword = simplify_scheme_query(question)
    url = (
        "https://api.myscheme.gov.in/search/v6/schemes"
        f"?lang=en&q=%5B%5D&keyword={quote(keyword)}&sort=&from=0&size={max_results}"
    )
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 CivicAidRAG official myScheme discovery",
            "x-api-key": MYSCHEME_API_KEY,
            "Origin": "https://www.myscheme.gov.in",
            "Referer": "https://www.myscheme.gov.in/",
            "Accept": "application/json, text/plain, */*",
        },
    )
    try:
        with urlopen(request, timeout=25, context=ssl.create_default_context()) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return []

    items = payload.get("data", {}).get("hits", {}).get("items", [])
    sources = []
    for item in items[:max_results]:
        fields = item.get("fields", {})
        slug = fields.get("slug")
        if not slug:
            continue
        url = f"https://www.myscheme.gov.in/schemes/{slug}"
        title = fields.get("schemeName") or fields.get("schemeShortTitle") or url
        description = fields.get("briefDescription") or ""
        tags = ", ".join(fields.get("tags") or [])
        state = ", ".join(fields.get("beneficiaryState") or [])
        category = ", ".join(fields.get("schemeCategory") or [])
        page_text = fetch_page_text(url)
        text = page_text or normalize_text(f"{title}. {description}. State: {state}. Category: {category}. Tags: {tags}.")
        sources.append(
            WebSource(
                title=title,
                url=url,
                snippet=description,
                text=text,
            ).model_dump()
        )
    return sources


def simplify_scheme_query(question: str) -> str:
    stop_words = {
        "eligibility",
        "documents",
        "document",
        "official",
        "government",
        "scheme",
        "yojana",
        "benefits",
        "apply",
        "application",
        "am",
        "and",
        "are",
        "as",
        "at",
        "by",
        "center",
        "central",
        "centre",
        "do",
        "does",
        "for",
        "from",
        "how",
        "what",
        "which",
        "can",
        "i",
        "in",
        "is",
        "it",
        "me",
        "much",
        "my",
        "of",
        "on",
        "or",
        "state",
        "states",
        "the",
        "to",
        "with",
        "get",
        "need",
        "help",
    }
    tokens = re.findall(r"[a-zA-Z0-9]+", question.lower())
    useful = [token for token in tokens if token not in stop_words]
    return " ".join(useful[:6]) or question


def build_search_queries(question: str) -> list[str]:
    base = f"{question} official government scheme eligibility documents"
    return [
        f"{base} site:myscheme.gov.in",
        f"{base} site:gov.in",
        f"{base} site:india.gov.in",
    ]


def fetch_duckduckgo_html(query: str, timeout: int = 20) -> str:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 CivicAidRAG official source discovery",
            "Accept": "text/html",
        },
    )
    try:
        with urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
            return response.read(1_000_000).decode("utf-8", errors="replace")
    except OSError:
        return ""


def fetch_bing_html(query: str, timeout: int = 20) -> str:
    url = f"https://www.bing.com/search?q={quote_plus(query)}"
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 CivicAidRAG official source discovery",
            "Accept": "text/html",
        },
    )
    try:
        with urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
            return response.read(1_000_000).decode("utf-8", errors="replace")
    except OSError:
        return ""


def parse_duckduckgo_results(html: str) -> list[tuple[str, str, str]]:
    results = []
    for match in re.finditer(
        r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        raw_url = unescape(match.group("href"))
        url = unwrap_duckduckgo_url(raw_url)
        title = clean_html(match.group("title"))
        snippet = find_nearby_snippet(html, match.end())
        results.append((title, url, snippet))
    return results


def parse_bing_results(html: str) -> list[tuple[str, str, str]]:
    results = []
    for match in re.finditer(r'<li class="b_algo".*?</li>', html, flags=re.IGNORECASE | re.DOTALL):
        block = match.group(0)
        link = re.search(r'<h2[^>]*>.*?<a[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>', block, flags=re.IGNORECASE | re.DOTALL)
        if not link:
            continue
        snippet_match = re.search(r'<p[^>]*>(.*?)</p>', block, flags=re.IGNORECASE | re.DOTALL)
        results.append(
            (
                clean_html(link.group("title")),
                unescape(link.group("href")),
                clean_html(snippet_match.group(1)) if snippet_match else "",
            )
        )
    return results


def unwrap_duckduckgo_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.path.startswith("/l/"):
        query = parse_qs(parsed.query)
        if "uddg" in query:
            return unquote(query["uddg"][0])
    return url


def clean_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return normalize_text(value)


def find_nearby_snippet(html: str, start: int) -> str:
    window = html[start : start + 1200]
    match = re.search(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>|<div[^>]+class="result__snippet"[^>]*>(.*?)</div>', window, re.DOTALL)
    if not match:
        return ""
    return clean_html(match.group(1) or match.group(2) or "")


def fetch_page_text(url: str, timeout: int = 25) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 CivicAidRAG official source fetcher",
            "Accept": "text/html,application/xhtml+xml,text/plain",
        },
    )
    try:
        with urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
            content_type = response.headers.get_content_type()
            if content_type and "html" not in content_type and "text" not in content_type:
                return ""
            body = response.read(1_500_000)
            charset = response.headers.get_content_charset() or "utf-8"
            html = body.decode(charset, errors="replace")
            parser = TextExtractor()
            parser.feed(html)
            return parser.text()
    except OSError:
        return ""
