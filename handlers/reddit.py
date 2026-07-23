import json, re, urllib.parse
from urllib.parse import urljoin

from handlers.config import session, rotate_agent, REDLIB_INSTANCES
from handlers.utils import html_fragment_to_text, meta_content_from_html, extract_post_id, html_attr

def _post_from_reddit_payload(p: dict, post_id: str) -> dict:
    permalink = f"https://redd.it/{post_id}"
    if p.get("permalink"):
        v = p["permalink"]
        if v.startswith("/"):
            v = f"https://reddit.com{v}"
        if v.startswith(("http://", "https://")):
            permalink = v
    return {
        "title": p.get("title") or "N/A",
        "selftext": (p.get("selftext") or "").strip(),
        "author": p.get("author") or "[deleted]",
        "subreddit": p.get("subreddit") or "",
        "score": p.get("score") or p.get("ups") or 0,
        "num_comments": p.get("num_comments") or 0,
        "url": p.get("url") or permalink,
        "permalink": permalink,
    }

def _format_reddit_post(post: dict) -> str:
    lines = [f"TITLE: {post.get('title', 'Untitled')}"]
    lines.append(f"AUTHOR: u/{post.get('author', '[deleted]')} | SUBREDDIT: r/{post.get('subreddit', '')} | SCORE: {post.get('score', 0)}")
    selftext = post.get("selftext", "")
    if selftext:
        lines.append("")
        lines.append(selftext)
    lines.append(f"\nPERMALINK: {post.get('permalink', '')}")
    return "\n".join(lines)

def _first_reddit_listing_post(raw: dict | list) -> dict | None:
    if isinstance(raw, list) and raw:
        listing = raw[0]
    elif isinstance(raw, dict):
        listing = raw
    else:
        return None
    children = listing.get("data", {}).get("children", [])
    return children[0].get("data") if children else None

def fetch_pullpush_post(post_id: str) -> dict | None:
    try:
        r = session.get(
            "https://api.pullpush.io/reddit/search/submission/",
            params={"ids": post_id, "size": 1},
            timeout=6, headers=rotate_agent()
        )
        if r.status_code != 200:
            return None
        data = r.json()
        if not isinstance(data, dict) or data.get("error"):
            return None
        for item in data.get("data", []):
            if str(item.get("id", "")).lower() == post_id.lower():
                return _post_from_reddit_payload(item, post_id)
    except Exception:
        pass
    return None

def _post_from_redlib_html(html_text: str, post_id: str) -> dict | None:
    if not html_text or ("post_title" not in html_text and "post_body" not in html_text):
        return None
    block = re.search(
        r"""(?is)<div\s+class=['"][^'"]*\bpost\b[^'"]*\bhighlighted\b[^'"]*['"][^>]*>(.*?)(?=<!--\s*SORT FORM\s*-->|<div\s+id=['"]commentQueryForms|<div\s+class=['"][^'"]*\bcomments\b|$)""",
        html_text,
    )
    post_block = block.group(1) if block else html_text
    title = ""
    title_meta = meta_content_from_html(html_text, "title")
    if title_meta:
        title = re.sub(r"\s+-\s+r/[^-]+$", "", title_meta, flags=re.I).strip()
    if not title or title.lower() in {"reddit - dive into anything", "redlib"}:
        tm = re.search(r"""(?is)<h1\s+class=['"][^'"]*\bpost_title\b[^'"]*['"][^>]*>(.*?)</h1>""", post_block)
        if tm:
            title = html_fragment_to_text(tm.group(1))
    bm = re.search(
        r"""(?is)<div\s+class=['"][^'"]*\bpost_body\b[^'"]*['"][^>]*>(.*?)<!--\s*SC_ON\s*-->""",
        post_block
    )
    if not bm:
        bm = re.search(r"""(?is)<div\s+class=['"][^'"]*\bmd\b[^'"]*['"][^>]*>(.*?)</div>""", post_block)
    selftext = html_fragment_to_text(bm.group(1) if bm else "")
    author = (meta_content_from_html(html_text, "author") or "").removeprefix("u/")
    sub_name = ""
    sm = re.search(r"/r/([^/]+)/", html_text, re.I)
    if sm:
        sub_name = urllib.parse.unquote(sm.group(1))
    if not title and not selftext:
        return None
    permalink = f"https://reddit.com/r/{sub_name}/comments/{post_id}/" if sub_name else f"https://redd.it/{post_id}"
    return {
        "title": title or "Untitled",
        "selftext": selftext,
        "author": author or "[deleted]",
        "subreddit": sub_name,
        "score": 0, "num_comments": 0,
        "url": permalink, "permalink": permalink,
    }

def fetch_redlib_post(post_id: str, subreddit: str | None = None) -> dict | None:
    paths = []
    if subreddit:
        paths.append(f"/r/{urllib.parse.quote(subreddit, safe='')}/comments/{post_id}/")
    paths.append(f"/comments/{post_id}/")
    seen = set()
    for instance in REDLIB_INSTANCES:
        for path in paths:
            url = urljoin(instance + "/", path.lstrip("/"))
            if url in seen:
                continue
            seen.add(url)
            try:
                r = session.get(url, headers={"Accept": "text/html,application/xhtml+xml", **rotate_agent()}, timeout=7)
                if r.status_code >= 400:
                    continue
                post = _post_from_redlib_html(r.text, post_id)
                if post:
                    return post
            except Exception:
                pass
    return None

def _is_block_page(html: str) -> bool:
    if len(html) < 200:
        return True
    if "Please wait" in html[:1000] or "checking your browser" in html[:1000]:
        return True
    tm = re.search(r'(?is)<title>(.*?)</title>', html)
    if not tm or not tm.group(1).strip():
        return True
    title_text = tm.group(1).strip().lower()
    if title_text in {"reddit", "redlib", "just a moment", ""}:
        return True
    return False

