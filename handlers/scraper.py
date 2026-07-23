import re, json
from bs4 import BeautifulSoup

from handlers.config import session, rotate_agent, TIMEOUT, ARTICLE_TEXT_LIMIT
from handlers.utils import source_name_from_url, text_key

_BAD_PARAGRAPH_RE = re.compile(
    r"^(advertisement|subscribe|sign up|sign in|log in|read more|cookie|cookies|"
    r"all rights reserved|share this|follow us|newsletter|related articles)",
    re.I,
)
_NOISE = ("enable javascript", "accept cookies", "privacy policy",
          "terms of service", "click here")

def _jsonld_payloads(soup):
    payloads = []
    for tag in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = tag.string or tag.get_text("", strip=True)
        if raw:
            try:
                payloads.append(json.loads(raw))
            except Exception:
                pass
    return payloads

def _jsonld_texts(soup):
    texts = []
    def collect(obj):
        if isinstance(obj, dict):
            for key in ("articleBody", "description", "text"):
                v = obj.get(key)
                if isinstance(v, str):
                    texts.append(v)
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    collect(v)
        elif isinstance(obj, list):
            for item in obj:
                collect(item)
    for p in _jsonld_payloads(soup):
        collect(p)
    return texts

def _meta_content(soup, *names):
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""

def _usable_text(text: str) -> bool:
    text = text.strip()
    if len(text) < 40:
        return False
    if _BAD_PARAGRAPH_RE.match(text):
        return False
    lowered = text.casefold()
    return not any(f in lowered for f in _NOISE)

def _paragraphs_from(container):
    paragraphs = []
    seen = set()
    for node in container.find_all(["p", "h2", "h3", "h4", "li"], recursive=True):
        text = node.get_text(" ", strip=True)
        k = text_key(text)
        if not k or k in seen or not _usable_text(text):
            continue
        seen.add(k)
        paragraphs.append(text)
    return paragraphs

def _extract_body_text(soup):
    seen = set()
    collected = []
    selectors = (
        "article", "main", "[role='main']", "[itemprop='articleBody']",
        "[data-testid='article-body']", "[data-test-id='article-body']",
        "[data-component='text-block']",
        "[class*='article-body']", "[class*='articleBody']", "[class*='article__body']",
        "[class*='story-body']", "[class*='storyBody']",
        ".article-body", ".article__body", ".article-content", ".article__content",
        ".story-body", ".story__body",
        ".entry-content", ".post-content", ".content-body",
        "#mw-content-text", ".mw-parser-output",
    )
    for selector in selectors:
        for el in soup.select(selector):
            for p in _paragraphs_from(el):
                k = text_key(p)
                if k and k not in seen:
                    seen.add(k)
                    collected.append(p)
    if collected:
        return collected
    parts = []
    seen = set()
    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)
        k = text_key(text)
        if not k or k in seen or not _usable_text(text):
            continue
        seen.add(k)
        parts.append(text)
    return parts

def scrape_article_deep(url: str) -> str:
    try:
        r = session.get(url, headers={**session.headers, **rotate_agent()}, timeout=TIMEOUT)
        if r.status_code != 200:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")

        title = _meta_content(soup, "og:title", "twitter:title") or (
            soup.title.string.strip() if soup.title and soup.title.string else ""
        )
        description = _meta_content(soup, "og:description", "twitter:description", "description")

        author = _meta_content(soup, "author", "article:author", "dc.creator", "parsely-author")
        if not author:
            for sel in ("[rel='author']", ".author", ".byline", "[class*='byline']"):
                node = soup.select_one(sel)
                if node:
                    t = node.get_text(" ", strip=True)
                    if t:
                        author = re.sub(r"^\s*(by|author)\s*[:\-]\s*", "", t.strip(), flags=re.I)
                        break

        date = ""
        for name in ("article:published_time", "article:modified_time", "og:updated_time",
                     "pubdate", "publishdate", "date", "datePublished", "dateModified"):
            val = _meta_content(soup, name)
            if val:
                date = val
                break
        if not date:
            for tag in soup.find_all("time"):
                dt = tag.get("datetime", "") or tag.get_text(" ", strip=True)
                if dt:
                    date = dt.strip()
                    break

        jsonld_texts = _jsonld_texts(soup)
        for tag in soup(["script", "style", "nav", "footer", "aside", "form", "header", "noscript", "svg"]):
            tag.decompose()

        paras = _extract_body_text(soup)
        body_text = " ".join(paras) if paras else ""

        candidates = [t for t in jsonld_texts if len(t.strip()) > 100]
        if body_text:
            candidates.append(body_text)
        best_body = max(candidates, key=len, default="")
        if not best_body:
            best_body = re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()

        full = re.sub(r"\s+", " ", best_body).strip()[:ARTICLE_TEXT_LIMIT]

        parts = []
        if title:
            parts.append(f"TITLE: {title}")
        if author:
            parts.append(f"AUTHOR: {author}")
        if date:
            parts.append(f"DATE: {date}")
        if description:
            parts.append(f"DESCRIPTION: {description}")
        parts.append(f"SOURCE: {source_name_from_url(url)}")
        if full:
            parts.append("")
            parts.append(full)
        return "\n".join(parts)
    except Exception:
        return ""