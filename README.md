# Tard

Deep research API. Searches the web from multiple angles, scrapes full content (articles + Reddit), summarizes every source individually via Groq LLaMA, then synthesizes a final answer.

## Usage

```
GET /api/search?q=<query>
```

Returns:

```json
{
  "query": "latest on AI regulation",
  "sources_discovered": 35,
  "sources_scraped": 20,
  "sources_summarized": 18,
  "per_source_summaries": [
    { "title": "...", "url": "...", "summary": "..." }
  ],
  "answer": "AI regulation is evolving rapidly..."
}
```

## Pipeline

1. **Search** — Expands query into multiple variations, searches Bing + Startpage fallback, deduplicates by domain (up to 50 results)
2. **Scrape** — Fetches every result in parallel. Articles use a deep HTML scraper (JSON-LD, 15+ CSS selectors, noise filtering). Reddit posts go through PullPush → Redlib mirrors → Old Reddit → AllOrigins proxy (4 fallback layers, including share link resolution)
3. **Summarize** — Each source is summarized by `llama-3.3-70b-versatile` (1024 tokens, parallel)
4. **Synthesize** — All per-source summaries combined into a final answer (4096 tokens)

## Deploy

```bash
pip install -r requirements.txt
set GROQ_API_KEY=gsk_...
uvicorn api.server:app --reload --port 8000
```

### Vercel

Push to GitHub, import in Vercel, set `GROQ_API_KEY` in environment variables. `vercel.json` routes `/api/*` to the Python serverless function (512MB, 30s timeout).

## Project structure

```
api/server.py         FastAPI app — / and /search endpoints
handlers/
  config.py           Constants, requests.Session, user-agent rotation
  search.py           Bing + Startpage search, dedup
  scraper.py          Full-article extractor (JSON-LD, CSS selectors, noise filter)
  reddit.py           Reddit post fetcher (PullPush → Redlib → Old Reddit → AllOrigins)
  utils.py            URL hashing, Reddit parsing, HTML helpers
```
