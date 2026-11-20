// uk-mot-history: zero-dependency client for the UK DVSA MOT History API.
// Works anywhere with a global fetch: Node 20+, Cloudflare Workers, Deno, Bun.
// https://github.com/behoss/uk-mot-history (MIT)

export const API_BASE = "https://history.mot.api.gov.uk";
export const DEFAULT_SCOPE = "https://tapi.dvsa.gov.uk/.default";
const RETRY = new Set([429, 500, 502, 503, 504]);
const KM_PER_MILE = 1.609344;

export class MotHistoryError extends Error {
  /** @param {string} message @param {{ status?: number, errorCode?: string, kind?: string }} [info] */
  constructor(message, info = {}) {
    super(message);
    this.name = "MotHistoryError";
    this.status = info.status;
    this.errorCode = info.errorCode;
    /** "config" | "auth" | "not-found" | "invalid" | "rate-limited" | "upstream" */
    this.kind = info.kind ?? "upstream";
  }
}

/** "ab12 cde" -> "AB12CDE" */
export function normaliseRegistration(value) {
  return String(value).toUpperCase().replace(/[^A-Z0-9]/g, "");
}

const KINDS = { 400: "invalid", 401: "auth", 403: "auth", 404: "not-found", 429: "rate-limited" };

export class MotHistoryClient {
  /** @param {import("./index").MotHistoryOptions} options */
  constructor(options) {
    const { clientId, clientSecret, apiKey, tenantId } = options ?? {};
    const tokenUrl = options?.tokenUrl ?? (tenantId ? `https://login.microsoftonline.com/${tenantId}/oauth2/v2.0/token` : "");
    const missing = Object.entries({ clientId, clientSecret, apiKey, tenantId: tokenUrl }).filter(([, v]) => !v).map(([k]) => k);
    if (missing.length) throw new MotHistoryError(`missing options: ${missing.join(", ")}`, { kind: "config" });
    this.clientId = clientId;
    this.clientSecret = clientSecret;
    this.apiKey = apiKey;
    this.tokenUrl = tokenUrl;
    this.scope = options.scope ?? DEFAULT_SCOPE;
    this.baseUrl = (options.baseUrl ?? API_BASE).replace(/\/$/, "");
    this.maxRetries = options.maxRetries ?? 3;
    this.backoffMs = options.backoffMs ?? 500;
    this.timeoutMs = options.timeoutMs ?? 10_000;
    this.fetch = options.fetch ?? ((input, init) => globalThis.fetch(input, init));
    this.sleep = options.sleep ?? ((ms) => new Promise((r) => setTimeout(r, ms)));
    this.now = options.now ?? (() => Date.now());
    /** @type {{ value: string, exp: number } | null} */
    this.token = null;
    /** @type {Promise<string> | null} */
    this.pending = null;
  }

  /** Build from MOT_HISTORY_CLIENT_ID, _CLIENT_SECRET, _API_KEY and _TENANT_ID (process.env or a Workers env). */
  static fromEnv(env = globalThis.process?.env ?? {}) {
    return new MotHistoryClient({
      clientId: env.MOT_HISTORY_CLIENT_ID,
      clientSecret: env.MOT_HISTORY_CLIENT_SECRET,
      apiKey: env.MOT_HISTORY_API_KEY,
      tenantId: env.MOT_HISTORY_TENANT_ID,
      tokenUrl: env.MOT_HISTORY_TOKEN_URL || undefined,
    });
  }

  /** MOT history by registration (spaces and case don't matter). */
  async byRegistration(registration) {
    const reg = normaliseRegistration(registration);
    if (!reg) throw new MotHistoryError("empty registration", { kind: "invalid" });
    return this.#get(`/v1/trade/vehicles/registration/${encodeURIComponent(reg)}`);
  }

  /** MOT history by VIN. */
  async byVin(vin) {
    const clean = normaliseRegistration(vin);
    if (!clean) throw new MotHistoryError("empty VIN", { kind: "invalid" });
    return this.#get(`/v1/trade/vehicles/vin/${encodeURIComponent(clean)}`);
  }

  /** Links to the bulk extract and daily delta files. */
  async bulkDownload() {
    return this.#get("/v1/trade/vehicles/bulk-download");
  }

