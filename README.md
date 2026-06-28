# twscrape-twitter-mcp

A read-optimized [MCP](https://modelcontextprotocol.io) server for X (Twitter), built as a thin layer over [twscrape](https://github.com/vladkens/twscrape).

You bring your own authenticated browser session or cookies. Your agent gets clean, markdown-shaped tools for reading posts, threads, replies, quotes, and search. No paid X API, no developer account.

## Why this exists

There are plenty of Twitter MCP servers. They fall into three buckets, and each has a gap:

- **Official-API ones** need a paid developer key and can get expensive for agent loops.
- **Free cookie-scraper ones** are single-account and mostly wrap `twikit`, which has been intermittently broken on X's `x-client-transaction-id` changes.
- **Browser-driving ones** are heavy and need constant selector maintenance.

`twscrape-twitter-mcp` does the boring-but-missing thing: wrap the **healthier, actively-maintained** scraper (`twscrape`, which has account pooling + browser-TLS impersonation + fast fixes), pin it, and expose **read-first tools an agent actually wants** plus practical session bootstrap.

### The maintenance bargain

The hard part of X scraping (GraphQL signing, the `x-client-transaction-id` header, TLS fingerprinting) lives entirely in `twscrape`. This repo never touches it. When X breaks `twscrape`, you:

1. bump the pin in `pyproject.toml`,
2. let CI's weekly **live smoke test** confirm it reads again,
3. tag a release.

That's the whole treadmill. A dependency bump, not reverse-engineering.

## Tools

| Tool | What it returns |
|---|---|
| `read_tweet(url_or_id)` | One post as markdown. |
| `read_thread(url_or_id, max_replies=50)` | Root post + the author's self-thread + top replies. |
| `read_replies(url_or_id, limit=50)` | Replies to a post. |
| `read_quotes(url_or_id, limit=30)` | Quote-tweets (best-effort, search-based). |
| `search(query, limit=20, product="Latest")` | Search results. Supports `from:`, `has:media`, `min_faves:`, etc. |

## Auth: attach to your signed-in browser

The preferred no-paste path is a dedicated browser profile managed by `twscrape-twitter-mcp`.
It launches a normal Chrome or Brave window with a DevTools port, you sign into
X there once, and `twscrape-twitter-mcp` reads that live session through the browser API. It
does not decrypt browser cookie stores and it does not automate X's login flow.

```bash
pipx install twscrape-twitter-mcp          # or: uv tool install twscrape-twitter-mcp
twscrape-twitter-mcp login --launch-browser chrome
twscrape-twitter-mcp smoke                 # live check: reads one public tweet
```

Use `--launch-browser brave` if you prefer Brave. The profile is stored under
`TWSCRAPE_TWITTER_MCP_HOME`, so it survives restarts without touching your daily browser.

If you want to reuse an already signed-in browser profile instead, launch that
browser yourself with a debug port, then attach:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222
# or
"/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" --remote-debugging-port=9222
# or
"/Applications/Arc.app/Contents/MacOS/Arc" --remote-debugging-port=9222
```

If you use another port or host:

```bash
twscrape-twitter-mcp login --attach --cdp-url http://127.0.0.1:9333
```

After the first successful capture, the session is reused silently across
restarts. Run `login --launch-browser chrome` or `login --attach` again when the
session expires or to add extra burner sessions for rate-limit rotation.
`twscrape-twitter-mcp accounts` lists the pool.

There is also an explicit fallback:

```bash
twscrape-twitter-mcp login --fresh-browser
```

That opens an automated browser at X's login page. It is not recommended as the
default because X can detect and block automated fresh login attempts.

> Install `twscrape-twitter-mcp[stealth]` to use an undetected Chromium (patchright) for the
> fresh-browser fallback. Used automatically if present.

### Wire it into Claude Code

```bash
claude mcp add x --scope user -- twscrape-twitter-mcp serve --transport stdio
```

Or edit your MCP config directly, see [`examples/claude_mcp_config.json`](examples/claude_mcp_config.json). Then in a session: *"read this thread: <url>"*.

### Manual / CI fallback

Headless environments (CI) cannot attach to your desktop browser, so `init` adds
a session from raw cookies instead:

```bash
twscrape-twitter-mcp init --username YOU --auth-token AUTH --ct0 CT0
```

## Deploy (remote, HTTP)

Use this when you want the server always-on / reachable from a hosted client. It runs as a container; **Cloudflare Workers won't work** (twscrape is Python with native deps).

**Auth on a server:** a headless container cannot attach to your desktop browser,
so you authenticate **locally** with `twscrape-twitter-mcp login --attach` (which writes `storage_state.json`
under `TWSCRAPE_TWITTER_MCP_HOME`), then ship that session to the host, either copy the file to
the mounted volume, or run the cookie-based `init` over SSH. The server reloads a
persisted session silently on boot.

**Always set a token** when exposing HTTP, anyone who can reach the endpoint can use your X session:

```bash
export TWSCRAPE_TWITTER_MCP_AUTH_TOKEN=$(openssl rand -hex 32)
```

### Fly.io

```bash
fly launch --no-deploy
fly volumes create twscrape_twitter_mcp_data --size 1
fly secrets set TWSCRAPE_TWITTER_MCP_AUTH_TOKEN=$(openssl rand -hex 32)
fly deploy
# seed a session onto the volume:
fly ssh console -C "twscrape-twitter-mcp init --username YOU --auth-token AUTH --ct0 CT0"
```

### Railway

Point Railway at this repo (it reads `railway.json` + `Dockerfile`), add a volume mounted at `/data`, set `TWSCRAPE_TWITTER_MCP_AUTH_TOKEN`, and seed a session via the Railway shell with `twscrape-twitter-mcp init`.

The HTTP endpoint is `POST /mcp`; clients send `Authorization: Bearer <token>`.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `TWSCRAPE_TWITTER_MCP_HOME` | `~/.config/twscrape-twitter-mcp` | Where the sqlite account pool lives. Point at a volume in prod. |
| `TWSCRAPE_TWITTER_MCP_DB` | `$TWSCRAPE_TWITTER_MCP_HOME/accounts.db` | Override the pool path directly. |
| `TWSCRAPE_TWITTER_MCP_AUTH_TOKEN` | _(unset)_ | Required bearer token for HTTP transport. |
| `TWSCRAPE_TWITTER_MCP_PROXY` | _(unset)_ | Global proxy for every account. |
| `TWSCRAPE_TWITTER_MCP_CDP_URL` | `http://127.0.0.1:9222` | Browser DevTools endpoint for `login --attach`. |
| `TWSCRAPE_TWITTER_MCP_DEFAULT_LIMIT` | `40` | Default result count. |
| `PORT` | `8080` | HTTP port (Railway injects this). |

## Maintenance

- Pinned dependency: `twscrape==0.19.0`.
- Weekly GitHub Action runs unit tests always and a **live** read (using `X_USERNAME` / `X_AUTH_TOKEN` / `X_CT0` repo secrets) on a schedule. A red run means X moved and the pin needs a bump.

## Known Limits

- X can expire, rate-limit, or suspend the account behind your session.
- Protected, deleted, geo-blocked, or otherwise restricted posts may not be readable.
- Quote-tweet coverage is search-based and incomplete.
- Search results depend on X's current search behavior and can vary by account/session.
- This package intentionally does not decrypt browser cookie stores. Use browser attach or manual cookie init.
- When X changes internals, `twscrape` may need a version bump before reads work again.

## Legal / ToS

This reads X using your own logged-in session, which may violate X's Terms of Service. Accounts used for scraping can be rate-limited or suspended, use burner accounts, not your main. Provided as-is for research and personal use. You are responsible for how you use it.

## Credits

All the genuinely hard work is [`twscrape`](https://github.com/vladkens/twscrape) by vladkens. This is a thin MCP shell on top. Go star it.
