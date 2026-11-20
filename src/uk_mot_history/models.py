"""Typed records for MOT History API responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

KM_PER_MILE = 1.609344


def _str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_date(value: Any) -> date | None:
    """Parse `YYYY-MM-DD` (or the older `YYYY.MM.DD`) into a date; anything else gives None."""
    text = _str(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text[:10].replace(".", "-"))
    except ValueError:
        return None


def parse_datetime(value: Any) -> datetime | None:
    """Parse an ISO 8601 timestamp such as `2024-02-27T11:42:10.000Z`."""
    text = _str(value)
    if text is None:
        return None
    # Older records used `2013.11.14 09:10:23`.
    if text[4:5] == ".":
        text = text.replace(".", "-", 2)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        day = parse_date(text)
        if day is None:
            return None
        parsed = datetime(day.year, day.month, day.day)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_int(value: Any) -> int | None:
    text = _str(value)
    if text is None:
        return None
    digits = text.replace(",", "")
    return int(digits) if digits.isdigit() else None


@dataclass(frozen=True, slots=True)
class Defect:
    """One item the tester recorded: ADVISORY, MINOR, MAJOR, DANGEROUS, FAIL, PRS or USER ENTERED."""

    text: str
    type: str
    dangerous: bool = False

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Defect:
        return cls(
            text=_str(data.get("text")) or "",
            type=(_str(data.get("type")) or "UNKNOWN").upper(),
            dangerous=bool(data.get("dangerous")),
        )

    @property
    def is_failure(self) -> bool:
        """True for items that fail the test on their own (MAJOR, DANGEROUS, or FAIL on older records)."""
        return self.type in {"MAJOR", "DANGEROUS", "FAIL"} or self.dangerous


@dataclass(frozen=True, slots=True)
class MotTest:
    """One MOT (or annual) test."""

    completed_date: datetime
    test_result: str
    odometer_result_type: str
    expiry_date: date | None = None
    odometer_value: int | None = None
    odometer_unit: str | None = None
    mot_test_number: str | None = None
    data_source: str | None = None
    registration_at_time_of_test: str | None = None
    location: str | None = None
    defects: tuple[Defect, ...] = ()

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> MotTest:
        completed = parse_datetime(data.get("completedDate"))
        if completed is None:
            raise ValueError(f"MOT test without a valid completedDate: {data.get('completedDate')!r}")
        return cls(
            completed_date=completed,
            test_result=(_str(data.get("testResult")) or "UNKNOWN").upper(),
            odometer_result_type=(_str(data.get("odometerResultType")) or "UNKNOWN").upper(),
            expiry_date=parse_date(data.get("expiryDate")),
            odometer_value=parse_int(data.get("odometerValue")),
            odometer_unit=(_str(data.get("odometerUnit")) or "").upper() or None,
            mot_test_number=_str(data.get("motTestNumber")),
            data_source=_str(data.get("dataSource")),
            registration_at_time_of_test=_str(data.get("registrationAtTimeOfTest")),
            location=_str(data.get("location")),
            defects=tuple(Defect.from_api(d) for d in data.get("defects") or [] if isinstance(d, dict)),
        )

    @property
    def passed(self) -> bool:
        return self.test_result == "PASSED"

    @property
    def odometer_miles(self) -> int | None:
        """The reading in miles (kilometres converted), or None when it was not read."""
        if self.odometer_result_type != "READ" or self.odometer_value is None:
            return None
        if self.odometer_unit == "KM":
            return round(self.odometer_value / KM_PER_MILE)
        return self.odometer_value

    @property
    def advisories(self) -> tuple[Defect, ...]:
        return tuple(d for d in self.defects if d.type == "ADVISORY")

    @property
    def failures(self) -> tuple[Defect, ...]:
        return tuple(d for d in self.defects if d.is_failure)


@dataclass(frozen=True, slots=True)
class Vehicle:
    """A vehicle and its MOT history, newest test first (as the API returns it)."""

    registration: str | None
    make: str | None = None
    model: str | None = None
    first_used_date: date | None = None
    registration_date: date | None = None
    manufacture_date: date | None = None
    manufacture_year: int | None = None
    fuel_type: str | None = None
    primary_colour: str | None = None
    engine_size: int | None = None
    has_outstanding_recall: str = "Unknown"
    mot_test_due_date: date | None = None
    mot_tests: tuple[MotTest, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Vehicle:
        tests = [MotTest.from_api(t) for t in data.get("motTests") or [] if isinstance(t, dict)]
        tests.sort(key=lambda t: t.completed_date, reverse=True)
        return cls(
            registration=_str(data.get("registration")),
            make=_str(data.get("make")),
            model=_str(data.get("model")),
            first_used_date=parse_date(data.get("firstUsedDate")),
            registration_date=parse_date(data.get("registrationDate")),
            manufacture_date=parse_date(data.get("manufactureDate")),
            manufacture_year=parse_int(data.get("manufactureYear")),
            fuel_type=_str(data.get("fuelType")),
            primary_colour=_str(data.get("primaryColour")),
            engine_size=parse_int(data.get("engineSize")),
            has_outstanding_recall=_str(data.get("hasOutstandingRecall")) or "Unknown",
            mot_test_due_date=parse_date(data.get("motTestDueDate")),
            mot_tests=tuple(tests),
            raw=data,
        )

    @property
    def latest_test(self) -> MotTest | None:
        return self.mot_tests[0] if self.mot_tests else None

    @property
    def mot_expiry(self) -> date | None:
        """Expiry of the latest passed test; for a car too new for its first MOT, the first test due date."""
        for test in self.mot_tests:
            if test.passed and test.expiry_date:
                return test.expiry_date
        return self.mot_test_due_date

    def mot_valid_on(self, day: date) -> bool:
        expiry = self.mot_expiry
        return expiry is not None and day <= expiry


@dataclass(frozen=True, slots=True)
class BulkFile:
    filename: str
    download_url: str
    file_size: int | None = None
    file_created_on: date | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> BulkFile:
        return cls(
            filename=_str(data.get("filename")) or "",
            download_url=_str(data.get("downloadUrl")) or "",
            file_size=parse_int(data.get("fileSize")),
            file_created_on=parse_date(data.get("fileCreatedOn")),
        )


@dataclass(frozen=True, slots=True)
class BulkDownload:
    """Links to the full bulk extract and the daily delta files. Download URLs expire quickly: use them at once."""

    bulk: tuple[BulkFile, ...]
    delta: tuple[BulkFile, ...]

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> BulkDownload:
        return cls(
            bulk=tuple(BulkFile.from_api(f) for f in data.get("bulk") or []),
            delta=tuple(BulkFile.from_api(f) for f in data.get("delta") or []),
        )
