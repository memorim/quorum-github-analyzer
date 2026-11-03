// Browser-only adapter, loaded exclusively by scripts/build_demo.py.
// ponytail: state lasts for one page session; use the documented server for shared, durable data.
(() => {
  const state = structuredClone(globalThis.DEMO_SEED);
  try {
    const saved = JSON.parse(localStorage.getItem('quorum-history') || 'null');
    if (Array.isArray(saved) && saved.length <= 100 && saved.every(r => r && typeof r.id === 'string' && typeof r.repository === 'string' && r.metrics && Array.isArray(r.actions))) state['/api/analyses'] = saved;
  } catch { /* Continue with session history when storage is unavailable. */ }
  const persist = () => { try { localStorage.setItem('quorum-history', JSON.stringify(state['/api/analyses'])); } catch { /* Session remains usable. */ } };
  const pending = new Map();
  const fail = (message, status = 400) => {
    throw Object.assign(new Error(message), { status });
  };
  const text = (value, min = 1, max = 200) => {
    if (
      typeof value !== "string" ||
      value.trim().length < min ||
      value.trim().length > max
    )
      fail("Проверьте введённые данные");
    return value.trim();
  };
  const json = (value, status = 200) =>
    new Response(JSON.stringify(value), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  const originalFetch = globalThis.fetch.bind(globalThis);
  globalThis.fetch = async (input, options = {}) => {
    const url = new URL(input, globalThis.location.href);
    if (
      url.origin !== globalThis.location.origin ||
      !url.pathname.startsWith("/api/")
    )
      return originalFetch(input, options);
    if (options.signal?.aborted)
      throw new DOMException("Aborted", "AbortError");
    try {
      return await handle(
        url,
        options.method || "GET",
        options.body ? JSON.parse(options.body) : {},
        new Headers(options.headers),
      );
    } catch (error) {
      return json(
        { message: error.message, detail: error.message },
        error.status || 400,
      );
    }
  };
  globalThis.PORTFOLIO_DEMO = true;

  async function handle(url, method, body) {
    if (url.pathname === "/api/analyses" && method === "GET")
      return json(state["/api/analyses"]);
    if (url.pathname === "/api/overview")
      return json({
        analyses: state["/api/analyses"].length,
        open_actions: state["/api/analyses"][0]?.actions.length || 0,
      });
    if (url.pathname === "/api/analyses/demo" && method === "POST") {
      if (state["/api/analyses"].length >= 20)
        fail("Перезагрузите страницу для новой сессии", 429);
      const report = {
        ...structuredClone(state["/api/analyses"][0]),
        id: crypto.randomUUID(),
        created_at: new Date().toISOString(),
      };
      state["/api/analyses"].unshift(report);
      persist();
      return json(report, 201);
    }
    if (url.pathname.startsWith('/api/analyses/') && method === 'GET') {
      const report = state['/api/analyses'].find(r => r.id === url.pathname.split('/').at(-1));
      if (!report) fail('Отчёт не найден',404);
      return json(report);
    }
    if (url.pathname === "/api/analyses" && method === "POST") {
      const repository = globalThis.QuorumPublic.normalize(text(body.repository,3,150));
      const previous = state['/api/analyses'].find(r => r.repository.toLowerCase() === repository.toLowerCase() && Date.now() - Date.parse(r.created_at) < 60000);
      if (previous) return json(previous,200);
      const key = repository.toLowerCase();
      if (!pending.has(key)) pending.set(key, globalThis.QuorumPublic.analyze(repository).then(report => {
        state['/api/analyses'].unshift(report);
        state['/api/analyses'] = state['/api/analyses'].slice(0,100);
        persist(); return report;
      }).finally(() => pending.delete(key)));
      return json(await pending.get(key),201);
    }
    fail("Не найдено", 404);
  }
})();
