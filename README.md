# FINN — investment intelligence prototype

A responsive, mobile-first local full-stack app for the ENAM Founding AI Engineer build challenge. It demonstrates a daily Push brief, on-demand Pull research, and a private Network layer woven into both.

## Phone demo

Try the [public mobile demo](https://saiprabhav31.github.io/FINN/). GitHub Pages serves the responsive frontend in offline-demo mode with clearly labelled synthetic examples. The public page does not run the Python API; live quote, filing-sync, and document-index actions require the local server described below. Every push to `main` deploys the site through `.github/workflows/deploy-pages.yml`.

## Run it

Install the one document-extraction dependency with `python -m pip install -r requirements.txt`, then run `python server.py` (Python 3.9+) and open `http://127.0.0.1:8765`. The server creates `finn.db` on first run and seeds the demo portfolio. No API key is required. Ctrl+C stops the server. If you open `index.html` directly, the frontend falls back to in-memory demo data and database actions are unavailable.

On Windows, double-click `run-finn.bat`. For a containerized read-only demo, run `docker compose up --build -d`; this maps port 8765 and persists the seeded DB in a named volume. Stop it with `docker compose down`.

## Product tour

- **Daily brief:** switch the 24-hour / 3-day / 7-day window, filter by priority or filing category, add a filing, and open alert preferences. Seeded feed examples intentionally say “simulated.”
- **Research:** type a company name/NSE symbol (with optional `.NS`/`.BO`), find annual-report and earnings-call links, index up to four PDF/HTML sources, then ask a question. FINN returns matching source passages linked to the source URL and PDF page number. This is deterministic keyword retrieval; it does not invent a summary, financial values, period comparisons, or management guidance. The former financial snapshots have been removed, and unsupported values remain withheld.
- **Network:** search synthetic people by company, sector, role, or topic; add a local profile. Results show why a person may help. Network links appear in Push and Pull.
- **Market data:** NSE is tried first for an NSE on-demand quote, with a labelled Yahoo Finance fallback; `.BO` research symbols use Yahoo Finance's BSE quote. Yahoo Finance daily bars are stored in SQLite for the NSE portfolio; the latest close is compared with the prior close and 20-session average volume. Configurable price-move and volume-spike rules create deduplicated Push alerts. The app refreshes EOD data at startup when the last sync is over 12 hours old and has a manual **Sync prices** action. Provider access can be blocked or rate-limited; the UI then keeps previously stored data and reports the sync result.
- **Official filings:** the first local-app launch triggers an NSE equity-announcements sync; the daily brief also has a manual **Sync NSE** action. It filters to portfolio symbols, classifies announcements heuristically, saves filing IDs/links, and deduplicates repeats. NSE may deny or throttle automated requests; the UI reports sync failures and keeps the official portal link available.
- **Company documents:** **Find source docs** discovers annual-report and earnings-call/transcript links from a company's Screener page. **Index source text** reads up to four discovered documents (PDFs up to 15 MB/500 pages or text/HTML pages) into SQLite. Search results are exact source passages with document links and page numbers for PDFs; HTML sources use section numbers. Scanned PDFs without a text layer are reported and skipped. Verify the linked issuer or exchange source before relying on a claim.
- **Alert preferences:** toggle material announcement categories and set price-move / volume-spike thresholds. Thresholds persist in SQLite when the backend is running.
- **API:** `/api/health`, `/api/bootstrap`, `/api/companies`, `/api/events`, `/api/network?q=...`, `/api/quote/{ticker}`, `/api/sync/status`, `/api/sources/{ticker}`, `/api/research/{ticker}`. POST `/api/sync/prices` refreshes and evaluates portfolio EOD bars; POST `/api/sync/nse` refreshes official announcements; POST `/api/sync/company/{ticker}` discovers annual-report/transcript links; POST `/api/research/index/{ticker}` indexes discovered documents; POST `/api/research/ask` searches indexed primary-source text. Other POST endpoints create filings, network profiles, source references, research notes, and preferences; DELETE endpoints remove records by ID.

## Data, privacy, and prototype boundaries

All seeded network names and filing examples are synthetic. Live quotes prefer NSE and use Yahoo Finance only as a labelled fallback; Yahoo EOD history is stored locally. NSE announcements and Screener-discovered company documents are fetched on demand. Indexed document text remains in the local SQLite database. No LinkedIn or LLM service is connected; source search is deterministic and cites the original link and PDF page. User-entered profiles and preferences also stay local. The server binds only to `127.0.0.1` by default and has no authentication, so do not expose a writable instance or store sensitive real contact data in this demo.

The research screen withholds numeric company metrics. It indexes document text and returns relevant source excerpts, but it does not calculate Revenue, EBITDA, PBT or PAT QoQ/YoY, reconcile statement tables, or summarize management guidance. A production analysis layer should extract period-labelled figures and guidance claims from primary documents, reconcile them, and retain source page spans before presenting calculations.

### Production architecture direction

1. **Ingestion:** refresh stale EOD bars when the app starts; ingest NSE/BSE announcements and issuer annual-report, quarterly-results and transcript sources. Persist immutable source documents and normalized entities with timestamps and source URLs.
2. **Extraction:** classify announcement type and materiality; parse financial tables deterministically where possible; use a constrained model for summaries and transcript claims. Store each claim with source document, page/section, period, units, extraction version, and confidence. Reconcile figures before computing QoQ/YoY.
3. **Network:** tenant-isolated people, affiliations and relationship edges; explicit provenance, consent, retention and deletion controls. Match filing names against known people with reviewable confidence, never silently assert a match.
4. **Serving:** API for portfolio, digest, alerts, research and graph search. Cache source-derived analyses. Use a small model for bulk classification and a stronger model only for multi-document reasoning. Ask before outreach; the prototype never contacts anyone.
5. **Security:** encrypt data in transit and at rest, isolate tenant keys/records, apply role-based access, minimize profile retention, audit accesses, and make source and consent state visible. Network data must never be used across investors.

## Suggested next implementation steps

1. Add period-aware table extraction and auditable QoQ/YoY calculations for quarterly result filings.
2. Replace local sample profiles with consented/imported contacts and a tenant-scoped graph store.
3. Add authentication, deployment configuration, observability, and a real mobile installable shell.

## Files

- `index.html` — responsive app and frontend interactions.
- `server.py` — local REST API, SQLite persistence, and quote provider adapter.
- `requirements.txt` — pypdf used to extract searchable text from PDF documents.
- `finn.db` — created locally at first startup; not checked into source control.
- `README.md` — setup, data caveats and architecture direction.
- `SUBMISSION.md` — covering-email draft and release checklist.
- `AI_BUILD_HISTORY.md` — honest summary of the AI-assisted work; add a session export/share link if one is made available.
- `Dockerfile` / `compose.yaml` — read-only demo container setup.
- Challenge PDFs are supplied separately and are not required to run the app.
