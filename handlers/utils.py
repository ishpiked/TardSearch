import re, html
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

_REDDIT_URL_PATTERNS = [
    re.compile(r"reddit\.com/r/[^/]+/comments/([a-z0-9]+)", re.I),
    re.compile(r"redd\.it/([a-z0-9]+)",                     re.I),
    re.compile(r"reddit\.com/comments/([a-z0-9]+)",         re.I),
]
_SHARE_LINK_PATTERN = re.compile(
    r"https?://(?:www\.)?reddit\.com/r/[^/]+/s/([A-Za-z0-9]+)",
    re.I,
)

def text_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.strip().casefold())

def url_hash(url: str) -> str:
    try:
        parts = urlsplit(url)
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                 if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
        clean = urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), ""))
        return text_key(clean)
    except Exception:
        return text_key(url)

def source_name_from_url(url: str) -> str:
    try:
        host = urlsplit(url).netloc.lower().removeprefix("www.")
        return host or "source"
    except Exception:
        return "source"

def extract_post_id(text: str) -> str | None:
    for pat in _REDDIT_URL_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).lower()
    return None

def extract_subreddit(url: str) -> str | None:
    m = re.search(r"/r/([^/]+)/", url, re.I)
    return m.group(1) if m else None

def extract_share_link(text: str) -> str | None:
    m = _SHARE_LINK_PATTERN.search(text)
    return m.group(0) if m else None

def html_fragment_to_text(fragment: str | None) -> str:
    if not fragment:
        return ""
    text = re.sub(r"(?is)<!--.*?-->", "", fragment)
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)<li\b[^>]*>", "- ", text)
    text = re.sub(r"(?is)</(p|div|blockquote|h[1-6]|li|ul|ol)>", "\n\n", text)
    text = re.sub(r"(?is)<a\b[^>]*>(.*?)</a>", r"\1", text)
    text = re.sub(r"(?is)<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def html_attr(tag: str, name: str) -> str | None:
    m = re.search(rf"""\b{re.escape(name)}\s*=\s*(['"])(.*?)\1""", tag, re.I | re.DOTALL)
    return html.unescape(m.group(2)).strip() if m else None

def meta_content_from_html(html_text: str, name: str) -> str | None:
    for tag in re.findall(r"(?is)<meta\b[^>]*>", html_text or ""):
        tn = (html_attr(tag, "name") or html_attr(tag, "property") or "").lower()
        if tn == name.lower():
            return html_attr(tag, "content")
    return None
