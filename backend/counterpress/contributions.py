"""Inspect a player's recorded share of team high recoveries from a synthetic feed."""

import argparse
from pathlib import Path

from pydantic import TypeAdapter

from counterpress.domain.contributions import analyze_contributions
from counterpress.domain.models import Event, ObservationWindow
from counterpress.fixture import load_fixture
from counterpress.replay import ReplaySession, parse_clock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--team", default="eastbridge")
    parser.add_argument("--player", required=True)
    parser.add_argument("--windows", nargs=3, default=("48:00", "53:00", "58:00"))
    parser.add_argument("--at")
    parser.add_argument("--updates", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        fixture = load_fixture(args.fixture)
        start, split, end = (parse_clock(t, fixture.initial_state.at.period) for t in args.windows)
        cutoff = parse_clock(args.at, fixture.initial_state.at.period) if args.at else end
        session = ReplaySession(fixture, end=max((end, cutoff), key=lambda t: t.key()))
        if args.updates:
            session.deliver(TypeAdapter(tuple[Event, ...]).validate_json(args.updates.read_text()))
        evidence = analyze_contributions(session, args.team, args.player,
            ObservationWindow(start=start, end=split), ObservationWindow(start=split, end=end), cutoff)
        if args.json:
            print(evidence.model_dump_json(indent=2))
            return
        print(f"{evidence.match_id} | {args.team}/{args.player} | {evidence.rule_version}")
        for label, window in (("Baseline", evidence.baseline), ("Current", evidence.current)):
            share = "undefined" if window.share is None else f"{window.share:.1%}"
            print(f"{label}: {window.player_count}/{window.team_count} team high recoveries | share={share}")
        decision = evidence.decision
        delta = "undefined" if decision.share_change is None else f"{100*decision.share_change:+.1f} pp"
        print(f"{decision.status} | player count {decision.count_change:+d} | share {delta}")
        print(evidence.disclosure)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
