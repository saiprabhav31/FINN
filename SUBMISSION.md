# FINN submission pack

## Covering email

**To:** assessment@enam.com

**Subject:** IIT Kanpur – Founding AI Engineer - 2027

Dear ENAM team,

I’m submitting FINN, a mobile-first investment intelligence prototype built for the Founding AI Engineer challenge.

- **Working demo:** [ADD DEPLOYED DEMO URL]
- **Public source repository:** [ADD PUBLIC REPOSITORY URL]
- **Build history:** see `AI_BUILD_HISTORY.md` in the repository (and add the relevant coding-agent session export/share link if requested).

FINN brings together a prioritized daily brief, on-demand company research, and a private network-intelligence view. The prototype includes a persistent SQLite API, an NSE announcement sync with source links, NSE-first quote lookup, Yahoo Finance end-of-day price history, configurable price/volume alerts, report/transcript link discovery, synthetic network profiles, and alert preferences. Research figures and seeded announcements are explicitly marked as simulated. Report and transcript links are discoverable, but their contents are not yet parsed into source-cited financial analysis.

I kept the scope deliberately narrow so the core interaction is demonstrable on a phone. The backend stores portfolio, filing, network, source-reference, research-note, and preference records in SQLite. Market quotes are fetched on demand; the demo can run in read-only mode for a public showcase. Network profiles are synthetic, and the local version should not be used with sensitive personal data.

Given more time, I would replace the public-web announcement adapter with an approved/licensed feed for production use, build source-cited extraction for annual reports/results/transcripts, and add authentication plus tenant isolation before handling real investor networks.

Thank you for your time. I’d be glad to walk through the product and the implementation decisions.

Regards,

[YOUR NAME]

[YOUR CONTACT DETAILS]

## Release checklist

- [ ] Replace both placeholder URLs with a publicly reachable demo and repository.
- [ ] Confirm the public demo is running with the read-only Compose configuration.
- [ ] Open the demo on a phone-sized viewport and verify the layout before sending.
- [ ] Confirm the repository does not contain `finn.db`, real contacts, credentials, or personal data.
- [ ] Add your name/contact details and confirm the requested email subject.
- [ ] Attach or link the full coding-agent/LLM session export if available; the included build-history note is a summary, not a raw session export.
- [ ] Send the email yourself after reviewing the final links and wording.

## Demo deployment

From a machine with Docker Compose installed, run `docker compose up --build -d`. The service listens on port 8765 and uses a persistent named volume. The included configuration enables read-only mode and seeds synthetic records on first startup. For a public host, terminate HTTPS at a trusted reverse proxy and keep the app read-only. This prototype has no user authentication and is not suitable for storing real network profiles or exposing a writable instance.
