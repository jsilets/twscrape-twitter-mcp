# Changelog

All notable changes to this project are documented here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/), and the project follows
semantic-ish versioning while in `0.x`.

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
