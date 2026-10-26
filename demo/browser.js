// Browser-only adapter, loaded exclusively by scripts/build_demo.py.
// ponytail: state lasts for one page session; use the documented server for shared, durable data.
(() => {
  const state = structuredClone(globalThis.DEMO_SEED);
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
        open_actions: state["/api/analyses"][0].actions.length,
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
      return json(report, 201);
    }
    if (url.pathname === "/api/analyses" && method === "POST")
      fail(
        "Здесь открыт пример отчёта. Для анализа " +
          text(body.repository, 3, 150) +
          " запустите сервер из README.",
        409,
      );
    fail("Не найдено", 404);
  }
})();
