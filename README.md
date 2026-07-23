# Tard

Deep research API. Searches the web, scrapes full article and Reddit content, then synthesises everything into one concise answer via an LLM fallback chain (Groq -> Cerebras -> OpenRouter). Deployed as a Vercel Python serverless function.

## API

### `GET /search?q=<query>`

```
curl "http://localhost:8000/search?q=what+is+the+current+state+of+fusion+energy"
```

```json
{
  "query": "what is the current state of fusion energy",
  "sources_discovered": 3,
  "sources_scraped": 3,
  "sources_summarized": 3,
  "per_source_summaries": [
    {
      "title": "Fusion Energy Report 2025",
      "url": "https://example.com/fusion",
      "summary": "TITLE: Fusion Energy Report 2025\nSOURCE: example.com\n\nThe ITER project..."
    }
  ],
  "answer": "Fusion energy research is progressing on multiple fronts..."
}
```

### `GET /` (health)

```json
{ "status": "online" }
```

## Pipeline

```
Search (DDGS -> HTML scrape fallback) -> Scrape 3 sources in parallel -> One-shot LLM synthesis
```

1. **Search** -- Single-query DuckDuckGo via TLS fingerprinting (`ddgs` library). Falls back to HTML scrape if DDGS fails. 3 results max, one per domain. YouTube results filtered out.
2. **Scrape** -- Fetches every result in parallel. Articles use a deep HTML scraper (JSON-LD, 15+ CSS selectors, meta extraction, noise filtering). Reddit posts go through PullPush -> Redlib mirrors -> Old Reddit -> AllOrigins proxy (4 fallback layers, including share link resolution).
3. **Synthesize** -- All scraped content is packed into a single LLM call. No per-source summarisation step -- the model sees raw text and produces the final answer directly.

## LLM Fallback Chain

Each provider is tried in order. If all models in a provider fail, the next provider is used.

| Provider | Models |
|---|---|
| **Groq** (primary) | `llama-3.3-70b-versatile`, `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `llama-3.1-8b-instant`, `qwen/qwen3.6-27b` |
| **Cerebras** (fallback 1) | `gemma-4-31b`, `gpt-oss-120b`, `zai-glm-4.7` |
| **OpenRouter** (fallback 2) | `poolside/laguna-xs-2.1:free`, `poolside/laguna-s-2.1:free` |

## Quick Start

```bash
git clone https://github.com/ishpiked/TardSearch.git
cd TardSearch
pip install -r requirements.txt
# Set at least one API key
set GROQ_API_KEY=gsk_...
uvicorn api.server:app --reload --port 8000
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | No (recommended) | Groq API key (primary LLM provider) |
| `CEREBRAS_API_KEY` | No | Cerebras API key (fallback 1) |
| `OPENROUTER_API_KEY` | No | OpenRouter API key (fallback 2) |
| `REDLIB_INSTANCES` | No | Space-separated Redlib mirror URLs (built-in defaults) |

At least one API key must be set.

## Vercel Deployment

Push to GitHub, import in Vercel, set at least one API key in environment variables.

Configuration (in `vercel.json`):
- 512 MB memory
- 30s timeout
- All routes rewritten to `api/server.py`

## Project Structure

```
api/server.py          FastAPI app (health, search endpoint, LLM orchestration)
handlers/
  config.py            Constants, requests.Session, user-agent rotation, Redlib instances
  search.py            DuckDuckGo search (ddgs library + HTML scrape fallback)
  scraper.py           Article content extraction (JSON-LD, CSS selectors, meta, noise filter)
  reddit.py            Reddit post fetching (PullPush -> Redlib -> Old Reddit -> AllOrigins)
  utils.py             URL hashing, Reddit ID/subreddit extraction, HTML helpers
vercel.json            Vercel rewrite rules and function config
requirements.txt       Python dependencies
```

## Tuning

All knobs are at the top of `handlers/config.py`:

| Constant | Default | Description |
|---|---|---|
| `MAX_RESULTS` | 3 | Max search results to scrape |
| `MAX_WORKERS` | 5 | Parallel scrape workers |
| `TIMEOUT` | 3 | HTTP request timeout (seconds) |
| `ARTICLE_TEXT_LIMIT` | 3000 | Max characters stored per article |
