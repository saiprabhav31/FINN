# FINN — investment intelligence prototype

A responsive, mobile-first local full-stack app for the ENAM Founding AI Engineer build challenge. It demonstrates a daily Push brief, on-demand Pull research, and a private Network layer woven into both.

## Run it

Run `python server.py` (Python 3.9+) and open `http://127.0.0.1:8765`. The server creates `finn.db` on first run and seeds the demo portfolio. No package installation or API key is required. Ctrl+C stops the server. If you open `index.html` directly, the frontend falls back to in-memory demo data and database actions are unavailable.

On Windows, double-click `run-finn.bat`. For a containerized read-only demo, run `docker compose up --build -d`; this maps port 8765 and persists the seeded DB in a named volume. Stop it with `docker compose down`.

## Product tour

- **Daily brief:** switch the 24-hour / 3-day / 7-day window, filter by priority or filing category, add a filing, and open alert preferences. Seeded feed examples intentionally say “simulated.”
- **Research:** use a seeded ticker chip or type a company name/NSE symbol (with optional `.NS`/`.BO`). Switch overview, trajectory, balance and cash, and narrative views. The five seeded examples contain illustrative figures; other tickers show a source-needed state instead of made-up financials.
- **Network:** search synthetic people by company, sector, role, or topic; add a local profile. Results show why a person may help. Network links appear in Push and Pull.
- **Market data:** NSE is tried first for an on-demand quote, with a labelled Yahoo Finance fallback. Yahoo Finance daily bars are stored in SQLite for the portfolio; the latest close is compared with the prior close and 20-session average volume. Configurable price-move and volume-spike rules create deduplicated Push alerts. The app refreshes EOD data at startup when the last sync is over 12 hours old and has a manual **Sync prices** action. Provider access can be blocked or rate-limited; the UI then keeps previously stored data and reports the sync result.
- **Official filings:** the first local-app launch triggers an NSE equity-announcements sync; the daily brief also has a manual **Sync NSE** action. It filters to portfolio symbols, classifies announcements heuristically, saves filing IDs/links, and deduplicates repeats. NSE may deny or throttle automated requests; the UI reports sync failures and keeps the official portal link available.
- **Company documents:** **Find company reports** discovers annual-report and earnings-call/transcript links from a company's Screener page and stores their source URLs. It does not download or summarize the PDFs; open a document link to inspect the original issuer/exchange file.
- **Alert preferences:** toggle material announcement categories and set price-move / volume-spike thresholds. Thresholds persist in SQLite when the backend is running.
- **API:** `/api/health`, `/api/bootstrap`, `/api/companies`, `/api/events`, `/api/network?q=...`, `/api/quote/{ticker}`, `/api/sync/status`, `/api/sources/{ticker}`, `/api/research/{ticker}`. POST `/api/sync/prices` refreshes and evaluates portfolio EOD bars; POST `/api/sync/nse` refreshes official announcements; POST `/api/sync/company/{ticker}` discovers annual-report/transcript links. Other POST endpoints create filings, network profiles, source references, research notes, and preferences; DELETE endpoints remove records by ID.

## Data, privacy, and prototype boundaries

All seeded network names are synthetic. Seeded filing descriptions and financial snapshots are illustrative until replaced by a successful NSE sync; they are not current market information. Live quotes prefer NSE and use Yahoo Finance only as a labelled fallback. Official NSE announcements can be synced; company report links are discovered through Screener, but documents are not downloaded or analyzed automatically. No LinkedIn or LLM service is connected. User-entered profiles and preferences stay in the local SQLite database. The server binds only to `127.0.0.1` by default and has no authentication, so do not expose a writable instance or store sensitive real contact data in this demo.

The research screen withholds company-specific numbers for unseeded symbols. It can discover links to annual reports and transcripts but does not extract their figures or claims. A real implementation should retrieve primary-source documents, preserve document and period metadata, then extract and reconcile claims with citations before showing financial analysis.

### Production architecture direction

1. **Ingestion:** refresh stale EOD bars when the app starts; ingest NSE/BSE announcements and issuer annual-report, quarterly-results and transcript sources. Persist immutable source documents and normalized entities with timestamps and source URLs.
2. **Extraction:** classify announcement type and materiality; parse financial tables deterministically where possible; use a constrained model for summaries and transcript claims. Store each claim with source document, page/section, period, units, extraction version, and confidence. Reconcile figures before computing QoQ/YoY.
3. **Network:** tenant-isolated people, affiliations and relationship edges; explicit provenance, consent, retention and deletion controls. Match filing names against known people with reviewable confidence, never silently assert a match.
4. **Serving:** API for portfolio, digest, alerts, research and graph search. Cache source-derived analyses. Use a small model for bulk classification and a stronger model only for multi-document reasoning. Ask before outreach; the prototype never contacts anyone.
5. **Security:** encrypt data in transit and at rest, isolate tenant keys/records, apply role-based access, minimize profile retention, audit accesses, and make source and consent state visible. Network data must never be used across investors.

## Suggested next implementation steps

1. Add document extraction with citation spans for annual reports, quarterly results and earnings calls.
2. Replace local sample profiles with consented/imported contacts and a tenant-scoped graph store.
3. Add authentication, deployment configuration, observability, and a real mobile installable shell.

## Files

- `index.html` — responsive app and frontend interactions.
- `server.py` — local REST API, SQLite persistence, and quote provider adapter.
- `finn.db` — created locally at first startup; not checked into source control.
- `README.md` — setup, data caveats and architecture direction.
- `SUBMISSION.md` — covering-email draft and release checklist.
- `AI_BUILD_HISTORY.md` — honest summary of the AI-assisted work; add a session export/share link if one is made available.
- `Dockerfile` / `compose.yaml` — read-only demo container setup.
- Challenge PDFs are supplied separately and are not required to run the app.
