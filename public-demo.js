/* GitHub Pages API adapter. Data is a timestamped CI snapshot; edits live only
   in this browser. The local Python server remains the full writable API. */
(() => {
  if (!location.hostname.endsWith("github.io")) return;

  const nativeFetch = window.fetch.bind(window);
  const prefix = `finn-public-demo:${location.pathname}:`;
  const memory = new Map();
  let snapshotPromise;
  let serial = Date.now();

  function load(key, fallback) {
    try {
      const raw = localStorage.getItem(prefix + key);
      return raw === null ? fallback : JSON.parse(raw);
    } catch (_) {
      return memory.has(key) ? memory.get(key) : fallback;
    }
  }

  function save(key, value) {
    memory.set(key, value);
    try { localStorage.setItem(prefix + key, JSON.stringify(value)); } catch (_) {}
  }

  function getSnapshot() {
    if (!snapshotPromise) {
      const url = new URL("demo-data.json", location.href);
      url.searchParams.set("v", "snapshot");
      snapshotPromise = nativeFetch(url, { cache: "no-store" }).then(async response => {
        if (!response.ok) throw new Error(`Public data snapshot unavailable (${response.status})`);
        return response.json();
      });
    }
    return snapshotPromise;
  }

  function json(value, status = 200) {
    return new Response(JSON.stringify(value), {
      status,
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  }

  function locals() {
    return {
      events: load("events", []),
      people: load("people", []),
      sources: load("sources", []),
      notes: load("notes", []),
      preferences: load("preferences", {}),
    };
  }

  function allEvents(snapshot, local) {
    return [...(snapshot.events || []), ...local.events];
  }

  function allPeople(snapshot, local) {
    return [...(snapshot.people || []), ...local.people];
  }

  function documents(snapshot, ticker) {
    return (snapshot.documents || []).filter(item => item.ticker === ticker);
  }

  function passagesFor(snapshot, ticker) {
    return (snapshot.passages || []).filter(item => item.ticker === ticker);
  }

  function makeRecord(fields) {
    return { id: ++serial, created_at: new Date().toISOString(), ...fields };
  }

  function asArrayMatch(items, query) {
    const term = String(query || "").trim().toLowerCase();
    return items.filter(item => !term || Object.values(item).join(" ").toLowerCase().includes(term));
  }

  function searchPassages(snapshot, ticker, question) {
    const ignored = new Set(["about", "after", "against", "and", "are", "can", "company", "does", "from", "how", "into", "its", "latest", "more", "most", "over", "show", "that", "the", "their", "this", "through", "what", "when", "where", "which", "with", "would"]);
    const terms = [...new Set((String(question).toLowerCase().match(/[a-z0-9.%+-]{2,}/g) || []).filter(term => !ignored.has(term)))];
    const matches = passagesFor(snapshot, ticker).map(item => {
      const text = item.text.toLowerCase();
      const score = terms.reduce((total, term) => total + (text.includes(term) ? 1 + (text.split(term).length > 2 ? 0.5 : 0) : 0), 0);
      return { ...item, score };
    }).filter(item => item.score > 0).sort((a, b) => b.score - a.score || a.title.localeCompare(b.title) || a.page - b.page).slice(0, 8);
    return {
      ticker,
      question,
      matches,
      method: "Keyword retrieval from short excerpts in the dated public snapshot. Open the source document to review the full context.",
      notice: "Excerpts are evidence to review. FINN does not infer values, periods, or guidance that the source does not state.",
    };
  }

  async function route(url, method, body) {
    const snapshot = await getSnapshot();
    const local = locals();
    const path = url.pathname.replace(/^\/(?:FINN\/)?/, "/");
    const query = url.searchParams.get("q") || "";
    const now = snapshot.generated_at;
    const localStatus = (source, ok) => ({
      source,
      status: ok ? "ok" : "error",
      records: 0,
      detail: ok ? "Included in the public source snapshot." : "Provider fetch failed while this snapshot was collected.",
      created_at: now,
    });

    if (method === "GET" && path === "/api/health") return json({ ok: true, app: "FINN", mode: "static snapshot", time: now });
    if (method === "GET" && path === "/api/bootstrap") {
      return json({
        companies: snapshot.companies || [],
        events: allEvents(snapshot, local),
        people: allPeople(snapshot, local),
        preferences: { ...(snapshot.preferences || {}), ...local.preferences },
        market_data: snapshot.market_data || [],
        read_only: false,
        last_nse_sync: snapshot.last_nse_sync || localStatus("NSE announcements", snapshot.sync_results?.nse?.ok),
        last_price_sync: snapshot.last_price_sync || localStatus("Yahoo Finance EOD", snapshot.sync_results?.prices?.ok),
        source_mode: `static public-source snapshot · collected ${now}; edits are stored in this browser`,
      });
    }
    if (method === "GET" && path === "/api/companies") return json(snapshot.companies || []);
    if (method === "GET" && path === "/api/events") return json(allEvents(snapshot, local));
    if (method === "GET" && path === "/api/sync/status") return json(snapshot.sync_log || []);
    if (method === "GET" && path === "/api/network") return json(asArrayMatch(allPeople(snapshot, local), query));

    let match = path.match(/^\/api\/quote\/([^/]+)$/);
    if (method === "GET" && match) {
      const symbol = decodeURIComponent(match[1]).toUpperCase();
      const ticker = symbol.replace(/\.(NS|BO)$/, "");
      const record = (snapshot.market_data || []).find(item => item.ticker === ticker);
      if (!record) return json({ ticker, error: "No price for this company in the public snapshot.", hint: "The hosted demo refreshes its snapshot through the daily deployment job." }, 404);
      return json({ ticker, symbol, price: record.close, change_pct: record.change_pct, volume: record.volume, currency: "INR", provider: `${record.provider} (public snapshot)`, as_of: record.session_date, snapshot: true, simulated: false });
    }

    match = path.match(/^\/api\/sources\/([^/]+)$/);
    if (method === "GET" && match) {
      const ticker = decodeURIComponent(match[1]).toUpperCase();
      return json([...(snapshot.sources || []).filter(item => item.ticker === ticker), ...local.sources.filter(item => item.ticker === ticker)]);
    }
    match = path.match(/^\/api\/research\/([^/]+)$/);
    if (method === "GET" && match) {
      const ticker = decodeURIComponent(match[1]).toUpperCase().replace(/[^A-Z0-9]/g, "");
      return json({ ticker, sources: (snapshot.sources || []).filter(item => item.ticker === ticker), documents: documents(snapshot, ticker), notes: local.notes.filter(item => item.ticker === ticker), notice: "Documents are collected in the public snapshot; verify the original issuer or exchange document before relying on a claim." });
    }

    if (method === "POST" && path === "/api/sync/prices") {
      return json({ mode: "snapshot", as_of: now, updated: (snapshot.market_data || []).length, alerts: (snapshot.events || []).filter(item => item.category === "Price move" || item.category === "Volume spike").length, provider_status: snapshot.sync_results?.prices || null });
    }
    if (method === "POST" && path === "/api/sync/nse") {
      const result = snapshot.sync_results?.nse || {};
      return json({ mode: "snapshot", as_of: now, source: "NSE India corporate announcements", received: result.received || 0, portfolio_matches: result.portfolio_matches || 0, inserted: result.inserted || 0, provider_status: result.ok === false ? "unavailable during snapshot collection" : "included in snapshot" });
    }
    match = path.match(/^\/api\/sync\/company\/([A-Z0-9.]+)$/);
    if (method === "POST" && match) {
      const ticker = match[1].replace(/[^A-Z0-9]/g, "");
      const found = documents(snapshot, ticker);
      return json({ mode: "snapshot", ticker, count: found.length, documents: found, as_of: now });
    }
    match = path.match(/^\/api\/research\/index\/([A-Z0-9.]+)$/);
    if (method === "POST" && match) {
      const ticker = match[1].replace(/[^A-Z0-9]/g, "");
      const docs = documents(snapshot, ticker);
      return json({ mode: "snapshot", ticker, indexed: docs.filter(item => item.indexed_at && !item.error).length, errors: docs.filter(item => item.error).map(item => ({ title: item.title, error: item.error })), documents: docs, as_of: now });
    }
    if (method === "POST" && path === "/api/research/ask") {
      const ticker = String(body.ticker || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
      const question = String(body.question || "").trim();
      if (!ticker || !question) return json({ error: "ticker and question are required" }, 400);
      return json(searchPassages(snapshot, ticker, question));
    }
    if (method === "POST" && path === "/api/events") {
      const required = ["ticker", "category", "priority", "title", "summary"];
      if (required.some(key => !String(body[key] || "").trim())) return json({ error: "ticker, category, priority, title and summary are required" }, 400);
      const event = makeRecord({ ...body, ticker: String(body.ticker).toUpperCase(), network_context: [] });
      local.events.push(event); save("events", local.events);
      return json(event, 201);
    }
    if (method === "POST" && path === "/api/network") {
      const name = String(body.name || "").trim();
      if (!name) return json({ error: "name is required" }, 400);
      const person = makeRecord({ ...body, name, initials: body.initials || name.split(/\s+/).slice(0, 2).map(item => item[0]).join("").toUpperCase(), role: body.role || "", sectors: body.sectors || "", context: body.context || "User added profile", synthetic: 0, tags: [] });
      local.people.push(person); save("people", local.people);
      return json(person, 201);
    }
    if (method === "POST" && path === "/api/sources") {
      if (!body.ticker || !body.title || !String(body.url || "").startsWith("https://")) return json({ error: "ticker, title and an HTTPS url are required" }, 400);
      const source = makeRecord({ ...body, ticker: String(body.ticker).toUpperCase(), kind: body.kind || "primary" });
      local.sources.push(source); save("sources", local.sources);
      return json(source, 201);
    }
    if (method === "POST" && path === "/api/research/notes") {
      if (!body.ticker || !body.body) return json({ error: "ticker and body are required" }, 400);
      const note = makeRecord({ ...body, ticker: String(body.ticker).toUpperCase() });
      local.notes.push(note); save("notes", local.notes);
      return json(note, 201);
    }
    if (method === "POST" && path === "/api/preferences") {
      local.preferences = { ...local.preferences, ...body };
      save("preferences", local.preferences);
      return json({ saved: true, preferences: body });
    }
    match = path.match(/^\/api\/(events|network|sources|research\/notes)\/(\d+)$/);
    if (method === "DELETE" && match) {
      const key = { events: "events", network: "people", sources: "sources", "research/notes": "notes" }[match[1]];
      const before = local[key].length;
      local[key] = local[key].filter(item => String(item.id) !== match[2]);
      save(key, local[key]);
      return json({ deleted: local[key].length < before });
    }
    return json({ error: `Unsupported public demo API route: ${method} ${path}` }, 404);
  }

  window.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === "string" || input instanceof URL ? input : input.url, location.href);
    if (!url.pathname.includes("/api/")) return nativeFetch(input, init);
    const method = String(init.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
    let body = {};
    if (init.body) {
      try { body = JSON.parse(init.body); } catch (_) { return json({ error: "Invalid JSON request body" }, 400); }
    }
    try {
      return await route(url, method, body);
    } catch (error) {
      return json({ error: error.message || "Public demo data unavailable" }, 503);
    }
  };
})();
