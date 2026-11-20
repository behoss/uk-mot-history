import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { MotHistoryClient, MotHistoryError, findMileageAnomalies, mileageReadings, motExpiry, normaliseRegistration } from "../src/index.js";

const vehicle = JSON.parse(readFileSync(new URL("./vehicle.json", import.meta.url)));
const newReg = JSON.parse(readFileSync(new URL("./new_reg.json", import.meta.url)));
const TOKEN_URL = "https://login.example.test/tenant/oauth2/v2.0/token";

function fakeFetch(responses) {
  const calls = [];
  let tokens = 0;
  const fn = async (url, init) => {
    calls.push({ url, init });
    if (url === TOKEN_URL) {
      tokens++;
      return Response.json({ access_token: `fake-token-${tokens}`, expires_in: 3599 });
    }
    const [status, body] = responses.shift();
    const headers = status === 429 ? { "retry-after": "1" } : {};
    return body === null ? new Response(null, { status, headers }) : Response.json(body, { status, headers });
  };
  fn.calls = calls;
  fn.tokens = () => tokens;
  return fn;
}

function client(responses, extra = {}) {
  const fetch = fakeFetch(responses);
  const sleeps = [];
  const c = new MotHistoryClient({
    clientId: "test-client", clientSecret: "test-secret", apiKey: "test-api-key", tokenUrl: TOKEN_URL,
    fetch, sleep: async (ms) => { sleeps.push(ms); }, ...extra,
  });
  return { c, fetch, sleeps };
}

test("byRegistration normalises and sends both auth headers", async () => {
  const { c, fetch } = client([[200, vehicle]]);
  const v = await c.byRegistration("ab12 cde");
  assert.equal(v.model, "FOCUS");
  const api = fetch.calls.at(-1);
  assert.equal(api.url, "https://history.mot.api.gov.uk/v1/trade/vehicles/registration/AB12CDE");
  assert.equal(api.init.headers.authorization, "Bearer fake-token-1");
  assert.equal(api.init.headers["x-api-key"], "test-api-key");
  assert.match(fetch.calls[0].init.body, /grant_type=client_credentials/);
});

test("token is cached across calls, and concurrent calls share one token request", async () => {
  const { c, fetch } = client([[200, vehicle], [200, newReg], [200, vehicle]]);
  await Promise.all([c.byRegistration("AB12CDE"), c.byVin("WF0AXXGCDACB12345")]);
  await c.byRegistration("AB12CDE");
  assert.equal(fetch.tokens(), 1);
  assert.ok(fetch.calls.some((x) => x.url.endsWith("/v1/trade/vehicles/vin/WF0AXXGCDACB12345")));
});

test("401 refreshes the token once", async () => {
  const { c, fetch } = client([[401, null], [200, vehicle]]);
  await c.byRegistration("AB12CDE");
  assert.equal(fetch.tokens(), 2);
});

test("429 and 5xx are retried with Retry-After and backoff", async () => {
  const { c, sleeps } = client([[429, null], [503, null], [200, vehicle]]);
  await c.byRegistration("AB12CDE");
  assert.deepEqual(sleeps, [1000, 1000]);
});

test("errors carry a kind", async () => {
  const { c } = client([[404, { errorCode: "MOTH-NF-01", errorMessage: "No data found" }]]);
  await assert.rejects(c.byRegistration("ZZ99ZZZ"), (e) => e instanceof MotHistoryError && e.kind === "not-found" && e.errorCode === "MOTH-NF-01");
  const { c: c2 } = client([[429, null], [429, null], [429, null], [429, null]]);
  await assert.rejects(c2.byRegistration("AB12CDE"), (e) => e.kind === "rate-limited");
});

test("missing options throw a config error", () => {
  assert.throws(() => MotHistoryClient.fromEnv({}), (e) => e.kind === "config");
});

test("mileage helpers flag a drop between tests", () => {
  assert.deepEqual(mileageReadings(vehicle).map((r) => r.miles), [49870, 61002, 58410, 71240]);
  const [a] = findMileageAnomalies(vehicle);
  assert.equal(a.drop, 2592);
  assert.equal(a.later.date, "2023-02-20");
  assert.equal(findMileageAnomalies(vehicle, 5000).length, 0);
  assert.equal(motExpiry(vehicle), "2025-02-28");
  assert.equal(motExpiry(newReg), "2027-09-01");
  assert.equal(normaliseRegistration(" ab12-cde "), "AB12CDE");
});
