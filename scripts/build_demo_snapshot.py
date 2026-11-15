"""Collect a small public-data snapshot for the GitHub Pages demo.

The persistent app database is never used or uploaded by this script. It creates
an isolated, seeded database, runs the public-source adapters, and exports only
portfolio events, prices, source metadata, and short searchable excerpts.
"""
from __future__ import annotations

import json
import gc
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "demo-data.json"


def short_passages(server, ticker: str, max_per_document: int = 30) -> list[dict]:
    docs = server.rows(
        """SELECT d.id,d.ticker,d.title,d.url,d.kind,p.page_no,p.text
           FROM company_documents d
           JOIN document_pages p ON p.document_id=d.id
           JOIN company_document_index i ON i.document_id=d.id
           WHERE d.ticker=? AND i.error IS NULL
           ORDER BY d.id,p.page_no""",
        (ticker,),
    )
    terms = re.compile(
        r"revenue|income|cash flow|debt|margin|guidance|capital expenditure|"
        r"segment|profit|order book|capacity|risk|working capital|dividend|"
        r"earnings|ebitda|borrowings|investment|demand|operations",
        re.I,
    )
    result: list[dict] = []
    by_document: dict[int, int] = {}
    seen: set[tuple[int, int, str]] = set()
    for doc in docs:
        sentences = re.split(r"(?<=[.!?])\s+|(?<=\n)|\s{2,}", doc["text"])
        candidates = []
        for sentence in sentences:
            text = " ".join(sentence.split())
            if len(text) < 45:
                continue
            hits = len(terms.findall(text))
            if not hits:
                continue
            text = text[:560].rstrip()
            key = (doc["id"], doc["page_no"], text[:100])
            if key in seen:
                continue
            seen.add(key)
            candidates.append((hits, text))
        # Keep the most useful short source passages, rather than publishing
        # the locally indexed full text in a public static bundle.
        candidates.sort(key=lambda item: (-item[0], len(item[1])))
        count = by_document.get(doc["id"], 0)
        for _score, text in candidates[: max(0, max_per_document - count)]:
            result.append(
                {
                    "ticker": doc["ticker"],
                    "title": doc["title"],
                    "url": doc["url"],
                    "kind": doc["kind"],
                    "page": doc["page_no"],
                    "text": text,
                }
            )
            count += 1
        by_document[doc["id"]] = count
    return result


def main() -> None:
    # Import only after pointing the API module at a fresh temporary database.
    with tempfile.TemporaryDirectory(prefix="finn-pages-", ignore_cleanup_errors=True) as temp:
        os.environ["FINN_DB_PATH"] = str(Path(temp) / "snapshot.db")
        sys.path.insert(0, str(ROOT))
        import server

        server.init_db()
        sync_results: dict[str, dict] = {}
        for key, action in (
            ("prices", server.sync_prices),
            ("nse", server.sync_nse_announcements),
        ):
            try:
                result = action()
                ok = not (key == "prices" and result.get("updated", 0) == 0)
                sync_results[key] = {"ok": ok, **result}
            except Exception as exc:  # Providers can throttle CI runners.
                sync_results[key] = {"ok": False, "error": str(exc)[:300]}
                conn = server.connect()
                source = "Yahoo Finance EOD" if key == "prices" else "NSE announcements"
                conn.execute(
                    "INSERT INTO sync_log(source,status,records,detail,created_at) VALUES(?,?,?,?,?)",
                    (source, "error", 0, str(exc)[:300], datetime.now(timezone.utc).isoformat()),
                )
                conn.close()

        try:
            sync_results["documents"] = server.discover_company_documents("TCS")
            sync_results["index"] = server.index_company_documents("TCS")
        except Exception as exc:
            sync_results["documents"] = {"ok": False, "error": str(exc)[:300]}

        prefs = {}
        for row in server.rows("SELECT key,value FROM preferences"):
            try:
                prefs[row["key"]] = json.loads(row["value"])
            except (ValueError, TypeError):
                prefs[row["key"]] = row["value"]

        def latest(source: str):
            rows = server.rows(
                "SELECT * FROM sync_log WHERE source=? ORDER BY id DESC LIMIT 1", (source,)
            )
            return rows[0] if rows else None

        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "companies": server.rows("SELECT * FROM companies WHERE active=1 ORDER BY name"),
            "events": server.events_with_network(),
            "people": server.network_profiles(),
            "preferences": prefs,
            "market_data": server.rows(
                """SELECT m.ticker,m.session_date,m.close,m.volume,m.provider,
                   CASE WHEN p.close IS NOT NULL AND p.close<>0
                        THEN ROUND((m.close-p.close)*100.0/p.close,2) END AS change_pct
                   FROM market_prices m LEFT JOIN market_prices p
                     ON p.ticker=m.ticker AND p.session_date=(
                       SELECT MAX(x.session_date) FROM market_prices x
                       WHERE x.ticker=m.ticker AND x.session_date<m.session_date)
                   WHERE m.session_date=(SELECT MAX(y.session_date) FROM market_prices y
                                         WHERE y.ticker=m.ticker)"""
            ),
            "sources": server.rows("SELECT * FROM sources ORDER BY id DESC"),
            "documents": server.rows(
                """SELECT d.*,i.page_count,i.char_count,i.indexed_at,i.error
                   FROM company_documents d LEFT JOIN company_document_index i
                     ON i.document_id=d.id ORDER BY d.ticker,d.kind,d.title"""
            ),
            "passages": short_passages(server, "TCS"),
            "sync_results": sync_results,
            "last_nse_sync": latest("NSE announcements"),
            "last_price_sync": latest("Yahoo Finance EOD"),
            "sync_log": server.rows("SELECT * FROM sync_log ORDER BY id DESC LIMIT 20"),
            "source_mode": "static public-source snapshot",
        }
        OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(
            "Snapshot saved: "
            f"{len(payload['market_data'])} prices, {len(payload['events'])} events, "
            f"{len(payload['documents'])} documents, {len(payload['passages'])} short passages"
        )
        summary = {
            "prices": {"ok": sync_results["prices"].get("ok"), "updated": sync_results["prices"].get("updated", 0)},
            "nse": {"ok": sync_results["nse"].get("ok"), "received": sync_results["nse"].get("received", 0), "matches": sync_results["nse"].get("portfolio_matches", 0)},
            "documents": {"discovered": sync_results["documents"].get("count", 0), "indexed": sync_results.get("index", {}).get("indexed", 0)},
        }
        print(json.dumps(summary, ensure_ascii=False))
        gc.collect()


if __name__ == "__main__":
    main()
