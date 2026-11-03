import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import worker, { isDue } from "../src/index.js";

const TOKEN = "fake-token-for-tests";
const env = {
  GITHUB_TOKEN: TOKEN,
  GITHUB_OWNER: "ben10gregory1",
  GITHUB_REPO: "class-bot",
  GITHUB_WORKFLOW: "watch.yml",
  GITHUB_REF: "main",
  FAST_FROM: "2026-11-05T05:00:00Z",
  FAST_UNTIL: "2026-11-08T05:00:00Z",
};
const realFetch = globalThis.fetch;
const realLog = console.log;

function mockFetch(status, body = "") {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return new Response(status === 204 ? null : body, { status });
  };
  return calls;
}

afterEach(() => {
  globalThis.fetch = realFetch;
  console.log = realLog;
});

test("POSTs one dispatch with no inputs to watch.yml on main", async () => {
  const calls = mockFetch(200, "{}");
  console.log = () => {};
  await worker.scheduled({}, env);
  assert.equal(calls.length, 1);
  assert.equal(
    calls[0].url,
    "https://api.github.com/repos/ben10gregory1/class-bot/actions/workflows/watch.yml/dispatches",
  );
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.headers.Authorization, `Bearer ${TOKEN}`);
  assert.deepEqual(JSON.parse(calls[0].init.body), { ref: "main" });
});

test("outside the fast window only 10-min marks dispatch", () => {
  assert.equal(isDue(Date.parse("2026-11-03T02:10:00Z"), env), true);
  assert.equal(isDue(Date.parse("2026-11-03T02:15:00Z"), env), false);
  assert.equal(isDue(Date.parse("2026-11-08T05:05:00Z"), env), false);
});

test("inside the fast window every 5-min tick dispatches", () => {
  assert.equal(isDue(Date.parse("2026-11-05T05:05:00Z"), env), true);
  assert.equal(isDue(Date.parse("2026-11-08T04:55:00Z"), env), true);
});

test("a skipped tick makes no network call", async () => {
  const calls = mockFetch(200, "{}");
  await worker.scheduled({ scheduledTime: Date.parse("2026-11-03T02:15:00Z") }, env);
  assert.equal(calls.length, 0);
});

test("a missing or bad window falls back to 10-min marks", () => {
  assert.equal(isDue(Date.parse("2026-11-05T06:05:00Z"), {}), false);
});

test("accepts 204, the status older API versions return", async () => {
  mockFetch(204);
  console.log = () => {};
  await worker.scheduled({}, env);
});

test("logs success without the token", async () => {
  mockFetch(200, "{}");
  const lines = [];
  console.log = (line) => lines.push(line);
  await worker.scheduled({}, env);
  assert.deepEqual(lines, ["dispatch ok: HTTP 200"]);
});

for (const [status, hint] of [
  [401, /expired/],
  [403, /Actions write/],
  [404, /wrong owner/],
  [422, /bad ref/],
  [500, /next tick/],
]) {
  test(`HTTP ${status} throws a clear error without the token`, async () => {
    mockFetch(status, '{"message":"nope"}');
    await assert.rejects(worker.scheduled({}, env), (err) => {
      assert.match(err.message, new RegExp(`HTTP ${status}`));
      assert.match(err.message, hint);
      assert.match(err.message, /nope/);
      assert.ok(!err.message.includes(TOKEN));
      return true;
    });
  });
}

test("missing token throws before any network call", async () => {
  const calls = mockFetch(200, "{}");
  await assert.rejects(worker.scheduled({}, { ...env, GITHUB_TOKEN: undefined }), /secret unset/);
  assert.equal(calls.length, 0);
});
