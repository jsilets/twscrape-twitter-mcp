# Changelog

All notable changes to this project are documented here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/), and the project follows
semantic-ish versioning while in `0.x`.

## [0.1.3]

### Security
- CDP session capture now persists only X/Twitter cookies and restricts local
  session-file permissions where supported.
- HTTP refuses non-localhost binding without `TWSCRAPE_TWITTER_MCP_AUTH_TOKEN`.
- Bearer-token comparison is timing-safe, and 401 responses include
  `WWW-Authenticate: Bearer`.

### Changed
- The package now starts the stdio MCP server when invoked without a subcommand,
  so MCP registry launches (`uvx twscrape-twitter-mcp`) work.
- Tool failures never raise: they return readable markdown with the MCP
  `isError` flag set. Tools publish read-only annotations, and tool inputs have
  bounded schemas.
- `auth_status` replaces the stateful MCP `login` tool. Browser login remains a
  local CLI command.
- Server metadata reports the package version instead of FastMCP's version.

### Added
- Tweet output now renders attached media (image, video, and GIF URLs, with the
  highest-quality video variant and humanized duration) and external links.
  Agents previously lost these entirely.
- `user_profile(username)` tool: reads a user's profile by handle and returns it
  as markdown (bio, location, follower/following/tweet counts, join date, url).
- `user_timeline(username, limit=40, include_replies=False)` tool: a user's
  recent posts as markdown, newest first, with an option to include replies.

### Dependencies
- Bumped `twscrape` 0.19.1 to 0.19.2. X now serves anonymous web clients a build
  that omits the client-transaction-id signing assets, so 0.19.1 could no longer
  generate transaction ids and every read failed. 0.19.2 fetches those assets
  with account cookies, which still return the assets the parser needs.

## [0.1.2]

### Changed
- Bumped pinned `twscrape` to `0.19.1` (updated GraphQL operation IDs for current
  X API compatibility). Verified with unit tests + a live `smoke` read.

### Added
- `CONTRIBUTING.md` with scope/non-goals and the twscrape bump ritual.
- Dependabot config to auto-open `twscrape` and GitHub Actions bump PRs.
- `SECURITY.md`, pull-request template, and this changelog.

## [0.1.1]
- Release via PyPI Trusted Publishing (OIDC).

## [0.1.0]
- Initial public release: read-only MCP server over twscrape (read_tweet,
  read_thread, read_replies, read_quotes, search) with stdio + Streamable HTTP
  transports.
