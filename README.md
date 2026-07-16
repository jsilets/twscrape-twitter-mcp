<!-- mcp-name: io.github.jsilets/twscrape-twitter-mcp -->

# twscrape-twitter-mcp

[![PyPI](https://img.shields.io/pypi/v/twscrape-twitter-mcp)](https://pypi.org/project/twscrape-twitter-mcp/)
[![CI](https://github.com/jsilets/twscrape-twitter-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/jsilets/twscrape-twitter-mcp/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/twscrape-twitter-mcp)](https://pypi.org/project/twscrape-twitter-mcp/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-server-black)](https://modelcontextprotocol.io)

An [MCP](https://modelcontextprotocol.io) server that reads X (Twitter): posts,
threads, replies, quotes, and search. It wraps [twscrape](https://github.com/vladkens/twscrape)
and uses your own logged-in session, so there's no paid X API and no developer
account. Tools return clean markdown shaped for an agent to read, including
image, video, and GIF URLs and any external links in a post.

Works with any MCP client over the two standard transports — local **stdio** and
hosted **Streamable HTTP**.

## Tools

| Tool | Returns |
|---|---|
| `read_tweet(url_or_id)` | One post as markdown. |
| `read_thread(url_or_id, max_replies=50)` | Root post + the author's self-thread + top replies. |
| `read_replies(url_or_id, limit=50)` | Replies to a post. |
| `read_quotes(url_or_id, limit=30)` | Quote-tweets (best-effort, search-based). |
| `user_timeline(username, limit=40, include_replies=False)` | A user's recent posts, newest first. Set `include_replies=True` to include replies. |
| `search(query, limit=20, product="Latest")` | Search results. Supports `from:`, `has:media`, `min_faves:`, etc. |
| `user_profile(username)` | A user's profile as markdown: bio, location, follower/following/tweet counts, join date. |

## Install

```bash
uv tool install twscrape-twitter-mcp     # or: pipx install twscrape-twitter-mcp
```

Then authenticate once (next section) and verify:

```bash
twscrape-twitter-mcp smoke               # reads one public tweet end-to-end
```

## Authenticate

Reads run against your own X session. Pick one path:

**1. Launch a dedicated browser (recommended).** Opens a separate Chrome/Brave
profile with a DevTools port, you sign in to X once, and the session is captured.
It does not touch your daily browser or automate X's login flow.

```bash
twscrape-twitter-mcp login --launch-browser chrome   # or: brave
```

**2. Attach to a dedicated browser profile.** Only use this when you already run
an isolated Chromium profile with a debug port. Browser debugging exposes browser
data, and recent Chrome versions do not enable it for the default profile.

```bash
# macOS
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222 --user-data-dir=/tmp/x-mcp-browser
# Linux:   google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/x-mcp-browser
# Windows: "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir=%TEMP%\x-mcp-browser

twscrape-twitter-mcp login --attach                  # add --cdp-url for a non-default port
```

**3. Headless / CI (raw cookies).** A server can't open your desktop browser, so
add a session from `auth_token` + `ct0` cookies. Run this without cookie flags to
enter values through hidden prompts, rather than leaving secrets in shell history:

```bash
twscrape-twitter-mcp init
```

The captured session is reused across restarts. Run `login --launch-browser chrome` again when it expires,
or to add burner sessions for rate-limit rotation. `twscrape-twitter-mcp accounts`
lists the pool.

> Use burner accounts, not your main — see [Legal](#legal).

## Connect your client

The server runs locally over stdio. Most MCP clients take a JSON block like this:

```json
{
  "mcpServers": {
    "x": {
      "command": "twscrape-twitter-mcp",
      "args": ["serve", "--transport", "stdio"]
    }
  }
}
```

Client-specific equivalents:

<details>
<summary><b>Claude Code</b></summary>

```bash
claude mcp add x --scope user -- twscrape-twitter-mcp serve --transport stdio
```
</details>

<details>
<summary><b>Claude Desktop</b></summary>

Add the JSON block above to `claude_desktop_config.json`
(Settings → Developer → Edit Config).
</details>

<details>
<summary><b>Codex</b> — <code>~/.codex/config.toml</code></summary>

```toml
[mcp_servers.x]
command = "twscrape-twitter-mcp"
args = ["serve", "--transport", "stdio"]
```
</details>

<details>
<summary><b>Cursor</b> — <code>~/.cursor/mcp.json</code></summary>

```json
{
  "mcpServers": {
    "x": {
      "command": "twscrape-twitter-mcp",
      "args": ["serve", "--transport", "stdio"]
    }
  }
}
```
</details>

<details>
<summary><b>VS Code</b> — <code>.vscode/mcp.json</code></summary>

```json
{
  "servers": {
    "x": {
      "command": "twscrape-twitter-mcp",
      "args": ["serve", "--transport", "stdio"]
    }
  }
}
```
</details>

<details>
<summary><b>Remote (Streamable HTTP)</b></summary>

For a hosted private instance (see [Deploy](#deploy)), point a preconfigured
client at the HTTP endpoint with a bearer token. This is static bearer auth, not
an OAuth sign-in flow.

```json
{
  "mcpServers": {
    "x": {
      "url": "https://YOUR-APP.example.com/mcp",
      "headers": { "Authorization": "Bearer YOUR_TOKEN" }
    }
  }
}
```
</details>

Then ask, e.g. *"read this thread: &lt;url&gt;"*.

## Deploy

Run the server always-on and reachable over HTTP (`POST /mcp`). It ships as a
container; Cloudflare Workers won't work because twscrape is Python with native
deps.

A headless container can't open your desktop browser, so authenticate **locally**
first (`login --attach` writes `storage_state.json` under
`TWSCRAPE_TWITTER_MCP_HOME`), then ship that session to the host — copy the file to
the mounted volume, or run the cookie-based `init` over SSH. The server reloads a
persisted session on boot.

**Always set a token when exposing HTTP** — anyone who can reach the endpoint can
use your X session:

```bash
export TWSCRAPE_TWITTER_MCP_AUTH_TOKEN=$(openssl rand -hex 32)
```

<details>
<summary><b>Fly.io</b></summary>

```bash
fly launch --no-deploy
fly volumes create twscrape_twitter_mcp_data --size 1
fly secrets set TWSCRAPE_TWITTER_MCP_AUTH_TOKEN=$(openssl rand -hex 32)
fly deploy
# seed a session onto the volume through hidden prompts:
fly ssh console -C "twscrape-twitter-mcp init"
```
</details>

<details>
<summary><b>Railway</b></summary>

Point Railway at this repo (it reads `railway.json` + `Dockerfile`), add a volume
mounted at `/data`, set `TWSCRAPE_TWITTER_MCP_AUTH_TOKEN`, and seed a session via
the Railway shell with `twscrape-twitter-mcp init`.
</details>

Clients send `Authorization: Bearer <token>`.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `TWSCRAPE_TWITTER_MCP_HOME` | `~/.config/twscrape-twitter-mcp` | Where the sqlite account pool lives. Point at a volume in prod. |
| `TWSCRAPE_TWITTER_MCP_DB` | `$TWSCRAPE_TWITTER_MCP_HOME/accounts.db` | Override the pool path directly. |
| `TWSCRAPE_TWITTER_MCP_AUTH_TOKEN` | _(unset)_ | Required bearer token for HTTP transport. |
| `TWSCRAPE_TWITTER_MCP_PROXY` | _(unset)_ | Global proxy for every account. |
| `TWSCRAPE_TWITTER_MCP_CDP_URL` | `http://127.0.0.1:9222` | Browser DevTools endpoint for `login --attach`. |
| `TWSCRAPE_TWITTER_MCP_DEFAULT_LIMIT` | `40` | Default timeline and search result count (1–100). |
| `PORT` | `8080` | HTTP port (Railway injects this). |

## How it works

The hard part of reading X — GraphQL signing, the `x-client-transaction-id`
header, TLS fingerprinting — lives entirely in `twscrape`, which is pinned.
This package is a read-only MCP layer on top and never
touches that machinery. When X changes something and reads break, the fix is a
version bump, not reverse-engineering.

## Limits

- X can expire, rate-limit, or suspend the account behind your session.
- Protected, deleted, geo-blocked, or otherwise restricted posts may not be readable.
- Quote-tweet coverage is search-based and incomplete.
- Search results depend on X's current search behavior and can vary by session.
- It does not decrypt browser cookie stores — use browser attach or cookie `init`.

## Legal

Reading X with your own logged-in session may violate X's Terms of Service, and
accounts used for scraping can be rate-limited or suspended. Use burner accounts,
not your main. Provided as-is for research and personal use; you are responsible
for how you use it.

## License

MIT.

## Credits

The hard scraping work is [`twscrape`](https://github.com/vladkens/twscrape) by
vladkens. This is a read-only MCP layer on top — go star it.
</content>
