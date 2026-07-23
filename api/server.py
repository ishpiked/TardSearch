from fastapi import FastAPI, APIRouter
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

router = APIRouter(prefix=os.getenv("API_PREFIX", "/api" if os.getenv("VERCEL") else ""))

@router.get("/")
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

@router.get("/search")
def search(q: str):
    try:
        key = os.getenv("GROQ_API_KEY")
        if not key:
            return {"error": "missing GROQ key"}
        client = Groq(api_key=key)

        results = search_web_deep(q)
        if not results:
            return {"query": q, "answer": "No relevant results found for your query.", "sources_discovered": 0, "sources_scraped": 0, "sources_summarized": 0, "per_source_summaries": []}

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
            return {"query": q, "answer": "Insufficient content was extracted to answer your query.", "sources_discovered": len(results), "sources_scraped": 0, "sources_summarized": 0, "per_source_summaries": []}

        summaries = []

        def summarize_source(title, url, snippet, body):
            prompt = (
                f"Query: {q}\n\n"
                f"Source: {title}\n"
                f"URL: {url}\n"
                f"Snippet: {snippet}\n\n"
                f"Content:\n{body[:ARTICLE_TEXT_LIMIT]}\n\n"
                "Extract and summarize the key information from this source "
                "that is relevant to the query. Focus on specific facts, data, "
                "quotes, names, dates, and evidence. Keep the summary concise "
                "(2-4 paragraphs) but comprehensive. If the source is not "
                "relevant, say so briefly."
            )
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1024,
            )
            return {
                "title": title,
                "url": url,
                "summary": resp.choices[0].message.content,
            }

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            sum_futures = {}
            for r in results:
                body = scraped.get(r["url"])
                if not body:
                    continue
                sum_futures[
                    ex.submit(
                        summarize_source,
                        r["title"],
                        r["url"],
                        r.get("snippet", ""),
                        body,
                    )
                ] = r
            for f in as_completed(sum_futures):
                try:
                    summaries.append(f.result())
                except Exception:
                    pass

        if not summaries:
            return {"query": q, "answer": "Insufficient content was extracted to answer your query.", "sources_discovered": len(results), "sources_scraped": len(scraped), "sources_summarized": 0, "per_source_summaries": []}

        context = "\n\n".join(
            f"<SOURCE>{s['title']}</SOURCE>\n"
            f"<URL>{s['url']}</URL>\n"
            f"<SUMMARY>\n{s['summary']}\n</SUMMARY>"
            for s in summaries
        )

        prompt = (
            f"Question: {q}\n\n"
            "Below are per-source summaries extracted from web data. "
            "Synthesize them into a thorough, well-structured answer.\n\n"
            "Requirements:\n"
            "- Synthesize information across all sources, noting agreement or disagreement\n"
            "- Include specific numbers, dates, names, locations, and concrete evidence\n"
            "- Organize logically (chronological, thematic, or comparative)\n"
            "- Mention any uncertainty or conflicting information\n"
            "- Cite sources using <SOURCE> tags\n\n"
            f"SOURCES:\n{context}\n\n"
            "Answer:"
        )

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=4096,
        )

        return JSONResponse({
            "query": q,
            "sources_discovered": len(results),
            "sources_scraped": len(scraped),
            "sources_summarized": len(summaries),
            "per_source_summaries": summaries,
            "answer": response.choices[0].message.content,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)