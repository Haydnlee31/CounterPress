"""Continuous-ball spatial proposals with training-fitted exponential tilts.

The proposal starts at the current ball location. It never moves the passer or
rewrites a completed event. Role/context tilts change probabilities, not quotas.
Legacy models retain their original RNG path in simulation.py.
"""
import math


def in_box(p):
    return p[0] >= 88.5 and 13.84 <= p[1] <= 54.16


def features(a, b):
    gain = math.hypot(105-a[0], 34-a[1])-math.hypot(105-b[0], 34-b[1])
    threshold = 30 if a[0] < 52.5 and b[0] < 52.5 else 15 if a[0] < 52.5 else 10
    return {
        'progression': gain >= threshold,
        'third_entry': a[0] < 70 <= b[0],
        'box_entry': not in_box(a) and in_box(b),
        'long': math.dist(a, b) >= 32,
        'backward': b[0]-a[0] < -5,
        'lateral': abs(b[0]-a[0]) <= 5,
        'cross': a[0] > 75 and abs(a[1]-34) > 18 and abs(b[1]-34) < 14,
    }


def pass_target(model, role, start, rng):
    z = min(2, int(start[0]/35))
    dx, dy = model['pass_deltas'][f'{z}:x'], model['pass_deltas'][f'{z}:y']
    scale = model.get('pass_length_role_scale', {}).get(role, 1)
    tilts = model['spatial']['pass_tilts'][role]
    proposals, weights = [], []
    for _ in range(12):
        for attempt in range(50):
            x = start[0]+rng.gauss(dx['mean'], dx['sd'])*scale
            y = start[1]+rng.gauss(dy['mean'], dy['sd'])*scale
            if 1 < x < 104 and 1 < y < 67:
                break
        target = (max(1, min(70 if role == 'GK' else 104, x)), max(1, min(67, y)))
        score = sum(tilts.get(k, 0) for k, present in features(start, target).items() if present)
        proposals.append(target)
        weights.append(math.exp(max(-15, min(15, score))))
    return rng.choices(proposals, weights)[0]
