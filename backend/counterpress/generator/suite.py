"""Fixed development/holdout assignments. Never select seeds by generated outcomes."""

from counterpress.generator.models import GeneratorConfig, Phase, Tactics


def profile(seed: int, name: str = "pressure-shift") -> GeneratorConfig:
    east = Tactics(pressure=0.2, directness=0.4, flank="centre", escape_skill=0.65)
    north = Tactics(pressure=0.25, directness=0.55, flank="right", escape_skill=0.75)
    phases = [Phase(start_ms=180000, eastbridge=east, northport=north)]
    if name == "pressure-shift":
        phases.append(Phase(start_ms=480000, eastbridge=east.model_copy(update={"pressure": 0.85}), northport=north))
    elif name == "directness-shift":
        phases.append(Phase(start_ms=480000, eastbridge=east.model_copy(update={"directness": 0.8, "flank": "left"}), northport=north))
    elif name != "steady":
        raise ValueError("unknown generator profile")
    return GeneratorConfig(seed=seed, phases=tuple(phases))


def suite() -> dict[str, tuple[GeneratorConfig, ...]]:
    development = tuple(profile(seed, "pressure-shift") for seed in range(24))
    development += tuple(profile(seed, "steady") for seed in range(101, 107))
    development += tuple(profile(seed, "directness-shift") for seed in range(201, 207))
    # Different seeds AND complete setting combinations, fixed before generation.
    # These runs are for structural validation / later detector evaluation, not tuning.
    holdout = []
    for index, seed in enumerate(range(1001, 1007)):
        east = Tactics(pressure=0.35, directness=0.25, flank="right", escape_skill=0.8)
        north = Tactics(pressure=0.45, directness=0.7, flank="left", escape_skill=0.9)
        if index % 2 == 0:
            phases = (Phase(start_ms=180000, eastbridge=east, northport=north),
                      Phase(start_ms=420000, eastbridge=east.model_copy(update={"pressure": 0.7}), northport=north))
        else:
            phases = (Phase(start_ms=180000, eastbridge=east, northport=north),
                      Phase(start_ms=540000, eastbridge=east.model_copy(update={"directness": 0.6, "flank": "centre"}), northport=north))
        holdout.append(GeneratorConfig(seed=seed, phases=phases))
    return {"development": development, "holdout": tuple(holdout)}