def fetch_old_reddit_post(post_id: str, subreddit: str | None = None) -> dict | None:
    path = (
        f"/r/{urllib.parse.quote(subreddit, safe='')}/comments/{post_id}/"
        if subreddit
        else f"/comments/{post_id}/"
    )
    url = f"https://old.reddit.com{path}"
    for attempt in range(2):
        try:
            r = session.get(url, headers=rotate_agent(), timeout=10)
            if r.status_code >= 400:
                continue
            html = r.text
            if _is_block_page(html):
                continue

            selftext = ""
            thing_input = re.search(
                r'(?is)<input\s[^>]*name=["\']thing_id["\'][^>]*value=["\']t3_' + re.escape(post_id) + r'["\']',
                html
            )
            if thing_input:
                pb = re.search(
                    r'(?is)<div\s+class=["\']usertext-body[^"\']*["\'][^>]*>.*?<div\s+class=["\']md["\'][^>]*>(.*?)</div>\s*</div>',
                    html[thing_input.end():]
                )
                if pb:
                    selftext = html_fragment_to_text(pb.group(1))

            if not selftext:
                dm = re.search(r'(?is)<meta\s+name=["\']description["\'][^>]*content=["\']([^"\']+)["\']', html)
                if dm:
                    selftext = dm.group(1)

            title = ""
            tm = re.search(r'(?is)<title>(.*?)</title>', html)
            if tm:
                title = re.sub(r'\s+[-–—|:].*$', '', tm.group(1), flags=re.I).strip()

            author = ""
            am = re.search(r'(?is)<a\s+class=["\']author["\'][^>]*>(.*?)</a>', html)
            if am:
                author = re.sub(r'<[^>]+>', '', am.group(1)).strip()

            sub_name = subreddit or ""
            if not sub_name:
                sm = re.search(r'/r/([^/]+)/comments/' + re.escape(post_id), html)
                if sm:
                    sub_name = urllib.parse.unquote(sm.group(1))

            if not title and not selftext:
                continue

            permalink = f"https://reddit.com/r/{sub_name}/comments/{post_id}/" if sub_name else f"https://redd.it/{post_id}"
            return {
                "title": title or "Untitled",
                "selftext": selftext,
                "author": author or "[deleted]",
                "subreddit": sub_name,
                "score": 0, "num_comments": 0,
                "url": permalink, "permalink": permalink,
            }
        except Exception:
            continue
    return None

def fetch_via_allorigins(post_id: str) -> str | None:
    reddit_url = f"https://www.reddit.com/comments/{post_id}.json?raw_json=1"
    for endpoint in ("raw", "get"):
        proxy_url = f"https://api.allorigins.win/{endpoint}?url={urllib.parse.quote(reddit_url, safe='')}"
        try:
            r = session.get(proxy_url, headers={"User-Agent": "TardBot/1.0", "Accept": "application/json"}, timeout=8)
            if r.status_code != 200:
                continue
            if endpoint == "get":
                wrapper = r.json()
                raw = json.loads(wrapper.get("contents", "{}"))
            else:
                raw = r.json()
            p = _first_reddit_listing_post(raw)
            if p:
                return _format_reddit_post(_post_from_reddit_payload(p, post_id))
        except Exception:
            pass
    return None

def _canonical_post_url(html_text: str) -> str | None:
    if not html_text:
        return None
    for tag in re.findall(r"(?is)<meta\b[^>]*>", html_text):
        tn = (html_attr(tag, "name") or html_attr(tag, "property") or "").lower()
        if tn == "og:url":
            content = html_attr(tag, "content")
            if content and extract_post_id(content):
                return content
    link_match = re.search(r"""(?is)<link\s+[^>]*rel=['"]canonical['"][^>]*>""", html_text)
    if link_match:
        href = html_attr(link_match.group(0), "href")
        if href and extract_post_id(href):
            return href
    return None

def resolve_share_link(share_url: str) -> str | None:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "text/html"}
    final_url = share_url
    last_body = ""

    try:
        r = session.head(share_url, headers=headers, timeout=8, allow_redirects=True)
        final_url = str(r.url)
    except Exception:
        pass

    if not extract_post_id(final_url):
        try:
            r2 = session.get(share_url, headers=headers, timeout=10, allow_redirects=True)
            final_url = str(r2.url)
            last_body = r2.text
        except Exception:
            pass

    if extract_post_id(final_url):
        return final_url

    canonical = _canonical_post_url(last_body)
    if canonical:
        return canonical

    proxy_url = f"https://api.allorigins.win/get?url={urllib.parse.quote(share_url, safe='')}"
    try:
        r3 = session.get(proxy_url, headers={"User-Agent": "TardBot/1.0", "Accept": "application/json"}, timeout=12)
        if r3.status_code == 200:
            wrapper = r3.json()
            body = wrapper.get("contents") or ""
            proxied_url = str(wrapper.get("status", {}).get("url", ""))
            if extract_post_id(proxied_url):
                return proxied_url
            canonical = _canonical_post_url(body)
            if canonical:
                return canonical
    except Exception:
        pass

    return None

def format_reddit_post_text(post_id: str, subreddit: str | None = None) -> str | None:
    post = fetch_pullpush_post(post_id)
    if post:
        return _format_reddit_post(post)
    post = fetch_redlib_post(post_id, subreddit)
    if post:
        return _format_reddit_post(post)
    post = fetch_old_reddit_post(post_id, subreddit)
    if post:
        return _format_reddit_post(post)
    return fetch_via_allorigins(post_id)