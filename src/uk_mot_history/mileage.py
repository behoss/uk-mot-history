"""Mileage helpers: the odometer timeline and clocking warnings.

A reading that goes down between two MOT tests is the classic sign of a clocked (wound-back) odometer. It can also be a
tester's typo or a replaced instrument cluster, so treat it as a warning to investigate, not proof.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .models import MotTest, Vehicle


@dataclass(frozen=True, slots=True)
class MileageReading:
    date: date
    miles: int
    test: MotTest


@dataclass(frozen=True, slots=True)
class MileageAnomaly:
    """A later test recorded fewer miles than an earlier one."""

    earlier: MileageReading
    later: MileageReading

    @property
    def drop(self) -> int:
        return self.earlier.miles - self.later.miles

    def __str__(self) -> str:
        return (
            f"mileage went down by {self.drop:,} miles: {self.earlier.miles:,} on {self.earlier.date.isoformat()}"
            f" -> {self.later.miles:,} on {self.later.date.isoformat()}"
        )


def mileage_readings(vehicle: Vehicle) -> list[MileageReading]:
    """Every readable odometer reading in miles, oldest first."""
    readings = [
        MileageReading(t.completed_date.date(), miles, t)
        for t in vehicle.mot_tests
        if (miles := t.odometer_miles) is not None
    ]
    readings.sort(key=lambda r: r.test.completed_date)
    return readings


def find_mileage_anomalies(vehicle: Vehicle, *, tolerance: int = 0) -> list[MileageAnomaly]:
    """Each point where the odometer went down by more than `tolerance` miles against the highest earlier reading.

    Comparing with the highest earlier reading (not just the previous one) catches a wind-back that is followed by
    normal-looking growth.
    """
    anomalies: list[MileageAnomaly] = []
    peak: MileageReading | None = None
    for reading in mileage_readings(vehicle):
        if peak is not None and peak.miles - reading.miles > tolerance:
            anomalies.append(MileageAnomaly(peak, reading))
        if peak is None or reading.miles > peak.miles:
            peak = reading
    return anomalies


def average_annual_miles(vehicle: Vehicle) -> int | None:
    """Average miles a year between the first and last readings (None with fewer than two readings a year apart)."""
    readings = mileage_readings(vehicle)
    if len(readings) < 2:
        return None
    first, last = readings[0], readings[-1]
    days = (last.date - first.date).days
    if days < 365:
        return None
    return round((last.miles - first.miles) / days * 365.25)
