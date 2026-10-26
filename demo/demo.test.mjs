import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { webcrypto } from "node:crypto";
function browser() {
  let offset = 0;
  class Clock extends Date {
    static now() {
      return Date.now() + offset;
    }
  }
  let network = 0;
  const scope = {
    DEMO_SEED: JSON.parse(
      readFileSync(new URL("./seed.json", import.meta.url), "utf8"),
    ),
    structuredClone,
    Response,
    Headers,
    URL,
    DOMException,
    TextEncoder,
    TextDecoder,
    Uint8Array,
    Date: Clock,
    crypto: webcrypto,
    location: new URL("https://example.test/project/"),
    fetch: async () => {
      network++;
      throw Error("Unexpected network request");
    },
  };
  runInNewContext(
    readFileSync(new URL("./browser.js", import.meta.url), "utf8"),
    scope,
  );
  return {
    call: async (path, method = "GET", body, headers) => {
      const response = await scope.fetch(path, {
        method,
        ...(body ? { body: JSON.stringify(body) } : {}),
        headers,
      });
      return { status: response.status, body: await response.json() };
    },
    advance: (ms) => {
      offset += ms;
    },
    network: () => network,
  };
}
test("saved reports and history do not impersonate a fresh GitHub analysis", async () => {
  const b = browser();
  const existing = (await b.call("/api/analyses")).body;
  assert(existing.length > 0);
  assert.equal(
    (
      await b.call("/api/analyses", "POST", {
        repository: "memorim/seatly-workspace-booking",
      })
    ).status,
    409,
  );
  const copy = await b.call("/api/analyses/demo", "POST");
  assert.equal(copy.status, 201);
  assert.equal(copy.body.score, existing[0].score);
  assert.equal(
    (await b.call("/api/analyses")).body.length,
    existing.length + 1,
  );
  assert.equal(b.network(), 0);
});
