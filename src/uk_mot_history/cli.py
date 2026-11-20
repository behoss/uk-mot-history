"""`uk-mot-history AB12CDE`: print a vehicle's MOT history in the terminal."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date

from . import __version__
from .client import MotHistoryClient
from .errors import ConfigurationError, MotHistoryError, VehicleNotFound
from .mileage import average_annual_miles, find_mileage_anomalies
from .models import Vehicle

EPILOG = """\
credentials (from DVSA, see https://github.com/behoss/uk-mot-history#get-a-dvsa-api-key):
  MOT_HISTORY_CLIENT_ID, MOT_HISTORY_CLIENT_SECRET, MOT_HISTORY_API_KEY, MOT_HISTORY_TENANT_ID

No key yet? Run a free car check by reg at https://getfreecarcheck.co.uk
"""


def format_vehicle(vehicle: Vehicle, *, today: date | None = None) -> str:
    """A readable, plain-text MOT history."""
    today = today or date.today()
    lines: list[str] = []
    title = " ".join(p for p in (vehicle.make, vehicle.model) if p) or "Unknown vehicle"
    lines.append(f"{title}  ({vehicle.registration or '?'})")
    facts = [
        vehicle.primary_colour,
        vehicle.fuel_type,
        f"{vehicle.engine_size} cc" if vehicle.engine_size else None,
        f"first used {vehicle.first_used_date.isoformat()}" if vehicle.first_used_date else None,
    ]
    if any(facts):
        lines.append(" | ".join(f for f in facts if f))
    expiry = vehicle.mot_expiry
    if expiry:
        state = "valid" if vehicle.mot_valid_on(today) else "EXPIRED"
        label = "MOT expires" if vehicle.mot_tests else "First MOT due"
        lines.append(f"{label}: {expiry.isoformat()} ({state})")
    lines.append(f"Outstanding recall: {vehicle.has_outstanding_recall}")
    lines.append("")

    if not vehicle.mot_tests:
        lines.append("No MOT tests yet.")
    for test in vehicle.mot_tests:
        result = "PASS" if test.passed else "FAIL"
        miles = test.odometer_miles
        reading = f"{miles:,} mi" if miles is not None else test.odometer_result_type.lower().replace("_", " ")
        lines.append(f"{test.completed_date.date().isoformat()}  {result}  {reading}")
        for defect in test.defects:
            lines.append(f"            {defect.type:<10} {defect.text}")

    if vehicle.mot_tests:
        lines.append("")
        anomalies = find_mileage_anomalies(vehicle)
        if anomalies:
            for anomaly in anomalies:
                lines.append(f"WARNING: {anomaly} (possible clocking)")
        else:
            lines.append("Mileage: no drops between tests.")
        average = average_annual_miles(vehicle)
        if average is not None:
            lines.append(f"Average: {average:,} miles a year.")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="uk-mot-history",
        description="Look up a UK vehicle's MOT history (tests, mileage, defects) from the DVSA MOT History API.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("registration", help="registration (number plate), e.g. AB12CDE, or a VIN with --vin")
    parser.add_argument("--vin", action="store_true", help="treat the argument as a VIN")
    parser.add_argument("--json", action="store_true", help="print the raw API response as JSON")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    try:
        client = MotHistoryClient.from_env()
        vehicle = client.by_vin(args.registration) if args.vin else client.by_registration(args.registration)
    except ConfigurationError as err:
        print(f"uk-mot-history: {err}", file=sys.stderr)
        return 2
    except VehicleNotFound:
        print(f"uk-mot-history: no MOT record found for {args.registration}", file=sys.stderr)
        return 1
    except MotHistoryError as err:
        print(f"uk-mot-history: {err}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(vehicle.raw, indent=2))
    else:
        print(format_vehicle(vehicle))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
