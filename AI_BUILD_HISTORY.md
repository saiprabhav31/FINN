# AI build history — FINN

This note records the AI-assisted work completed in this Codex task. It is a concise summary, not a raw transcript export or a public session link.

## Work sequence

1. **Read the challenge brief and glossary.** Extracted the three product layers (Push, Pull, Network), mobile-first requirement, primary-source research constraint, synthetic network option, and submission requirements.
2. **Built the interface.** Created a responsive single-page app with daily digest filters, research views, network matching, and alert preferences. Explicitly labelled seeded financial figures, filings, and people as synthetic.
3. **Added a local API and persistence.** Implemented a Python standard-library HTTP server and SQLite store for portfolio companies, events, profiles, source references, notes, and alert preferences. Added create/read/delete routes and a health endpoint.
4. **Connected public market and exchange sources.** Added an NSE-first quote adapter with a labelled Yahoo fallback, plus an on-demand NSE equity-announcements sync that stores portfolio matches with official attachment/filing links and deduplication keys. Added Yahoo Finance daily-bar ingestion, SQLite history, configurable price-move and 20-session volume-spike checks, and deduplicated Push alerts. Added Screener-page discovery of annual-report and transcript links.
5. **Connected the UI to the API.** Added bootstrap loading, first-run/manual NSE and EOD price sync, local record creation for filings and network profiles, persisted alert preferences, report-link discovery, data-backed portfolio moves and date-window filtering, and an explicit offline-demo fallback.
6. **Prepared handoff materials.** Added local and container launch instructions, a read-only Compose configuration, a covering-note draft, and this build-history summary.

## Decisions and course corrections

- Used a dependency-free Python server and SQLite to keep the demo easy to run and inspect.
- Avoided inventing data for unseeded tickers; the app indicates when source-backed analysis is unavailable.
- Kept demo profiles synthetic and documented privacy limits. The public container configuration disables API writes.
- A JavaScript syntax check found a malformed object key in the research-tab renderer; it was corrected, and the JavaScript/Python syntax checks then passed.
- Browser-based preview was unavailable because this environment's browser policy blocked access to the local `file://` page. Visual QA on the deployed URL is still needed.

## Current implementation limits

NSE announcement, Yahoo Finance and Screener endpoints may rate-limit or block requests. Annual-report/transcript links are discovered but not parsed, and seeded financial snapshots and filing examples remain illustrative. No LLM analysis pipeline, authentication, or investor tenant isolation is implemented. Do not deploy it as a writable service for real personal data.

## Session provenance

The code was created and iterated in the Codex task associated with this workspace. Add the actual Codex share link or export here if one is created for submission; this document does not fabricate a share URL.
