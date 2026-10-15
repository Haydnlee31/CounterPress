"""Inspect sustained-possession progression evidence from a public synthetic feed."""

import argparse
from pathlib import Path

from pydantic import TypeAdapter

from counterpress.domain.models import Event, ObservationWindow
from counterpress.domain.pressure import Publication
from counterpress.domain.progression import analyze_progression
from counterpress.fixture import load_fixture
from counterpress.replay import ReplaySession, parse_clock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--team", default="eastbridge")
    parser.add_argument("--windows", nargs=3, default=("48:00","53:00","58:00"))
    parser.add_argument("--at")
    parser.add_argument("--updates", type=Path)
    parser.add_argument("--publications", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        fixture = load_fixture(args.fixture)
        start, split, end = (parse_clock(t,fixture.initial_state.at.period) for t in args.windows)
        cutoff = parse_clock(args.at,fixture.initial_state.at.period) if args.at else end
        session = ReplaySession(fixture,end=max((end,cutoff),key=lambda t:t.key()))
        if args.updates:
            session.deliver(TypeAdapter(tuple[Event,...]).validate_json(args.updates.read_text()))
        receipts = TypeAdapter(tuple[Publication,...]).validate_json(args.publications.read_text()) if args.publications else ()
        evidence = analyze_progression(session,args.team,ObservationWindow(start=start,end=split),
            ObservationWindow(start=split,end=end),cutoff,publications=receipts)
        if args.json:
            print(evidence.model_dump_json(indent=2))
            return
        print(f"{evidence.match_id} | {args.team} | {evidence.rule_version}")
        for label,w in (("Baseline",evidence.baseline),("Current",evidence.current)):
            print(f"{label}: {w.without_progression_count}/{w.completed} without progression | "
                  f"boundary={len(w.boundary_excluded)}; unknown_start={len(w.left_censored)}; pending={len(w.pending)}; "
                  f"brief={len(w.brief_excluded)}; limited_space={len(w.limited_space)}")
        d=evidence.decisions[0]
        change="undefined" if d.change is None else f"{100*d.change:+.1f} pp"
        print(f"{d.status} ({d.direction}) | {change}")
        print(evidence.disclosure)
    except (OSError,ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
