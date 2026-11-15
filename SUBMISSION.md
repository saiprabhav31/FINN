# FINN submission pack

## Covering email

**To:** assessment@enam.com

**Subject:** IIT Kanpur – Founding AI Engineer - 2027

Dear ENAM team,

I’m submitting FINN, a mobile-first investment intelligence prototype built for the Founding AI Engineer challenge.

- **Working demo:** https://saiprabhav31.github.io/FINN/ (responsive public preview; synthetic offline-demo data)
- **Public source repository:** https://github.com/saiprabhav31/FINN
- **AI build history:** `AI_BUILD_HISTORY.md` and its full Codex session share link in the repository.

FINN brings together a prioritized daily brief, on-demand company research, and a private network-intelligence view. Its responsive frontend is available on GitHub Pages; the public phone demo runs with synthetic offline-demo data. The local Python REST API and SQLite store support an NSE announcement sync with source links, NSE-first quote lookup, Yahoo Finance end-of-day price history, configurable price/volume alerts, report/transcript discovery, page-cited text search, and alert preferences. Numeric company metrics stay hidden until source evidence is available. Search is deterministic and passage-based; the running product does not use an LLM or claim to calculate period comparisons.

The architecture is a mobile-first single-page frontend, a small Python HTTP API, and SQLite persistence. GitHub Pages hosts only the frontend; the read-only Docker Compose setup is the deployment path for the API. NSE, Yahoo Finance, and Screener adapters fetch public market and source-document data. I left LLM agents out of the runtime so returned research stays tied to exact source passages. Seeded events and network profiles are synthetic; the public showcase is read-only, and the app has no authentication or tenant isolation, so it must not store real contact data.

I deliberately left out unsourced financial summaries, automatic QoQ/YoY calculations, OCR for scanned PDFs, real-network imports, and investor outreach. Next I would add period-aware statement-table extraction, replace public-web adapters with approved/licensed feeds, and build authentication plus tenant isolation before handling real investor networks.

Thank you for your time. I’d be glad to walk through the product and the implementation decisions.

Regards,

[YOUR NAME]

[YOUR CONTACT DETAILS]

## Release checklist

- [x] Add a public responsive frontend preview and public source repository.
- [ ] Deploy and verify the read-only API using the Compose configuration before representing it as a live full-stack demo.
- [ ] Open the demo on a phone-sized viewport and verify the layout before sending.
- [ ] Confirm the repository does not contain `finn.db`, real contacts, credentials, or personal data.
- [ ] Add your name/contact details and confirm the requested email subject.
- [x] Link the full Codex build conversation; `AI_BUILD_HISTORY.md` explains the session’s scope and limitations.
- [ ] Send the email yourself after reviewing the final links and wording.

## Demo deployment

From a machine with Docker Compose installed, run `docker compose up --build -d`. The service listens on port 8765 and uses a persistent named volume. The included configuration enables read-only mode and seeds synthetic records on first startup. For a public host, terminate HTTPS at a trusted reverse proxy and keep the app read-only. This prototype has no user authentication and is not suitable for storing real network profiles or exposing a writable instance.
