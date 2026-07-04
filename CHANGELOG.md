# Changelog

All notable changes to this project are documented here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/), and the project follows
semantic-ish versioning while in `0.x`.

## [Unreleased]

### Added
- Tweet output now renders attached media (image, video, and GIF URLs, with the
  highest-quality video variant and humanized duration) and external links.
  Agents previously lost these entirely.
- `user_profile(username)` tool: reads a user's profile by handle and returns it
  as markdown (bio, location, follower/following/tweet counts, join date, url).
- `user_timeline(username, limit=40, include_replies=False)` tool: a user's
  recent posts as markdown, newest first, with an option to include replies.

### Changed
- Every tool now returns a plain explanatory string on any failure (bad input,
  rate-limit, expired session, no account available, network) instead of raising.
  Previously only the "not found" case was handled; a raised twscrape error would
  surface to the agent as an opaque protocol error.

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
