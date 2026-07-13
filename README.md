# yt-pipeline

Watches a private YouTube playlist, summarizes new videos with Gemini (free tier),
and files organized entries into a Notion database. Runs as a two-container stack
(n8n + yt-helper) deployed via Portainer on mbDocker.

Full build guide, task list, and operational reference live in Notion:
Greg's Homelab > YouTube Playlist AI Pipeline.

## Layout

```
docker-compose.yml    # n8n + yt-helper stack
yt-helper/            # FastAPI sidecar: yt-dlp metadata + transcripts
n8n/workflow.json     # Importable n8n workflow (16 nodes)
```

## Deploy

Deployed as a git-backed Portainer stack. Stack env var required:

| Variable | Value |
|---|---|
| N8N_ENCRYPTION_KEY | Any long random string. SAVE IT. Losing it orphans all stored n8n credentials. |

Generate one with: `openssl rand -hex 32`

## Post-deploy configuration (one time)

1. Browse to https://n8n.skynet51.com, create the n8n owner account.
2. Create credentials: YouTube OAuth2 API, Header Auth "Gemini API"
   (header `x-goog-api-key`), Notion API, optional Header Auth "GitHub Search".
3. Import `n8n/workflow.json` (Workflows > Import from file).
4. Assign credentials on: Get Playlist Items (YouTube), Notion Dedupe Query /
   Create Notion Entry / Update Properties / Append Page Blocks (Notion),
   Gemini Summarize (Gemini API header auth).
5. In "Get Playlist Items", replace PASTE_PLAYLIST_ID_HERE with your playlist ID
   (everything after `list=` in the playlist URL).
6. Share the "YouTube Video Library" Notion database with the yt-pipeline
   integration (database ... menu > Connections).
7. Execute once manually to test, then activate.

## Notes and maintenance

- The Notion database ID is baked into the workflow (Dedupe Query URL and
  Prepare Requests code). If the database is ever recreated, update both spots.
- Gemini model is set in the "Gemini Summarize" node URL (`gemini-flash-latest`, an alias that tracks the current Flash model).
  Swap the model name there if Google retires it or you want to upgrade.
- yt-dlp breaks occasionally when YouTube changes things. Fix: bump the pin in
  `yt-helper/requirements.txt`, commit, and re-pull the stack in Portainer
  (Recreate + re-pull/build).
- First activation processes EVERY video already in the playlist. Use an empty
  test playlist first, or accept the backfill (Gemini free tier: 10 req/min,
  1,500/day).
- Repos without description links are resolved via unauthenticated GitHub
  search (10 req/min, plenty at this volume). All model-guessed URLs are
  HEAD-verified; failures are written to Notion flagged "unverified" with a
  Google search fallback link.
