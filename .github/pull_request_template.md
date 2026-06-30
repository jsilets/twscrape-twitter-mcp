## What this changes

<!-- One or two sentences. Link any related issue. -->

## Scope checklist

Please confirm (see CONTRIBUTING.md → "Scope and non-goals"):

- [ ] Read-only — does not post, reply, like, follow, DM, or otherwise write to X.
- [ ] No third-party / paid backend added to core (route reads only through twscrape + the user's own session).
- [ ] New/changed tools return markdown and degrade to a plain string on miss/rate-limit (no raised stack traces to the agent).

## Verification

- [ ] `ruff check .` passes
- [ ] `pytest -q` passes
- [ ] If this bumps twscrape: ran `twscrape-twitter-mcp smoke` against a live session and it returned `SMOKE OK`
