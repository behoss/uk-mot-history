from __future__ import annotations

from datetime import date

import pytest

from conftest import load
from uk_mot_history import Vehicle, cli


def test_format_vehicle() -> None:
    text = cli.format_vehicle(Vehicle.from_api(load("vehicle.json")), today=date(2024, 6, 1))
    assert text.splitlines()[0] == "FORD FOCUS  (AB12CDE)"
    assert "MOT expires: 2025-02-28 (valid)" in text
    assert "2022-02-24  FAIL  61,002 mi" in text
    assert "DANGEROUS  Nearside Front Suspension arm ball joint" in text
    assert "WARNING: mileage went down by 2,592 miles" in text


def test_format_new_vehicle() -> None:
    text = cli.format_vehicle(Vehicle.from_api(load("new_reg.json")), today=date(2026, 1, 1))
    assert "First MOT due: 2027-09-01 (valid)" in text and "No MOT tests yet." in text


def test_cli_without_credentials(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    for name in ("MOT_HISTORY_CLIENT_ID", "MOT_HISTORY_CLIENT_SECRET", "MOT_HISTORY_API_KEY", "MOT_HISTORY_TENANT_ID"):
        monkeypatch.delenv(name, raising=False)
    assert cli.main(["AB12CDE"]) == 2
    assert "MOT_HISTORY_CLIENT_ID" in capsys.readouterr().err
