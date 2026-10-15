# Seeded procedural generator — Stage 8, first increment

The generator creates a fictional 48:00–58:00 segment using the existing Event
and PossessionFixture contracts. A local seeded random generator drives a
conditional possession state machine. The same configuration and generator
version reproduce the same feed, identifiers and evaluator records in the
project's pinned environment. No model request or Azure resource is involved.

## Run and replay

From the repository root, after the README's local setup:

```sh
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.generator --seed 2 --profile pressure-shift --output var/my-generated-match
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.replay var/my-generated-match/feeds/sim-cd3f34e3015e1cec5197fe8c.json
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.generator --suite --output var/my-generated-suite
```

Exports require a new directory and refuse to overwrite an existing one. Files
are staged before publishing the bundle; duplicate configurations across splits
fail instead of overwriting a match. Generated artifacts live under ignored
`var/`; source configuration, tests and independent expectations live in code.

Available profiles are `steady`, `pressure-shift` and `directness-shift`. The
default is seed 7 with `pressure-shift`. Both shift profiles change Eastbridge's
settings at 53:00. The pressure profile changes only pressure, from 0.2 to 0.85;
the directness profile changes directness from 0.4 to 0.8 and flank from centre
to left. Profiles specify inputs, not guaranteed outcomes.

For custom settings, copy the `config` object from an evaluator JSON file into a
separate private JSON file and use:

```sh
UV_CACHE_DIR=.uv-cache uv run --frozen python -m counterpress.generator --config var/private-config.json --output var/custom-generated-match
```

The config has a 32-bit unsigned integer `seed` and one to eight `phases`.
Each phase has `start_ms`, `eastbridge` and `northport`. Each team setting has
`pressure`, `directness`, `escape_skill` (finite values from 0 to 1) and `flank`
(`left`, `centre`, `right`). Times are milliseconds elapsed within period 2:
180000 means 48:00, 480000 means 53:00 and 780000 means 58:00. The first phase
starts at 180000; later starts strictly increase and must precede 780000.
`--config` and `--suite` cannot be combined with `--seed` or `--profile`.

## State and football conventions

The simulated states are controlled possession, a loose ball awaiting recovery,
and a restart awaiting control. Passes, carries and duels preserve player and
ball continuity. Completed passes transfer control to another registered player
on the same team. An incomplete pass or lost duel can precede an opponent's
recovery. A pass out of play leads to a delayed restart, excluded from open-play
high-recovery counts. Won duels retain control.

The 105 × 68 metre pitch uses actor-team attacking direction: every actor attacks
toward increasing x. The simulator keeps an internal fixed frame and rotates
both axes for Northport (`105 - x`, `68 - y`). A pressure-exposed challenge is
simulated when the holder is within its defensive third, x ≤ 35. Pressure changes
challenge and loss probabilities; directness changes forward range and completion
probability; flank preference biases lateral movement. Escape skill influences
retention. These are disclosed synthetic heuristics, not fitted football models.

Controlled actions are spaced 3–7 seconds apart, loose-ball resolutions 1–3
seconds and restarts 8–14 seconds. An initial zero-distance carry records the
starting holder. The generator does not compress an action to fit the ending
boundary: unfinished episodes remain pending. Its last event may precede 58:00.
The replay command supplies the 58:00 observation cutoff explicitly.

Every generated record has revision 1, a stable event ID, strictly increasing
occurrence order and source delivery sequence, and distinct occurrence and
availability times. Delivery delay is 0–300 milliseconds, bounded by the segment
end. Match IDs hash the configuration and generator version; event IDs are local
to that match. A changed configuration creates a different match. Generated
initial revisions reuse the existing correction-capable downstream pipeline.

Comparison windows remain `(48:00,53:00]` and `(53:00,58:00]`: exclude the start,
include the end. High recoveries require Eastbridge open-play established control
at normalized x ≥ 70. Duels and restarts do not qualify by themselves.

## Feed and evaluator separation

`feeds/<opaque-match-id>.json` contains only the existing public fixture schema.
`evaluation/<same-id>.json` holds the seed, phases, hidden settings, change times,
pressure trial outcomes and exact feed SHA-256. A pressure trial resolves to
retained possession, recovery or pending; references point to actual source
events. These labels describe simulator outcomes, not a causal estimate.
`evaluation/manifest.json` contains split assignments, seeds, hashes and counts.

Give replay and agents only the feed files. Directory separation is a data-input
convention, not filesystem access control; evaluator files must not be mounted
into future agent tools. Match IDs do not spell out seeds or labels, but their
hashes are not intended to conceal a known configuration cryptographically.

The fixed suite selects configurations before generation:

| Split | Runs | Configuration |
| --- | ---: | --- |
| Development | 36 | Seeds 0–23 pressure shift; 101–106 steady; 201–206 directness/flank shift |
| Holdout | 6 | Seeds 1001–1006; unseen paired team settings and changes at 52:00 or 54:00 |

Whole match IDs, seeds and complete paired-team setting combinations are disjoint.
There is no retry or filtering for attractive outcomes. Held-out runs are checked
for structural validity only; no detector threshold has been fitted to them and
no performance claim is made from these six runs.

## Independently reviewed development controls

The frozen expectations in `tests/expected_generator_controls.json` were written
separately after reviewing event identities, times, coordinates and resolutions.
Neither production generation nor replay reads this file.

| Control | Seed/profile | High recoveries before → after | Current-window pressure outcome |
| --- | --- | --- | --- |
| Successful pressure | 2 / pressure-shift | 1 → 3 | Three challenges resolve to high recoveries |
| Unsuccessful pressure | 7 / pressure-shift | 0 → 0 | One challenge, possession retained |
| No tactical change | 103 / steady | 0 → 0 | One challenge, possession retained |
| Count increase without a successful pressure challenge | 15 / pressure-shift | 1 → 2 | Five challenges, all retained |

Seed 2's qualifying IDs are `g0031`, then `g0087`, `g0097`, `g0107`.
Seed 15's are `g0005`, then `g0086`, `g0106`; opponent pass errors create the later
recoveries. This control prevents treating a count increase as proof of effective
pressure. Seed 59 is a separate boundary regression: a lost duel at exactly 58:00
remains pending. It is not added to the fixed suite or holdout.

## Verification and limits

The 59 new tests check every suite feed's geometry and possession continuity,
strict configuration validation, timing and revision identity, reproducibility,
split separation, independent positive/negative controls, pending endings,
overwrite refusal and evaluator separation. A generated public feed also passes
through persisted history, evidence creation and audience presentation without
its private configuration. All 236 backend tests pass. Exact CLI and test output
is recorded in [progress](progress.md).

This is a ten-minute synthetic possession simulator with a small fixed roster and
an unchanged 0–1 score. It has no shots, goals, full-match scheduling, offside,
tracking data, calibrated probabilities or real-match validity claim. The current
browser scenario selector still uses the curated fixtures; generated feeds are
available through the CLI. No new detector, recap or Azure deployment is included.

The next increment now implements [pressure exposure and defensive build-up
escape](pressure.md) from observable event evidence, with fully observed episodes,
boundary exclusions, pending counts, separate minimum samples and cooldowns.
Private simulator labels remain evaluation-only. [Durable pressure publication
and replay cards](pressure-publication.md) are now implemented. Further detectors
and recaps follow later.
