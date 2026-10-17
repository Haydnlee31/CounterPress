"""Local replay session and console comparison report."""

import argparse
from fractions import Fraction
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from counterpress.clock import VirtualClock
from counterpress.domain.metrics import RecoveryComparison, TeamMetrics, compare_recoveries, team_metrics
from counterpress.domain.models import Contract, DuelDetails, Event, MatchState, MatchTime, ObservationWindow, PassDetails, ShotDetails
from counterpress.domain.replay import EventJournal, reduce_state
from counterpress.fixture import PossessionFixture, load_fixture


class ReplaySnapshot(Contract):
    state: MatchState
    metrics: tuple[TeamMetrics, ...]
    events: tuple[Event, ...]


class ReplaySession:
    def __init__(self, fixture: PossessionFixture, *, end: MatchTime | None = None, speed: float = 1):
        self.fixture = fixture
        self.journal = EventJournal(fixture.match_id, fixture.events)
        last = max((event.available_at for event in fixture.events), key=lambda time: time.key())
        self.clock = VirtualClock(fixture.initial_state.at, end or last, speed)

    def deliver(self, records: tuple[Event, ...]) -> None:
        """Append revisions/late records; snapshots rebuild at their availability cutoff."""
        rosters = {team.team_id: set(team.player_ids) for team in self.fixture.teams}
        for event in records:
            if event.occurred_at.key() < self.fixture.initial_state.at.key():
                raise ValueError("event predates the declared initial state")
            actors = [event.actor]
            if isinstance(event.action, PassDetails) and event.action.recipient:
                actors.append(event.action.recipient)
            if isinstance(event.action, ShotDetails) and event.action.goalkeeper:
                actors.append(event.action.goalkeeper)
            if isinstance(event.action, DuelDetails):
                actors.append(event.action.opponent)
            if any(actor.player_id not in rosters.get(actor.team_id, set()) for actor in actors):
                raise ValueError("record contains an unregistered actor")
        self.journal.append(records)

    def snapshot(self, cutoff: MatchTime | None = None) -> ReplaySnapshot:
        at = cutoff or self.clock.now
        if not self.clock.start.key() <= at.key() <= self.clock.end.key():
            raise ValueError("snapshot cutoff is outside the declared replay interval")
        events = self.journal.events_at(at)
        state = reduce_state(self.fixture.initial_state, self.fixture.match_id, events, at, self.journal.cursor_at(at))
        return ReplaySnapshot(state=state, events=events,
                              metrics=tuple(team_metrics(events, team.team_id) for team in self.fixture.teams))

    def comparison(self, team_id: str, baseline: ObservationWindow, current: ObservationWindow) -> RecoveryComparison:
        if team_id not in self.fixture.initial_state.score:
            raise ValueError("unknown comparison team")
        if baseline.start.key() < self.clock.start.key():
            raise ValueError("comparison begins before the available match history")
        snapshot = self.snapshot()
        return compare_recoveries(snapshot.events, team_id, baseline, current, snapshot.state.at)


def display_time(time: MatchTime) -> str:
    seconds = time.elapsed_ms // 1000
    return f"{(45 if time.period == 2 else 0) + seconds // 60:02}:{seconds % 60:02}"


def parse_clock(value: str, period: int) -> MatchTime:
    try:
        minutes, seconds = map(int, value.split(":"))
    except ValueError as exc:
        raise ValueError("clock must use MM:SS") from exc
    offset = 45 if period == 2 else 0
    if not 0 <= seconds < 60 or minutes < offset:
        raise ValueError("clock is outside the selected period")
    return MatchTime(period=period, elapsed_ms=((minutes - offset) * 60 + seconds) * 1000)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--speed", type=float, default=1, help="virtual playback speed; no real-time sleeping")
    parser.add_argument("--at", help="stop/report at MM:SS, e.g. 54:00")
    parser.add_argument("--windows", nargs=3, default=["48:00", "53:00", "58:00"], metavar=("START", "SPLIT", "END"))
    parser.add_argument("--team", default="eastbridge")
    parser.add_argument("--updates", type=Path, help="JSON array of additional Event deliveries")
    args = parser.parse_args()
    try:
        fixture = load_fixture(args.fixture)
        period = fixture.initial_state.at.period
        start, split, end = (parse_clock(value, period) for value in args.windows)
        baseline = ObservationWindow(start=start, end=split)
        current = ObservationWindow(start=split, end=end)
        at = parse_clock(args.at, period) if args.at else end
        if not fixture.initial_state.at.key() <= start.key() or not fixture.initial_state.at.key() <= at.key() <= end.key():
            raise ValueError("requested windows/cutoff are outside replay history")
        if args.team not in fixture.initial_state.score:
            raise ValueError("unknown comparison team")
        session = ReplaySession(fixture, end=end, speed=args.speed)
        if args.updates:
            session.deliver(TypeAdapter(tuple[Event, ...]).validate_json(args.updates.read_text()))
        session.clock.play()
        session.clock.advance(Fraction(at.elapsed_ms - session.clock.start.elapsed_ms, 1000) / session.clock.speed)
        session.clock.pause()
        snapshot = session.snapshot()
        print(f"{fixture.match_id} | {display_time(snapshot.state.at)} | {len(snapshot.events)} canonical events")
        print("Score: " + ", ".join(f"{team.name} {snapshot.state.score[team.team_id]}" for team in fixture.teams)
              + f" | Possession: {snapshot.state.controlled_possession_team_id}")
        for metrics in snapshot.metrics:
            print(f"{metrics.team_id}: passes {metrics.pass_completions}/{metrics.pass_attempts} | "
                  f"attempted pass distance {metrics.attempted_pass_distance_m:.2f} m | "
                  f"high recoveries {len(metrics.high_recoveries)}")
        if at.key() < end.key():
            print(f"Comparison not ready: current window ends at {display_time(end)}.")
        else:
            comparison = session.comparison(args.team, baseline, current)
            for name, observation in (("Baseline", comparison.baseline), ("Current", comparison.current)):
                ids = ", ".join(f"{ref.event_id}@r{ref.revision}" for ref in observation.source_events) or "none"
                print(f"{name} ({display_time(observation.window.start)}, {display_time(observation.window.end)}]: "
                      f"{observation.value} | {ids}")
            print(f"Count increase: {'yes' if comparison.increased else 'no'} (location/count fact only)")
    except (OSError, ValueError, ValidationError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
