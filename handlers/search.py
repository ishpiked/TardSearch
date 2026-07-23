from bs4 import BeautifulSoup
import urllib.parse

from handlers.config import session, rotate_agent, TIMEOUT, MAX_RESULTS
from handlers.utils import url_hash

BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
           "AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/120.0.0.0 Safari/537.36")

def expand_search_queries(query: str) -> list[str]:
    q = query.strip()
    base = [q, f"{q} news"]
    if not q.startswith(("what", "how", "why", "who", "where", "when", "which")):
        base.append(f"what is {q}")
        base.append(f"{q} explained")
    return base

def _search_ddgs(query: str) -> list[dict]:
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=15))
        parsed = []
        for r in results:
            title = (r.get("title") or "").strip()
            href = (r.get("href") or "").strip()
            body = (r.get("body") or "").strip()
            if title and href.startswith(("http://", "https://")):
                parsed.append({"title": title[:220], "url": href, "snippet": body})
        return parsed
    except Exception:
        pass
    return []

def _parse_ddg_html(html: str) -> list[dict]:
    results = []
    soup = BeautifulSoup(html, "html.parser")
    for x in soup.select(".result"):
        a = x.select_one(".result__title a") or x.select_one(".result__a")
        s = x.select_one(".result__snippet")
        if not a:
            continue
        href = a.get("href", "")
        real = href
        if "uddg=" in href:
            try:
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                real = parsed.get("uddg", [href])[0]
            except Exception:
                pass
        title = a.get_text(strip=True)
        if title and real.startswith(("http://", "https://")):
            results.append({
                "title": title[:220],
                "url": real,
                "snippet": (s.get_text(strip=True) if s else ""),
            })
    return results

def _search_ddg_html(query: str) -> list[dict]:
    try:
        r = session.get(
            f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}",
            headers={**session.headers, **rotate_agent()}, timeout=TIMEOUT
        )
        if r.status_code == 200:
            return _parse_ddg_html(r.text)
    except Exception:
        pass
    return []

SEARCH_METHODS = [_search_ddgs, _search_ddg_html]

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
    for method in SEARCH_METHODS:
        if len(candidates) >= 5:
            break
        for q in queries:
            for r in method(q):
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
