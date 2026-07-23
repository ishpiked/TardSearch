<!-- ANCHORED_SUMMARY
# Objective
Deep research API: search web from multiple angles, scrape full content (articles + Reddit), summarize every source individually via Groq/LLaMA, then synthesize a final answer. Deployed as a Vercel Python serverless function.

# Important Details
- Project path: `C:\Users\unkno\Downloads\Codes\Projects\Stack Dev\Tard`
- GitHub: `https://github.com/ishpiked/TardSearch.git`
- Reddit fetch chain: PullPush → Redlib mirrors → Old Reddit scrape → AllOrigins proxy (4 fallback layers)
- Share links (`/s/` tokens) are resolved via HEAD/GET redirect + og:url meta tag
- Old Reddit fallback bypasses Cloudflare — detects block pages, retries with fresh user-agent, extracts post body via `thing_id`-targeted `usertext-body` regex
- Search pipeline: per-source LLM summarization (parallel) → final synthesis
- Search sources: Bing (primary) + Startpage (fallback) — DuckDuckGo blocks datacenter IPs
- LLM: `llama-3.3-70b-versatile` via Groq, temperature 0.1, max_tokens 4096
- Vercel: Python serverless, 512MB memory, 30s timeout
- Router prefix auto-detects Vercel: `/api` on Vercel, empty locally

# Work State
## Completed
- Stripped frontend entirely — backend-only FastAPI service
- Replaced `duckduckgo_search` lib with direct Bing + Startpage HTTP scraping (DDG blocks datacenter IPs)
- Fixed all early-return paths to return consistent response shape
- Added auto-detect for Vercel API prefix
- Various bug fixes and code cleanup

## Active
- (none)

## Blocked
- (none)

# Relevant Files
- `api/server.py`: FastAPI app — `/` health, `/search` endpoint, `fetch_content()` orchestrator
- `handlers/config.py`: constants, requests.Session, USER_AGENTS, rotate_agent(), REDLIB_INSTANCES
- `handlers/utils.py`: extract_post_id, extract_share_link, url_hash, text_key, HTML helpers
- `handlers/reddit.py`: PullPush API, Redlib mirror parser, Old Reddit scrape, AllOrigins proxy, share link resolution
- `handlers/scraper.py`: deep article scrape (JSON‑LD, 15+ selectors, meta extraction, noise filtering)
- `handlers/search.py`: Bing + Startpage search, multi-query expansion, dedup by domain
- `vercel.json`: routes `/api/*` → Python backend
--> 