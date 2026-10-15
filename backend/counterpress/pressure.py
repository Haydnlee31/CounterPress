"""Inspect observed build-up episodes and pressure-proxy evidence from a public feed."""

import argparse
from pathlib import Path

from pydantic import TypeAdapter

from counterpress.domain.models import Event, ObservationWindow
from counterpress.domain.pressure import Publication, analyze_pressure
from counterpress.fixture import load_fixture
from counterpress.replay import ReplaySession, parse_clock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--team", default="eastbridge")
    parser.add_argument("--windows", nargs=3, default=("48:00", "53:00", "58:00"))
    parser.add_argument("--at", help="availability cutoff MM:SS; defaults to window end")
    parser.add_argument("--updates", type=Path, help="source revision array")
    parser.add_argument("--publications", type=Path, help="prior Publication receipts for cooldowns")
    parser.add_argument("--json", action="store_true", help="full typed evidence including source records")
    args = parser.parse_args()
    try:
        fixture = load_fixture(args.fixture)
        period = fixture.initial_state.at.period
        start, split, end = (parse_clock(value, period) for value in args.windows)
        cutoff = parse_clock(args.at, period) if args.at else end
        session = ReplaySession(fixture, end=max((end, cutoff), key=lambda time: time.key()))
        if args.updates:
            session.deliver(TypeAdapter(tuple[Event, ...]).validate_json(args.updates.read_text()))
        publications = TypeAdapter(tuple[Publication, ...]).validate_json(args.publications.read_text()) if args.publications else ()
        result = analyze_pressure(session, args.team, ObservationWindow(start=start, end=split),
                                  ObservationWindow(start=split, end=end), cutoff, publications=publications)
        if args.json:
            print(result.model_dump_json(indent=2))
        else:
            print(f"{result.match_id} | {args.team} | {result.rule_version}")
            for label, window in (("Baseline", result.baseline), ("Current", result.current)):
                print(f"{label}: completed={window.completed}; exposed={window.exposed}; escaped_under_pressure={window.escaped_under_pressure}; "
                      f"boundary_excluded={len(window.boundary_excluded)}; left_censored={len(window.left_censored)}; pending={len(window.pending)}")
            for decision in result.decisions:
                delta = "undefined" if decision.change is None else f"{decision.change * 100:+.1f} pp"
                print(f"{decision.metric}: {decision.baseline_numerator}/{decision.baseline_denominator} -> "
                      f"{decision.current_numerator}/{decision.current_denominator} | {delta} | {decision.status} ({decision.direction})")
            print(f"Evidence SHA-256: {result.fingerprint}")
            print(result.disclosure)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
