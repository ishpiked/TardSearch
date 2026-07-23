from bs4 import BeautifulSoup
import urllib.parse, re

from handlers.config import session, rotate_agent, TIMEOUT, MAX_RESULTS
from handlers.utils import url_hash

BING_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

def expand_search_queries(query: str) -> list[str]:
    q = query.strip()
    base = [q, f"{q} news"]
    if not q.startswith(("what", "how", "why", "who", "where", "when", "which")):
        base.append(f"what is {q}")
        base.append(f"{q} explained")
    return base

def _search_bing(query: str) -> list[dict]:
    results = []
    try:
        r = session.get(
            f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count=20",
            headers=BING_HEADERS, timeout=TIMEOUT
        )
        if r.status_code != 200:
            return results
        soup = BeautifulSoup(r.text, "html.parser")
        for item in soup.select("#b_results > li.b_algo"):
            h2 = item.select_one("h2 a")
            if not h2:
                continue
            href = h2.get("href", "")
            title = h2.get_text(strip=True)
            if not title or not href.startswith(("http://", "https://")):
                continue
            snippet_el = item.select_one(".b_caption p")
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            results.append({
                "title": title[:220],
                "url": href,
                "snippet": snippet,
            })
    except Exception:
        pass
    return results

def _search_startpage(query: str) -> list[dict]:
    results = []
    try:
        r = session.get(
            f"https://www.startpage.com/sp/search?query={urllib.parse.quote(query)}",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "text/html"},
            timeout=TIMEOUT
        )
        if r.status_code != 200:
            return results
        soup = BeautifulSoup(r.text, "html.parser")
        for item in soup.select("article.result, .w-gl__result, .result"):
            a = item.select_one("h3 a, .result-title a, a.result-title")
            if not a:
                a = item.find("a", href=re.compile(r"^https?://"))
            if not a:
                continue
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if not title or not href.startswith(("http://", "https://")):
                continue
            snippet_el = item.select_one(".result-description, .w-gl__description, p")
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            results.append({
                "title": title[:220],
                "url": href,
                "snippet": snippet,
            })
    except Exception:
        pass
    return results

def search_web_deep(query: str) -> list[dict]:
    candidates = []
    seen_hashes = set()

    def add(title, url, snippet):
        if not url or not url.startswith(("http://", "https://")):
            return
        h = url_hash(url)
        if h in seen_hashes:
            return
        seen_hashes.add(h)
        candidates.append({
            "title": (title or "Untitled").strip()[:220],
            "url": url,
            "snippet": (snippet or "").strip(),
        })

    queries = expand_search_queries(query)
    for q in queries:
        for r in _search_bing(q):
            add(r["title"], r["url"], r["snippet"])

    if len(candidates) < 3:
        for q in queries:
            for r in _search_startpage(q):
                add(r["title"], r["url"], r["snippet"])

    seen_domains = set()
    unique = []
    for c in candidates:
        domain = urllib.parse.urlsplit(c["url"]).netloc.lower()
        if "youtube" in domain:
            continue
        if domain not in seen_domains:
            seen_domains.add(domain)
            unique.append(c)
    return unique[:MAX_RESULTS]
