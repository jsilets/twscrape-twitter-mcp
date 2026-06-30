# Security Policy

## Reporting a vulnerability

Please report security issues privately via GitHub's
[private vulnerability reporting](https://github.com/jsilets/twscrape-twitter-mcp/security/advisories/new)
rather than opening a public issue. Expect an initial response within a few days.

## What this tool handles

This server reads X/Twitter using **your own logged-in session** — it stores and
uses session cookies (`auth_token` / `ct0`) to authenticate reads. Treat those
with the same care as a password:

- The session pool (`accounts.db`, `storage_state.json`) lives under
  `TWSCRAPE_TWITTER_MCP_HOME`. Anyone with read access to that path can act as
  your X session.
- **When serving over HTTP, always set `TWSCRAPE_TWITTER_MCP_AUTH_TOKEN`.** An
  unauthenticated HTTP endpoint lets anyone who can reach it use your session.
- Use burner accounts, not your main — X can rate-limit or suspend accounts used
  for scraping.

## Supported versions

This is an actively maintained project; fixes land on the latest release. There
is no long-term support branch for older versions.
