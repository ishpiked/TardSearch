from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from groq import Groq
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

from handlers.config import MAX_WORKERS, ARTICLE_TEXT_LIMIT
from handlers.search import search_web_deep
from handlers.scraper import scrape_article_deep
from handlers.reddit import format_reddit_post_text, resolve_share_link
from handlers.utils import extract_post_id, extract_subreddit, extract_share_link

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MODELS = [
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.1-8b-instant",
    "qwen/qwen3.6-27b",
]

def _call_llm(messages, max_tokens=1024):
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return None
    client = Groq(api_key=key)
    for model in MODELS:
        try:
            r = client.chat.completions.create(
                model=model, messages=messages, temperature=0.1, max_tokens=max_tokens,
            )
            return r.choices[0].message.content
        except Exception:
            pass
    return None

@app.get("/")
def root():
    return {"status": "online"}

def fetch_content(url: str) -> str:
    share_url = extract_share_link(url)
    if share_url:
        resolved = resolve_share_link(share_url)
        if resolved:
            url = resolved
    post_id = extract_post_id(url)
    if post_id:
        sub = extract_subreddit(url)
        reddit_text = format_reddit_post_text(post_id, sub)
        if reddit_text:
            return reddit_text
        return ""
    return scrape_article_deep(url)

@app.get("/search")
def search(q: str):
    try:
        results = search_web_deep(q)
        if not results:
            return {
                "query": q, "answer": "No relevant results found for your query.",
                "sources_discovered": 0, "sources_scraped": 0,
                "sources_summarized": 0, "per_source_summaries": []
            }

        scraped = {}
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(fetch_content, r["url"]): r for r in results}
            for f in as_completed(futures):
                r = futures[f]
                try:
                    body = f.result()
                    if body and len(body) >= 200:
                        scraped[r["url"]] = body
                except Exception:
                    pass

        if not scraped:
            return {
                "query": q, "answer": "Insufficient content was extracted to answer your query.",
                "sources_discovered": len(results), "sources_scraped": 0,
                "sources_summarized": 0, "per_source_summaries": []
            }

        context = "\n\n".join(
            f"TITLE: {r['title']}\nURL: {r['url']}\nSNIPPET: {r.get('snippet', '')}\nCONTENT: {scraped.get(r['url'], '')[:ARTICLE_TEXT_LIMIT]}"
            for r in results if r['url'] in scraped
        )

        answer = _call_llm(
            [{"role": "user", "content": (
                f"Question: {q}\n\n"
                f"Below are the raw web sources:\n\n{context}\n\n"
                "Synthesize these into a concise, thorough answer. "
                "Include specific facts, data, and cite sources by title. "
                "Note any uncertainty or conflicting information."
            )}],
            max_tokens=1024,
        )

        if not answer:
            return JSONResponse({"error": "all models failed"}, status_code=500)

        return JSONResponse({
            "query": q,
            "sources_discovered": len(results),
            "sources_scraped": len(scraped),
            "sources_summarized": len(scraped),
            "per_source_summaries": [
                {"title": r["title"], "url": r["url"], "summary": scraped.get(r["url"], "")[:500]}
                for r in results if r["url"] in scraped
            ],
            "answer": answer,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
