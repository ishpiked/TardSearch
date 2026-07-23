from concurrent.futures import ThreadPoolExecutor
from handlers.config import session, rotate_agent, TIMEOUT, MAX_RESULTS
from handlers.utils import url_hash
import urllib.parse

def _run_with_timeout(fn, args=(), timeout=10):
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn, *args)
        try:
            return fut.result(timeout=timeout)
        except Exception:
            return None

def _search_ddgs(query: str) -> list | None:
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=MAX_RESULTS))
        return results
    except Exception:
        return None

def _search_html(query: str) -> list | None:
    try:
        from bs4 import BeautifulSoup
        r = session.get(
            f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}",
            headers={**session.headers, **rotate_agent()}, timeout=TIMEOUT
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
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
    except Exception:
        return None

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

    raw = _run_with_timeout(_search_ddgs, (query,), timeout=3)
    if raw is None:
        raw = _run_with_timeout(_search_html, (query,), timeout=2)

    if raw:
        for r in raw:
            add(r.get("title"), r.get("href") or r.get("url"), r.get("body") or r.get("snippet"))

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
