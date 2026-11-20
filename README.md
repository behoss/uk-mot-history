# uk-mot-history

**Python and TypeScript client for the UK DVSA MOT History API: every MOT test, mileage reading, defect and recall flag
for a vehicle, by registration or VIN, with clocking warnings built in.**

[![CI](https://github.com/behoss/uk-mot-history/actions/workflows/ci.yml/badge.svg)](https://github.com/behoss/uk-mot-history/actions/workflows/ci.yml)
[![MIT licence](https://img.shields.io/badge/licence-MIT-blue.svg)](LICENSE)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)
![Node 20+ and Workers](https://img.shields.io/badge/node-20%2B%20%7C%20Workers-green)

> **Don't want to code?** Run a [free car check](https://getfreecarcheck.co.uk) by reg at GetFreeCarCheck: MOT history,
> mileage, ULEZ, tax and recalls in seconds, no sign-up.

- **Zero runtime dependencies** in both languages (Python standard library; JavaScript `fetch`).
- **OAuth2 done for you**: client-credentials token fetched, cached for its 60 minutes and refreshed on 401.
- **Retries** on 429 and 5xx with `Retry-After` and exponential backoff; clear typed errors for everything else.
- **Typed models**: frozen dataclasses in Python, full `.d.ts` types in JavaScript.
- **Mileage checks**: readings in miles (kilometres converted), average miles a year, and a warning wherever the
  odometer went down between tests.
- **CLI**: `uk-mot-history AB12CDE` prints a readable history in your terminal.
- Runs on **Node 20+, Cloudflare Workers, Deno and Bun**.

Docs: **[behoss.github.io/uk-mot-history](https://behoss.github.io/uk-mot-history/)**

## Install

```bash
# Python 3.12+
uv add git+https://github.com/behoss/uk-mot-history
# or
pip install git+https://github.com/behoss/uk-mot-history
```

JavaScript / TypeScript: copy [`js/src/index.js`](js/src/index.js) and its types
[`js/src/index.d.ts`](js/src/index.d.ts) into your project, for example as `mot/index.js`. One file, no dependencies,
nothing to build.

## Quick start (Python)

```python
from uk_mot_history import MotHistoryClient, find_mileage_anomalies

client = MotHistoryClient.from_env()  # reads MOT_HISTORY_* variables
car = client.by_registration("AB12 CDE")  # or client.by_vin("WF0AXXGCDACB12345")

print(car.make, car.model, "MOT expires", car.mot_expiry)
for test in car.mot_tests:  # newest first
    print(test.completed_date.date(), test.test_result, test.odometer_miles, [d.text for d in test.failures])
for warning in find_mileage_anomalies(car):
    print("Clocking warning:", warning)
```

## Quick start (TypeScript / JavaScript)

```ts
import { MotHistoryClient, findMileageAnomalies, motExpiry } from "./mot/index.js";

const client = MotHistoryClient.fromEnv(env);      // Workers: pass env; Node: reads process.env
const car = await client.byRegistration("AB12CDE");
console.log(car.make, car.model, "MOT expires", motExpiry(car));
for (const a of findMileageAnomalies(car)) console.log(`Mileage fell ${a.drop} miles by ${a.later.date}`);
```

Create the client once at module level in a Worker: the token cache then lives for the isolate, and concurrent requests
share a single token request.

## CLI

```bash
export MOT_HISTORY_CLIENT_ID=... MOT_HISTORY_CLIENT_SECRET=... MOT_HISTORY_API_KEY=... MOT_HISTORY_TENANT_ID=...
uk-mot-history AB12CDE          # --vin for a VIN, --json for the raw response
```

```text
FORD FOCUS  (AB12CDE)
Silver | Petrol | 1596 cc | first used 2012-03-01
MOT expires: 2025-02-28 (valid)
Outstanding recall: No

2024-02-27  PASS  71,240 mi
            ADVISORY   Nearside Front Tyre worn close to legal limit/worn on edge (5.2.3 (e))
2023-02-20  PASS  58,410 mi
2022-02-24  FAIL  61,002 mi
            MAJOR      Offside Rear Brake pipe excessively corroded (1.1.11 (c))
            DANGEROUS  Nearside Front Suspension arm ball joint excessively worn (5.3.4 (a) (i))
2021-02-25  PASS  49,870 mi
            ADVISORY   Front Brake disc worn, pitted or scored, but not seriously weakened (1.1.14 (a) (ii))

WARNING: mileage went down by 2,592 miles: 61,002 on 2022-02-24 -> 58,410 on 2023-02-20 (possible clocking)
Average: 7,115 miles a year.
```

(Sample output from the test fixture; the registration is made up.)

## Get a DVSA API key

The MOT History API is free. DVSA issues keys to organisations, businesses and individuals.

1. Read DVSA's [registration page](https://documentation.history.mot.api.gov.uk/mot-history-api/register) and fill in
   the [MOT History API registration form](https://submit.forms.service.gov.uk/form/2382/register-for-mot-history-api/7519)
   (name, email, postal address).
2. Review takes up to five working days. DVSA emails you a **client ID**, **client secret**, **API key** and the
   **tenant ID** used in the token URL.
3. Put them in environment variables (never in code):

| Variable | From the DVSA email |
|---|---|
| `MOT_HISTORY_CLIENT_ID` | Client ID |
| `MOT_HISTORY_CLIENT_SECRET` | Client secret |
| `MOT_HISTORY_API_KEY` | API key (sent as `X-API-Key`) |
| `MOT_HISTORY_TENANT_ID` | Tenant ID in `https://login.microsoftonline.com/{tenantId}/oauth2/v2.0/token` |
| `MOT_HISTORY_TOKEN_URL` | Optional: the full token URL instead of the tenant ID |

Keys from the old MOT History API (the one without OAuth) do not work here: DVSA asks you to register again.

## API notes and gotchas

- **Two credentials on every call**: an OAuth2 bearer token (client credentials grant, scope
  `https://tapi.dvsa.gov.uk/.default`) **and** the `X-API-Key` header. Missing either gives 401/403.
- **Tokens last 60 minutes.** Cache them; requesting one per lookup is slow and counts against Microsoft's limits.
- **Rate limits**: 500,000 requests a day, 15 a second on average, bursts of 10. Over the daily quota, the key is blocked
  for 24 hours. The client backs off on 429, but cache results on your side (MOT data changes at most once a test).
- **Two response shapes**: a vehicle with tests has `motTests`; a car too new for its first MOT has no tests and a
  `motTestDueDate` instead. `car.mot_expiry` (Python) and `motExpiry(car)` (JS) handle both.
- **Odometer values are strings**, with `odometerUnit` of `MI` or `KM` and `odometerResultType` of `READ`,
  `UNREADABLE` or `NO_ODOMETER`. Use `odometer_miles` / `odometerMiles()` rather than the raw value.
- **Defect types**: `ADVISORY`, `MINOR`, `MAJOR`, `DANGEROUS`, plus `FAIL`, `PRS` and `USER ENTERED` on older records.
  A test can fail and pass again the same day (a retest): both appear in the history.
- **Mileage drops** are a classic clocking sign, but a typo by the tester or a replaced instrument cluster can cause them
  too. Treat `find_mileage_anomalies` as a flag to investigate.
- **Northern Ireland and heavy vehicles**: tests come with `dataSource` `DVA NI` or `CVS`; CVS tests carry a `location`.
- **Bulk data**: `client.bulk_download()` / `bulkDownload()` return short-lived links to the full extract and daily
  deltas. Download at once; the URLs expire.
- **Secrets expire.** `client.renew_client_secret(email)` asks DVSA for a new one.
- **Licence**: DVSA publishes the data under the Open Government Licence v3.0. Show "Contains public sector information
  licensed under the Open Government Licence v3.0." where you display it, and don't imply DVSA endorses your product.

Full reference: [DVSA MOT History API documentation](https://documentation.history.mot.api.gov.uk/).

## Open data: first-MOT fail rates by model

[`data/`](data/) holds first-MOT fail rates for 350 makes and models (7.3 million first MOTs, 2022–2024), built from
DVSA's open MOT data, each row linked to that model's
[reliability page](https://getfreecarcheck.co.uk/research/first-mot-fail-rates). OGL v3.0.

## Errors

| Python | JavaScript `error.kind` | When |
|---|---|---|
| `VehicleNotFound` | `not-found` | 404: no vehicle for that registration or VIN |
| `InvalidRequest` | `invalid` | 400: malformed registration or VIN |
| `AuthenticationError` | `auth` | Token refused, or 401/403 after a token refresh |
| `RateLimited` | `rate-limited` | Still 429 after every retry |
| `UpstreamError` | `upstream` | 5xx or network errors after every retry |
| `ConfigurationError` | `config` | Credentials missing |

All Python errors inherit from `MotHistoryError` and carry `.status` and `.error_code` (DVSA codes such as `MOTH-NF-01`).

## Development

```bash
uv sync && uv run ruff check . && uv run mypy && uv run pytest
cd js && npm install && npm run typecheck && npm test
```

Tests use recorded fixtures and a fake transport: no network, no key needed. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Related

- [GetFreeCarCheck](https://getfreecarcheck.co.uk): free UK car check by registration (MOT history, mileage, ULEZ, tax,
  recalls) and [car reliability by make and model](https://getfreecarcheck.co.uk/research/first-mot-fail-rates).

MIT licence. Made by [Bez](https://behoss.github.io). Not affiliated with or endorsed by DVSA.
