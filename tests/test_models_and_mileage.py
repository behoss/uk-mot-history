from __future__ import annotations

from datetime import UTC, date, datetime

from conftest import load
from uk_mot_history import Vehicle, average_annual_miles, find_mileage_anomalies, mileage_readings
from uk_mot_history.models import MotTest, parse_datetime


def test_vehicle_parsing() -> None:
    v = Vehicle.from_api(load("vehicle.json"))
    assert (v.make, v.model, v.engine_size, v.first_used_date) == ("FORD", "FOCUS", 1596, date(2012, 3, 1))
    assert len(v.mot_tests) == 4
    latest = v.latest_test
    assert latest is not None and latest.passed and latest.odometer_miles == 71240
    assert latest.advisories[0].text.startswith("Nearside Front Tyre")
    failed = v.mot_tests[2]
    assert not failed.passed and len(failed.failures) == 2
    assert v.mot_expiry == date(2025, 2, 28)
    assert v.mot_valid_on(date(2025, 2, 28)) and not v.mot_valid_on(date(2025, 3, 1))


def test_new_registration_has_no_tests() -> None:
    v = Vehicle.from_api(load("new_reg.json"))
    assert v.mot_tests == () and v.manufacture_year == 2024
    assert v.mot_expiry == date(2027, 9, 1)
    assert find_mileage_anomalies(v) == [] and average_annual_miles(v) is None


def test_mileage_anomaly_found() -> None:
    v = Vehicle.from_api(load("vehicle.json"))
    assert [r.miles for r in mileage_readings(v)] == [49870, 61002, 58410, 71240]
    anomalies = find_mileage_anomalies(v)
    assert len(anomalies) == 1
    assert anomalies[0].drop == 2592
    assert "61,002 on 2022-02-24 -> 58,410 on 2023-02-20" in str(anomalies[0])
    assert find_mileage_anomalies(v, tolerance=5000) == []


def test_kilometres_are_converted() -> None:
    t = MotTest.from_api(
        {
            "completedDate": "2020-01-01T00:00:00Z",
            "testResult": "PASSED",
            "odometerValue": "16093",
            "odometerUnit": "KM",
            "odometerResultType": "READ",
        }
    )
    assert t.odometer_miles == 10000


def test_unreadable_odometer_is_skipped() -> None:
    t = MotTest.from_api({"completedDate": "2020-01-01", "testResult": "FAILED", "odometerResultType": "UNREADABLE"})
    assert t.odometer_miles is None


def test_old_date_format() -> None:
    assert parse_datetime("2013.11.14 09:10:23") == datetime(2013, 11, 14, 9, 10, 23, tzinfo=UTC)


def test_average_annual_miles() -> None:
    v = Vehicle.from_api(load("vehicle.json"))
    assert average_annual_miles(v) == 7115
