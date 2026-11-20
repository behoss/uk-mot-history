from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from uk_mot_history.client import HttpRequest, HttpResponse, MotHistoryClient

FIXTURES = Path(__file__).parent / "fixtures"
TOKEN_URL = "https://login.example.test/tenant/oauth2/v2.0/token"


def load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text())
    return data


class FakeTransport:
    """Answers token requests with a fake token and API requests from a queue of (status, body) pairs."""

    def __init__(self, responses: list[tuple[int, Any]] | None = None, token_status: int = 200) -> None:
        self.responses = list(responses or [])
        self.token_status = token_status
        self.requests: list[HttpRequest] = []
        self.token_calls = 0

    def __call__(self, request: HttpRequest, timeout: float) -> HttpResponse:
        self.requests.append(request)
        if request.url == TOKEN_URL:
            self.token_calls += 1
            body = {"access_token": f"fake-token-{self.token_calls}", "expires_in": 3599}
            return HttpResponse(self.token_status, json.dumps(body).encode())
        status, body = self.responses.pop(0)
        headers = {"retry-after": "1"} if status == 429 else {}
        return HttpResponse(status, json.dumps(body).encode() if body is not None else b"", headers)


@pytest.fixture
def make_client() -> Callable[..., tuple[MotHistoryClient, FakeTransport, list[float]]]:
    def factory(
        responses: list[tuple[int, Any]] | None = None, **kwargs: Any
    ) -> tuple[MotHistoryClient, FakeTransport, list[float]]:
        transport = FakeTransport(responses, token_status=kwargs.pop("token_status", 200))
        sleeps: list[float] = []
        client = MotHistoryClient(
            client_id="test-client",
            client_secret="test-secret",
            api_key="test-api-key",
            token_url=TOKEN_URL,
            transport=transport,
            sleep=sleeps.append,
            **kwargs,
        )
        return client, transport, sleeps

    return factory
