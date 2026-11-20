"""Client for the DVSA MOT History API (https://history.mot.api.gov.uk).

Authentication is OAuth2 client credentials through Microsoft Entra ID plus an `X-API-Key` header. Access tokens last
60 minutes; the client caches one and refreshes it a minute before it expires, or at once if the API answers 401.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .errors import (
    AuthenticationError,
    ConfigurationError,
    InvalidRequest,
    MotHistoryError,
    RateLimited,
    UpstreamError,
    VehicleNotFound,
)
from .models import BulkDownload, Vehicle

API_BASE = "https://history.mot.api.gov.uk"
DEFAULT_SCOPE = "https://tapi.dvsa.gov.uk/.default"
TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
USER_AGENT = "uk-mot-history-python (+https://github.com/behoss/uk-mot-history)"

ENV_CLIENT_ID = "MOT_HISTORY_CLIENT_ID"
ENV_CLIENT_SECRET = "MOT_HISTORY_CLIENT_SECRET"
ENV_API_KEY = "MOT_HISTORY_API_KEY"
ENV_TENANT_ID = "MOT_HISTORY_TENANT_ID"
ENV_TOKEN_URL = "MOT_HISTORY_TOKEN_URL"
ENV_SCOPE = "MOT_HISTORY_SCOPE"

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True, slots=True)
class HttpRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes | None = None


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8")) if self.body else None


Transport = Callable[[HttpRequest, float], HttpResponse]
"""Sends one request with a timeout in seconds. Swap it out in tests, or to route through your own HTTP stack."""


def urllib_transport(request: HttpRequest, timeout: float) -> HttpResponse:
    """The default transport: the standard library, no extra dependencies."""
    req = urllib.request.Request(  # noqa: S310 (https URLs only)
        request.url, data=request.body, method=request.method, headers=dict(request.headers)
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:  # noqa: S310 (fixed https URLs)
            return HttpResponse(res.status, res.read(), {k.lower(): v for k, v in res.headers.items()})
    except urllib.error.HTTPError as err:
        return HttpResponse(err.code, err.read() or b"", {k.lower(): v for k, v in (err.headers or {}).items()})


_REG_CLEAN = re.compile(r"[^A-Z0-9]")


def normalise_registration(registration: str) -> str:
    """`ab12 cde` -> `AB12CDE`: upper case, spaces and punctuation removed."""
    return _REG_CLEAN.sub("", registration.upper())


class MotHistoryClient:
    """Look up MOT history by registration or VIN.

    >>> client = MotHistoryClient.from_env()          # doctest: +SKIP
    >>> vehicle = client.by_registration("AB12 CDE")  # doctest: +SKIP
    """

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        api_key: str,
        tenant_id: str | None = None,
        token_url: str | None = None,
        scope: str = DEFAULT_SCOPE,
        base_url: str = API_BASE,
        timeout: float = 10.0,
        max_retries: int = 3,
        backoff: float = 0.5,
        transport: Transport = urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not token_url:
            if not tenant_id:
                raise ConfigurationError("pass tenant_id (from your DVSA credentials email) or a full token_url")
            token_url = TOKEN_URL_TEMPLATE.format(tenant_id=tenant_id)
        missing = [
            n for n, v in (("client_id", client_id), ("client_secret", client_secret), ("api_key", api_key)) if not v
        ]
        if missing:
            raise ConfigurationError(f"missing credentials: {', '.join(missing)}")
        self._client_id = client_id
        self._client_secret = client_secret
        self._api_key = api_key
        self._token_url = token_url
        self._scope = scope
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff = backoff
        self._transport = transport
        self._sleep = sleep
        self._clock = clock
        self._token: tuple[str, float] | None = None
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None, **kwargs: Any) -> MotHistoryClient:
        """Build a client from MOT_HISTORY_CLIENT_ID, _CLIENT_SECRET, _API_KEY and _TENANT_ID (or _TOKEN_URL)."""
        env = os.environ if environ is None else environ
        missing = [n for n in (ENV_CLIENT_ID, ENV_CLIENT_SECRET, ENV_API_KEY) if not env.get(n)]
        if not env.get(ENV_TENANT_ID) and not env.get(ENV_TOKEN_URL):
            missing.append(ENV_TENANT_ID)
        if missing:
            raise ConfigurationError(f"set {', '.join(missing)} (see README: getting a DVSA key)")
        return cls(
            client_id=env[ENV_CLIENT_ID],
            client_secret=env[ENV_CLIENT_SECRET],
            api_key=env[ENV_API_KEY],
            tenant_id=env.get(ENV_TENANT_ID),
            token_url=env.get(ENV_TOKEN_URL),
            scope=env.get(ENV_SCOPE) or DEFAULT_SCOPE,
            **kwargs,
        )

    # Public API -------------------------------------------------------------------------------------------------------

    def by_registration(self, registration: str) -> Vehicle:
        """MOT history for a registration such as `AB12CDE` (spaces and case don't matter)."""
        reg = normalise_registration(registration)
        if not reg:
            raise InvalidRequest("empty registration")
        return Vehicle.from_api(self._get_json(f"/v1/trade/vehicles/registration/{urllib.parse.quote(reg)}"))

    def by_vin(self, vin: str) -> Vehicle:
        """MOT history for a vehicle identification number (usually 17 characters)."""
        clean = normalise_registration(vin)
        if not clean:
            raise InvalidRequest("empty VIN")
        return Vehicle.from_api(self._get_json(f"/v1/trade/vehicles/vin/{urllib.parse.quote(clean)}"))

    def bulk_download(self) -> BulkDownload:
        """Links to the bulk MOT history extract and the daily delta files."""
        return BulkDownload.from_api(self._get_json("/v1/trade/vehicles/bulk-download"))

    def renew_client_secret(self, email: str) -> str:
        """Ask DVSA for a new client secret (secrets expire). Returns the new secret; store it safely."""
        body = json.dumps({"awsApiKeyValue": self._api_key, "email": email}).encode()
        data = self._request("PUT", "/v1/trade/credentials", body=body)
        secret = data.get("clientSecret") if isinstance(data, dict) else None
        if not secret:
            raise UpstreamError("credentials endpoint returned no clientSecret")
        return str(secret)

    # Internals --------------------------------------------------------------------------------------------------------

    def _get_json(self, path: str) -> dict[str, Any]:
        data = self._request("GET", path)
        if not isinstance(data, dict):
            raise UpstreamError("unexpected response body")
        return data

    def access_token(self, *, force: bool = False) -> str:
        """A valid bearer token, cached until a minute before it expires."""
        with self._lock:
            now = self._clock()
            if not force and self._token and self._token[1] - 60 > now:
                return self._token[0]
            body = urllib.parse.urlencode(
                {
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": self._scope,
                }
            ).encode()
            req = HttpRequest(
                "POST",
                self._token_url,
                {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                    "User-Agent": USER_AGENT,
                },
                body,
            )
            res = self._send_with_retries(req)
            if res.status in (400, 401, 403):
                raise AuthenticationError(f"token request refused ({res.status})", status=res.status)
            if res.status != 200:
                raise UpstreamError(f"token request failed ({res.status})", status=res.status)
            payload = res.json() or {}
            token = payload.get("access_token")
            if not token:
                raise AuthenticationError("token response had no access_token")
            self._token = (str(token), now + float(payload.get("expires_in") or 3600))
            return self._token[0]

    def _send_with_retries(self, req: HttpRequest) -> HttpResponse:
        last: HttpResponse | None = None
        for attempt in range(self._max_retries + 1):
            try:
                res = self._transport(req, self._timeout)
            except (OSError, TimeoutError) as err:  # network error or timeout
                if attempt == self._max_retries:
                    raise UpstreamError(f"network error: {err}") from err
                self._sleep(self._backoff * 2.0**attempt)
                continue
            if res.status not in RETRY_STATUSES or attempt == self._max_retries:
                return res
            last = res
            self._sleep(self._retry_delay(res, attempt))
        assert last is not None
        return last

    def _retry_delay(self, res: HttpResponse, attempt: int) -> float:
        retry_after = res.headers.get("retry-after")
        if retry_after and retry_after.strip().isdigit():
            return min(float(retry_after), 30.0)
        return self._backoff * 2.0**attempt

    def _request(self, method: str, path: str, *, body: bytes | None = None) -> Any:
        refreshed = False
        while True:
            headers = {
                "Authorization": f"Bearer {self.access_token()}",
                "X-API-Key": self._api_key,
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            }
            if body is not None:
                headers["Content-Type"] = "application/json"
            res = self._send_with_retries(HttpRequest(method, f"{self._base_url}{path}", headers, body))
            if res.status == 401 and not refreshed:
                # The token was revoked or expired early: fetch a fresh one once.
                self.access_token(force=True)
                refreshed = True
                continue
            break
        if 200 <= res.status < 300:
            return res.json()
        raise _error_for(res)


def _error_for(res: HttpResponse) -> MotHistoryError:
    code = message = None
    try:
        data = res.json()
        if isinstance(data, dict):
            code = data.get("errorCode")
            message = data.get("errorMessage")
    except (ValueError, UnicodeDecodeError):
        pass
    text = f"{res.status}{f' {code}' if code else ''}: {message or 'MOT History API error'}"
    kinds: dict[int, type[MotHistoryError]] = {
        400: InvalidRequest,
        401: AuthenticationError,
        403: AuthenticationError,
        404: VehicleNotFound,
        429: RateLimited,
    }
    kind = kinds.get(res.status, UpstreamError)
    return kind(text, status=res.status, error_code=code)
