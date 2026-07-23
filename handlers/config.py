import os, time
import requests

MAX_RESULTS = 3
MAX_WORKERS = 5
TIMEOUT = 3
ARTICLE_TEXT_LIMIT = 3000

REDLIB_INSTANCES = tuple(
    i.rstrip("/") for i in os.getenv(
        "REDLIB_INSTANCES",
        "https://r.genit.al https://redlib.perennialte.ch https://redlib.hintstar.com https://reddit.nerdvpn.de https://redlib.catsarch.com"
    ).replace(",", " ").split() if i.strip()
)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]

session = requests.Session()
session.headers.update({"Accept-Language": "en-US,en;q=0.9"})

def rotate_agent():
    return {"User-Agent": USER_AGENTS[int(time.time()) % len(USER_AGENTS)]}
