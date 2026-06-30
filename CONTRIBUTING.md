# Contributing

## Scope

Read-only by design. PRs are judged against this:

- No tools that write to X (post, reply, like, follow, DM).
- No paid or third-party backends in core. Reads go through twscrape and your own session. Open an issue first if you think a case is exceptional.
- twscrape stays the engine. No alternative scraping backends.
- Tools return markdown, and return a plain string on miss/rate-limit instead of raising.

## Setup

```bash
uv pip install -e ".[dev]"
```

## Checks

CI runs these two (Python 3.12). Run them before pushing:

```bash
ruff check .
pytest -q
```

Tests are network-free. `twscrape-twitter-mcp smoke` does a live read (needs auth, see README) and is the manual gate when bumping twscrape.

## Bumping twscrape

A stale pin is how scrapers rot, so this is the main maintenance job. Dependabot opens the PRs. For each one:

1. Read the [release notes](https://github.com/vladkens/twscrape/releases). A patch is low risk. A minor can change twscrape's Python API, so skim its "Breaking Changes" for anything `server.py` calls.
2. Run `ruff check . && pytest -q && twscrape-twitter-mcp smoke`.
3. If green, update the pin and `version` in `pyproject.toml`, add a `CHANGELOG.md` entry, merge.

## PRs and releases

Branch, then PR; no direct pushes to `master`. To release, tag `vX.Y.Z` and push the tag (triggers the release workflow).
