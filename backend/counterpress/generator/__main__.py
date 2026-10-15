"""Generate one replay feed or a fixed development/holdout suite, with private labels separate."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import tempfile

from counterpress.generator.engine import encoded_feed, generate
from counterpress.generator.models import GeneratorConfig, VERSION
from counterpress.generator.suite import profile, suite


def export(output: Path, splits: dict[str, tuple[GeneratorConfig, ...]]) -> dict:
    """Stage a complete export, then publish to a new directory; never edit existing feeds."""
    if output.exists():
        raise FileExistsError("output directory already exists; choose a new directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"generator_version": VERSION, "splits": {}, "separation": "Feed files only for replay/agents; evaluation directory is evaluator-only."}
    with tempfile.TemporaryDirectory(prefix=".counterpress-generate-", dir=output.parent) as temporary:
        stage = Path(temporary) / "bundle"
        (stage / "feeds").mkdir(parents=True)
        (stage / "evaluation").mkdir()
        for split, configs in splits.items():
            manifest["splits"][split] = []
            for config in configs:
                result = generate(config)
                match_id = result.feed.match_id
                feed = encoded_feed(result.feed)
                feed_path = stage / "feeds" / f"{match_id}.json"
                # Duplicate config identities must not silently overwrite a prior split.
                with feed_path.open("x", encoding="utf-8") as stream:
                    stream.write(feed)
                (stage / "evaluation" / f"{match_id}.json").write_text(result.evaluation.model_dump_json(indent=2) + "\n", encoding="utf-8")
                manifest["splits"][split].append({"match_id": match_id, "seed": config.seed,
                    "feed_sha256": sha256(feed.encode()).hexdigest(), "event_count": len(result.feed.events)})
        (stage / "evaluation" / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        if output.exists():
            raise FileExistsError("output directory already exists; choose a new directory")
        stage.rename(output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new directory for feeds/ and evaluation/")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--suite", action="store_true", help="fixed 36 development + 6 held-out whole-match runs")
    mode.add_argument("--config", type=Path, help="private GeneratorConfig JSON with seed and hidden phases")
    parser.add_argument("--seed", type=int, help="single-match seed, defaults to 7")
    parser.add_argument("--profile", choices=("steady", "pressure-shift", "directness-shift"), help="single-match profile")
    args = parser.parse_args()
    try:
        if (args.suite or args.config) and (args.seed is not None or args.profile is not None):
            raise ValueError("--seed/--profile cannot be combined with --suite or --config")
        splits = suite() if args.suite else {"single": (GeneratorConfig.model_validate_json(args.config.read_text()) if args.config else
                    profile(args.seed if args.seed is not None else 7, args.profile or "pressure-shift"),)}
        manifest = export(args.output, splits)
        for split, matches in manifest["splits"].items():
            print(f"{split}: {len(matches)} matches | {sum(match['event_count'] for match in matches)} events")
            if len(matches) == 1:
                print(f"Feed: {args.output / 'feeds' / (matches[0]['match_id'] + '.json')}")
        print(f"Evaluator-only metadata: {args.output / 'evaluation'}")
        print("VALID: Event v1 feeds; hidden settings, seeds and outcome labels excluded from feeds.")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