  /** A bearer token, cached until a minute before it expires (concurrent callers share one request). */
  async accessToken(force = false) {
    if (!force && this.token && this.token.exp - 60_000 > this.now()) return this.token.value;
    if (!this.pending) {
      this.pending = this.#fetchToken().finally(() => {
        this.pending = null;
      });
    }
    return this.pending;
  }

  async #fetchToken() {
    const body = new URLSearchParams({
      grant_type: "client_credentials",
      client_id: this.clientId,
      client_secret: this.clientSecret,
      scope: this.scope,
    });
    const res = await this.#send(this.tokenUrl, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded", accept: "application/json" },
      body: body.toString(),
    });
    if (!res.ok) {
      const kind = [400, 401, 403].includes(res.status) ? "auth" : "upstream";
      throw new MotHistoryError(`token request failed (${res.status})`, { status: res.status, kind });
    }
    const j = await res.json();
    if (!j?.access_token) throw new MotHistoryError("token response had no access_token", { kind: "auth" });
    this.token = { value: j.access_token, exp: this.now() + (Number(j.expires_in) || 3600) * 1000 };
    return this.token.value;
  }

  async #send(url, init) {
    for (let attempt = 0; ; attempt++) {
      let res;
      try {
        res = await this.fetch(url, { ...init, signal: AbortSignal.timeout(this.timeoutMs) });
      } catch (err) {
        if (attempt >= this.maxRetries) throw new MotHistoryError(`network error: ${err?.message ?? err}`, { kind: "upstream" });
        await this.sleep(this.backoffMs * 2 ** attempt);
        continue;
      }
      if (!RETRY.has(res.status) || attempt >= this.maxRetries) return res;
      const after = Number(res.headers.get("retry-after"));
      await this.sleep(after > 0 ? Math.min(after, 30) * 1000 : this.backoffMs * 2 ** attempt);
    }
  }

  async #get(path) {
    let res;
    for (let refreshed = false; ; refreshed = true) {
      res = await this.#send(`${this.baseUrl}${path}`, {
        headers: { authorization: `Bearer ${await this.accessToken(refreshed)}`, "x-api-key": this.apiKey, accept: "application/json" },
      });
      if (res.status !== 401 || refreshed) break;
    }
    if (res.ok) return res.json();
    let code, message;
    try {
      const j = await res.json();
      code = j?.errorCode;
      message = j?.errorMessage;
    } catch {
      /* no JSON body */
    }
    throw new MotHistoryError(`${res.status}${code ? ` ${code}` : ""}: ${message ?? "MOT History API error"}`, {
      status: res.status,
      errorCode: code,
      kind: KINDS[res.status] ?? "upstream",
    });
  }
}

/** Odometer reading of one test in miles, or null if it was not read. */
export function odometerMiles(test) {
  if (test?.odometerResultType !== "READ") return null;
  const n = Number(String(test.odometerValue ?? "").replace(/,/g, ""));
  if (!Number.isFinite(n) || String(test.odometerValue ?? "") === "") return null;
  return test.odometerUnit === "KM" ? Math.round(n / KM_PER_MILE) : n;
}

/** Readable odometer readings, oldest first. */
export function mileageReadings(vehicle) {
  return (vehicle?.motTests ?? [])
    .map((test) => ({ date: String(test.completedDate).slice(0, 10), miles: odometerMiles(test), test }))
    .filter((r) => r.miles !== null)
    .sort((a, b) => String(a.test.completedDate).localeCompare(String(b.test.completedDate)));
}

/**
 * Points where the odometer went down (by more than `tolerance` miles) against the highest earlier reading: the
 * classic clocking warning. A drop can also be a typo or a replaced cluster, so treat it as a flag to investigate.
 */
export function findMileageAnomalies(vehicle, tolerance = 0) {
  const out = [];
  let peak = null;
  for (const r of mileageReadings(vehicle)) {
    if (peak && peak.miles - r.miles > tolerance) out.push({ earlier: peak, later: r, drop: peak.miles - r.miles });
    if (!peak || r.miles > peak.miles) peak = r;
  }
  return out;
}

/** Expiry date (YYYY-MM-DD) of the latest passed test, or the first MOT due date for a new vehicle. */
export function motExpiry(vehicle) {
  const passed = [...(vehicle?.motTests ?? [])]
    .filter((t) => t.testResult === "PASSED" && t.expiryDate)
    .sort((a, b) => String(b.completedDate).localeCompare(String(a.completedDate)));
  return passed[0]?.expiryDate ?? vehicle?.motTestDueDate ?? null;
}
