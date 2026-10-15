"""A conditional possession state machine with continuous ball/player state."""

from dataclasses import dataclass
from hashlib import sha256
import json
from random import Random

from counterpress.domain.models import (
    Actor, CarryDetails, DuelDetails, Event, EventReference, InitialState, MatchTime,
    PassDetails, PitchPosition, RecoveryDetails,
)
from counterpress.fixture import Pitch, PossessionFixture, Team
from counterpress.generator.models import END_MS, START_MS, VERSION, Evaluation, GeneratorConfig, PressureTrial

TEAMS = (
    Team(team_id="eastbridge", name="Eastbridge", player_ids=("eb04", "eb06", "eb08", "eb09")),
    Team(team_id="northport", name="Northport", player_ids=("np04", "np06", "np08")),
)


def encoded_feed(feed: PossessionFixture) -> str:
    return feed.model_dump_json(indent=2) + "\n"


@dataclass(frozen=True)
class GeneratedMatch:
    feed: PossessionFixture
    evaluation: Evaluation


def generate(config: GeneratorConfig) -> GeneratedMatch:
    # One local PRNG: reproducibility never depends on global random state or wall time.
    rng = Random(config.seed)
    identity = json.dumps({"version": VERSION, "config": config.model_dump(mode="json")}, sort_keys=True)
    match_id = "sim-" + sha256(identity.encode()).hexdigest()[:24]
    roster = {team.team_id: team.player_ids for team in TEAMS}
    holder = Actor(team_id="northport", player_id="np04")
    # Ball is held in a fixed Eastbridge-positive frame. Convert both axes for Northport.
    ball = (95.0, 34.0)
    elapsed = START_MS
    state = "controlled"
    cooldown = 0
    pending_actor = None
    pending_trial = None
    events: list[Event] = []
    trials: list[PressureTrial] = []

    def other(team):
        return "northport" if team == "eastbridge" else "eastbridge"

    def actor(team):
        return Actor(team_id=team, player_id=rng.choice(roster[team]))

    def relative(point, team):
        return point if team == "eastbridge" else (105 - point[0], 68 - point[1])

    def position(point, team):
        x, y = relative(point, team)
        return PitchPosition(x=round(x, 3), y=round(y, 3))

    def emit(who, action):
        index = len(events) + 1
        event = Event(match_id=match_id, event_id=f"g{index:04}", revision=1,
            source_delivery_sequence=index, occurrence_order=index,
            occurred_at=MatchTime(period=2, elapsed_ms=elapsed),
            available_at=MatchTime(period=2, elapsed_ms=elapsed + min(rng.randint(0, 300), END_MS - elapsed)),
            actor=who, position=position(ball, who.team_id), action=action)
        events.append(event)
        return EventReference(event_id=event.event_id, revision=1)

    # First observation records the initial holder and position without inventing a turnover.
    emit(holder, CarryDetails(kind="carry", end_position=position(ball, holder.team_id)))
    while elapsed < END_MS:
        delay = rng.randint(8, 14) if state == "restart" else rng.randint(1, 3) if state == "loose" else rng.randint(3, 7)
        # Do not squeeze a restart/recovery into the final second just to close the feed.
        # Unfinished possession/pressure episodes remain pending at the coverage boundary.
        if elapsed + delay * 1000 > END_MS:
            break
        elapsed += delay * 1000
        phase = next(phase for phase in reversed(config.phases) if phase.start_ms <= elapsed)
        if state != "controlled":
            ref = emit(pending_actor, RecoveryDetails(kind="recovery", from_team_id=holder.team_id,
                control="established", origin="restart" if state == "restart" else "open_play"))
            holder = pending_actor
            if pending_trial is not None:
                trials[pending_trial] = trials[pending_trial].model_copy(update={"outcome": "recovery", "resolution": ref})
            pending_actor = pending_trial = None
            state, cooldown = "controlled", 1
            continue

        own = getattr(phase, holder.team_id)
        defender = other(holder.team_id)
        opposition = getattr(phase, defender)
        x, y = relative(ball, holder.team_id)
        exposed = x <= 35  # A pressing challenge in the ball holder's defensive third.
        challenge_probability = (0.06 + 0.65 * opposition.pressure) if exposed else 0.035
        if cooldown == 0 and rng.random() < challenge_probability:
            challenger = actor(defender)
            loss_probability = max(0.04, min(0.85, 0.15 + 0.65 * opposition.pressure - 0.55 * own.escape_skill))
            lost = rng.random() < loss_probability
            ref = emit(holder, DuelDetails(kind="duel", opponent=challenger, outcome="lost" if lost else "won"))
            # Only pressure-exposed high challenges get evaluator labels. Other duels remain ordinary events.
            if exposed and opposition.pressure > 0:
                trials.append(PressureTrial(defending_team_id=defender, start=ref,
                    at=MatchTime(period=2, elapsed_ms=elapsed), pressure=opposition.pressure,
                    outcome="pending" if lost else "retained", resolution=None if lost else ref))
                pending_trial = len(trials) - 1 if lost else None
            if lost:
                pending_actor, state = challenger, "loose"
            cooldown = 1
            continue

        cooldown = max(0, cooldown - 1)
        flank_y = {"left": 12.0, "centre": 34.0, "right": 56.0}[own.flank]
        is_pass = rng.random() < 0.72
        dx = rng.uniform(-8, 12 + 26 * own.directness) if is_pass else rng.uniform(2, 10 + 6 * own.directness)
        target_x = round(max(0, min(105, x + dx)), 3)
        target_y = round(max(0, min(68, y + (flank_y - y) * 0.35 + rng.uniform(-9, 9))), 3)
        end = PitchPosition(x=target_x, y=target_y)
        if is_pass:
            completion = min(0.98, 0.86 + 0.12 * own.escape_skill - 0.22 * own.directness
                             - (0.25 * opposition.pressure if exposed else 0))
            completed = target_x < 103 and rng.random() < completion
            recipient = Actor(team_id=holder.team_id, player_id=rng.choice(
                tuple(player for player in roster[holder.team_id] if player != holder.player_id))) if completed else None
            restart = not completed and (target_x >= 103 or rng.random() < 0.25)
            if restart:
                end = PitchPosition(x=105.0, y=target_y) if target_x >= 103 else PitchPosition(x=target_x, y=rng.choice((0.0, 68.0)))
            emit(holder, PassDetails(kind="pass", outcome="completed" if completed else "incomplete", end_position=end, recipient=recipient))
            ball = relative((end.x, end.y), holder.team_id)
            if completed:
                holder = recipient
            else:
                pending_actor, state = actor(defender), "restart" if restart else "loose"
        else:
            # Keep carries inside the pitch; a subsequent overhit pass can lead to a restart.
            end = PitchPosition(x=min(end.x, 102.0), y=max(1.0, min(end.y, 67.0)))
            emit(holder, CarryDetails(kind="carry", end_position=end))
            ball = relative((end.x, end.y), holder.team_id)

    feed = PossessionFixture(schema_version="1.0", synthetic=True, match_id=match_id,
        pitch=Pitch(length_m=105, width_m=68, coordinates="actor_team_attacks_positive_x"), teams=TEAMS,
        initial_state=InitialState(at=MatchTime(period=2, elapsed_ms=START_MS),
            score={"eastbridge": 0, "northport": 1}, controlled_possession_team_id="northport"), events=tuple(events))
    audit = Evaluation(match_id=match_id, config=config, feed_sha256=sha256(encoded_feed(feed).encode()).hexdigest(),
                       pressure_trials=tuple(trials), end_state=state)
    return GeneratedMatch(feed=feed, evaluation=audit)
