# FINN submission pack

## Covering email

**To:** assessment@enam.com

**Subject:** IIT Kanpur – Founding AI Engineer - 2027

Dear ENAM team,

I’m submitting FINN, a mobile-first investment intelligence prototype built for the Founding AI Engineer challenge.

- **Working demo:** https://saiprabhav31.github.io/FINN/ (responsive demo with a dated public-data snapshot; browser-local edits)
- **Public source repository:** https://github.com/saiprabhav31/FINN
- **AI build history:** `AI_BUILD_HISTORY.md` and its full Codex session share link in the repository.

FINN brings together a prioritized daily brief, company research, and a network-intelligence view. GitHub Pages serves a responsive phone demo with a timestamped snapshot collected from Yahoo Finance, NSE India, and Screener when those providers respond. Its sync controls report snapshot age; the demo stores added filings, profiles, and preferences in browser storage. The local Python REST API and SQLite store support on-demand NSE announcement sync, NSE-first quote lookup, Yahoo Finance end-of-day history, configurable price/volume alerts, company document discovery, page-cited source search, and persistent alert preferences. The static demo bundles TCS source documents and a limited set of excerpts. Numeric company metrics stay hidden until source evidence is available. Search is deterministic and passage-based; the running product does not use an LLM or calculate period comparisons.

The architecture is a mobile-first single-page frontend, a small Python HTTP API, and SQLite persistence locally. A GitHub Actions workflow collects the public snapshot before deploying the static page and refreshes it daily. NSE, Yahoo Finance, and Screener adapters fetch public market and source-document data. I left LLM agents out of the runtime so returned research stays tied to source passages. Seeded profiles are synthetic; browser edits stay on that device. The app has no authentication or tenant isolation, so it must not store real contact data on a shared writable deployment.

I deliberately left out unsourced financial summaries, automatic QoQ/YoY calculations, OCR for scanned PDFs, real-network imports, and investor outreach. Next I would add period-aware statement-table extraction, replace public-web adapters with approved/licensed feeds, and build authentication plus tenant isolation before handling real investor networks.

Thank you for your time. I’d be glad to walk through the product and the implementation decisions.

Regards,

[YOUR NAME]

[YOUR CONTACT DETAILS]

## Release checklist

- [x] Add a public responsive frontend preview and public source repository.
- [ ] Deploy and verify the read-only API using the Compose configuration before representing it as a live full-stack demo.
- [x] Open the demo on a phone-sized viewport and verify the layout before sending.
- [x] Confirm the repository does not contain `finn.db`, real contacts, credentials, or personal data.
- [ ] Add your name/contact details and confirm the requested email subject.
- [x] Link the full Codex build conversation; `AI_BUILD_HISTORY.md` explains the session’s scope and limitations.
- [ ] Send the email yourself after reviewing the final links and wording.

## Demo deployment

From a machine with Docker Compose installed, run `docker compose up --build -d`. The service listens on port 8765 and uses a persistent named volume. The included configuration enables read-only mode and seeds synthetic records on first startup. For a public host, terminate HTTPS at a trusted reverse proxy and keep the app read-only. This prototype has no user authentication and is not suitable for storing real network profiles or exposing a writable instance.
