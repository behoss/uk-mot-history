from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from conftest import FakeTransport, load
from uk_mot_history import (
    AuthenticationError,
    ConfigurationError,
    InvalidRequest,
    MotHistoryClient,
    RateLimited,
    UpstreamError,
    VehicleNotFound,
)

Factory = Callable[..., tuple[MotHistoryClient, FakeTransport, list[float]]]


def test_by_registration_sends_auth_headers_and_normalises(make_client: Factory) -> None:
    client, transport, _ = make_client([(200, load("vehicle.json"))])
    vehicle = client.by_registration("ab12 cde")
    assert vehicle.registration == "AB12CDE"
    api = transport.requests[-1]
    assert api.url == "https://history.mot.api.gov.uk/v1/trade/vehicles/registration/AB12CDE"
    assert api.headers["Authorization"] == "Bearer fake-token-1"
    assert api.headers["X-API-Key"] == "test-api-key"
    token = transport.requests[0]
    assert token.body is not None and b"grant_type=client_credentials" in token.body
    assert b"scope=https%3A%2F%2Ftapi.dvsa.gov.uk%2F.default" in token.body


def test_by_vin(make_client: Factory) -> None:
    client, transport, _ = make_client([(200, load("vehicle.json"))])
    client.by_vin("wf0axxgcdacb12345")
    assert transport.requests[-1].url.endswith("/v1/trade/vehicles/vin/WF0AXXGCDACB12345")


def test_token_is_cached(make_client: Factory) -> None:
    client, transport, _ = make_client([(200, load("vehicle.json")), (200, load("new_reg.json"))])
    client.by_registration("AB12CDE")
    client.by_registration("XY74ZZZ")
    assert transport.token_calls == 1


def test_token_refreshed_when_expired(make_client: Factory) -> None:
    now = [1000.0]
    client, transport, _ = make_client([(200, load("vehicle.json")), (200, load("vehicle.json"))], clock=lambda: now[0])
    client.by_registration("AB12CDE")
    now[0] += 3600
    client.by_registration("AB12CDE")
    assert transport.token_calls == 2


def test_401_refreshes_token_once(make_client: Factory) -> None:
    client, transport, _ = make_client([(401, None), (200, load("vehicle.json"))])
    assert client.by_registration("AB12CDE").make == "FORD"
    assert transport.token_calls == 2


def test_retries_429_then_succeeds(make_client: Factory) -> None:
    client, _, sleeps = make_client([(429, None), (503, None), (200, load("vehicle.json"))])
    assert client.by_registration("AB12CDE").model == "FOCUS"
    assert sleeps == [1.0, 1.0]  # Retry-After honoured, then 0.5 * 2**1


def test_gives_up_after_retries(make_client: Factory) -> None:
    client, _, sleeps = make_client([(429, None)] * 4)
    with pytest.raises(RateLimited):
        client.by_registration("AB12CDE")
    assert len(sleeps) == 3


def test_5xx_becomes_upstream_error(make_client: Factory) -> None:
    client, _, _ = make_client([(500, None)] * 4)
    with pytest.raises(UpstreamError):
        client.by_registration("AB12CDE")


@pytest.mark.parametrize(
    ("status", "error"),
    [(404, VehicleNotFound), (400, InvalidRequest), (403, AuthenticationError)],
)
def test_error_mapping(make_client: Factory, status: int, error: type[Exception]) -> None:
    body: dict[str, Any] = {"errorCode": "MOTH-NF-01", "errorMessage": "No data found", "requestId": "1"}
    client, _, _ = make_client([(status, body)])
    with pytest.raises(error) as info:
        client.by_registration("ZZ99ZZZ")
    assert "No data found" in str(info.value)


def test_network_errors_are_retried(make_client: Factory) -> None:
    client, transport, sleeps = make_client()
    calls = {"n": 0}

    def flaky(request: Any, timeout: float) -> Any:
        if request.url.endswith("token"):
            return transport(request, timeout)
        calls["n"] += 1
        raise TimeoutError("slow")

    client._transport = flaky
    with pytest.raises(UpstreamError):
        client.by_registration("AB12CDE")
    assert calls["n"] == 4 and len(sleeps) == 3


def test_bad_credentials(make_client: Factory) -> None:
    client, _, _ = make_client(token_status=401)
    with pytest.raises(AuthenticationError):
        client.by_registration("AB12CDE")


def test_bulk_download(make_client: Factory) -> None:
    body = {
        "bulk": [
            {
                "filename": "bulk.zip",
                "downloadUrl": "https://example.test/b",
                "fileSize": 123,
                "fileCreatedOn": "2026-11-01",
            }
        ],
        "delta": [],
    }
    client, _, _ = make_client([(200, body)])
    files = client.bulk_download()
    assert files.bulk[0].file_size == 123 and files.delta == ()


def test_from_env() -> None:
    with pytest.raises(ConfigurationError) as info:
        MotHistoryClient.from_env({"MOT_HISTORY_CLIENT_ID": "x"})
    assert "MOT_HISTORY_API_KEY" in str(info.value)
    client = MotHistoryClient.from_env(
        {
            "MOT_HISTORY_CLIENT_ID": "id",
            "MOT_HISTORY_CLIENT_SECRET": "secret",
            "MOT_HISTORY_API_KEY": "key",
            "MOT_HISTORY_TENANT_ID": "tenant",
        }
    )
    assert client._token_url == "https://login.microsoftonline.com/tenant/oauth2/v2.0/token"


def test_empty_registration(make_client: Factory) -> None:
    client, _, _ = make_client()
    with pytest.raises(InvalidRequest):
        client.by_registration(" - ")
