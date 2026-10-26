"""Small, fail-closed contracts shared by provisioning and runtime."""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

ROLES = ("chance", "defence", "control", "players")
MAX_PACKET_CHARS = 24_000


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Reading(StrictModel):
    role: Literal["chance", "defence", "control", "players"]
    headline: str = Field(min_length=1, max_length=100)
    explanation: str = Field(min_length=1, max_length=550)
    alternative: str = Field(min_length=1, max_length=240)
    watch_next: str = Field(min_length=1, max_length=240)
    evidence_ids: list[str] = Field(min_length=1, max_length=8)
    metric_ids: list[str] = Field(min_length=1, max_length=8)
    confidence: Literal["low", "medium", "high"]


class SpecialistOutput(StrictModel):
    reading: Reading | None


class Selection(StrictModel):
    """Synthesis selects verified prose; it cannot introduce another claim."""
    accepted_roles: list[Literal["chance", "defence", "control", "players"]] = Field(max_length=4)
    selected_role: Literal["chance", "defence", "control", "players"] | None


def parse_packet(raw: str) -> dict:
    if not isinstance(raw, str) or len(raw) > MAX_PACKET_CHARS or len(raw.encode("utf-8")) > 32_000:
        raise ValueError("packet_size")
    packet = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    allowed = {"snapshot_id", "match_id", "cutoff", "through_sequence", "clubs", "score",
               "metrics", "players", "evidence", "signals", "language", "depth",
               "focus_player_id", "methods", "triggers", "windows"}
    if not isinstance(packet, dict) or set(packet) - allowed:
        raise ValueError("packet_fields")
    for name in ("snapshot_id", "match_id"):
        if not isinstance(packet.get(name), str) or not 1 <= len(packet[name]) <= 180:
            raise ValueError("packet_identity")
    cutoff = packet.get("cutoff")
    if (not isinstance(cutoff, dict) or set(cutoff) != {"period", "elapsed_ms"}
            or type(cutoff["period"]) is not int or cutoff["period"] not in (1, 2)
            or type(cutoff["elapsed_ms"]) is not int or not 0 <= cutoff["elapsed_ms"] <= 10_800_000
            or type(packet.get("through_sequence")) is not int or packet["through_sequence"] < 0):
        raise ValueError("packet_cutoff")
    for collection in ("metrics", "evidence", "signals", "players"):
        rows = packet.get(collection, [])
        if not isinstance(rows, list) or len(rows) > 256 or any(not isinstance(x, dict) for x in rows):
            raise ValueError("packet_collection")
        packet[collection] = rows
    for collection in ("metrics", "evidence", "signals"):
        ids = [x.get("id") for x in packet[collection]]
        if any(not isinstance(x, str) or not x or len(x) > 200 for x in ids) or len(ids) != len(set(ids)):
            raise ValueError("packet_ids")
    for evidence in packet["evidence"]:
        stamp = (evidence.get("period"), evidence.get("elapsed_ms"))
        if (any(type(x) is not int for x in stamp) or stamp[0] not in (1, 2)
                or stamp[1] < 0 or stamp > (cutoff["period"], cutoff["elapsed_ms"])):
            raise ValueError("future_evidence")
        available = (evidence.get("available_period"), evidence.get("available_ms"))
        if (any(type(x) is not int for x in available) or available[0] not in (1, 2)
                or available[1] < 0 or available > (cutoff["period"], cutoff["elapsed_ms"])
                or type(evidence.get("delivery_sequence")) is not int
                or not 1 <= evidence["delivery_sequence"] <= packet["through_sequence"]):
            raise ValueError("unavailable_evidence")
        if type(evidence.get("revision")) is not int or evidence["revision"] < 0:
            raise ValueError("evidence_revision")
    if packet.get("language", "en") not in ("en", "zh-Hans"):
        raise ValueError("language")
    if packet.get("depth", "analyst") not in ("casual", "analyst", "brief", "detailed"):
        raise ValueError("depth")
    focus = packet.get("focus_player_id")
    if focus is not None and (not isinstance(focus, str) or len(focus) > 150):
        raise ValueError("focus_player")
    return packet


# Numeric claims must be traceable to cited scalar metrics or the explicit
# comparison-window duration. The independent verifier checks their meaning,
# entity and time window; matching a number alone is never semantic proof.
_NUMBER = re.compile(r"(?<![\w])[-+]?\d+(?:\.\d+)?")
_NUMBER_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
                 "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def supported_numbers(prose: str, reading: Reading, packet: dict) -> bool:
    cited = set(reading.metric_ids)
    values = [(Decimal(str(row["value"])), row.get("unit", "count")) for row in packet["metrics"]
              if row["id"] in cited and type(row.get("value")) in (int, float)]
    def durations(value):
        if isinstance(value, dict):
            start, end = value.get("start_ms"), value.get("end_ms")
            if type(start) is int and type(end) is int and end >= start:
                values.extend([(Decimal(end-start) / 60000, "minutes"),
                               (Decimal(end-start) / 1000, "seconds")])
            for child in value.values(): durations(child)
        elif isinstance(value, list):
            for child in value: durations(child)
    durations(packet.get("windows", {}))
    def unit_after(text):
        if re.match(r"\s*(?:%|percent|percentage)", text, re.I): return "percent"
        if re.match(r"\s*[- ]?(?:minutes?|mins?)\b", text, re.I): return "minutes"
        if re.match(r"\s*(?:seconds?|secs?)\b", text, re.I): return "seconds"
        if re.match(r"\s*(?:metres?|meters?|m)\b", text, re.I): return "metres"
        if re.match(r"\s*(?:km/h|kph)\b", text, re.I): return "km/h"
        if re.match(r"\s*(?:(?:completed|successful|unsuccessful)\s+)?(?:shots?|passes|goals?|players?|chances?|entries|turnovers)\b", text, re.I): return "count"
        return None
    if re.search(r"\b(?:eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand)\s+(?:shots?|passes|goals?|percent|players?|chances?)\b", prose, re.I):
        return False
    tokens = [(m.group(), unit_after(prose[m.end():])) for m in _NUMBER.finditer(prose)]
    for match in re.finditer(r"\b(" + "|".join(_NUMBER_WORDS) + r")\s+(shots?|passes|goals?|percent|players?|chances?)\b", prose, re.I):
        tokens.append((str(_NUMBER_WORDS[match.group(1).lower()]), "percent" if match.group(2).lower() == "percent" else "count"))
    if any(unit == "percent" for _, unit in tokens) and re.search(r"probability|chance of|likelihood|likely to", prose, re.I):
        return False  # This event-data pilot has no calibrated prediction metric.
    for token, unit in tokens:
        try:
            number = Decimal(token)
            quantum = Decimal(1).scaleb(number.as_tuple().exponent)
            candidates = [(v, u) for v, u in values if unit is None or u == unit]
            if not any(v.quantize(quantum, rounding=ROUND_HALF_UP) == number
                       and not (quantum >= 1 and v != v.to_integral() and u in ("expected_goals", "ratio", "index"))
                       for v, u in candidates):
                return False
        except InvalidOperation:
            return False
    return True


_CERTAINTY = re.compile(r"\b(?:guaranteed|certainly|definitely|must|should|will score|will win|needs? to|has to|have to)\b", re.I)


def clock_context(packet: dict) -> dict:
    period, ms = packet["cutoff"]["period"], packet["cutoff"]["elapsed_ms"]
    def label(value): return f"{value // 60000}:{value // 1000 % 60:02d}"
    name = "First half" if period == 1 else "Second half"
    result = {"period_label": name, "elapsed_in_period": label(ms),
              "half_time_boundary": period == 1 and ms >= 2_700_000,
              "full_time_boundary": period == 2 and ms >= 2_700_000}
    for key in ("current", "previous"):
        window = packet.get("windows", {}).get(key, {})
        if type(window.get("start_ms")) is int and type(window.get("end_ms")) is int:
            result[key + "_window"] = name + " " + label(window["start_ms"]) + "–" + label(window["end_ms"])
    return result


def validate_temporal_and_sentence_prose(reading: Reading, packet: dict):
    prose = " ".join((reading.headline, reading.explanation, reading.alternative, reading.watch_next))
    period, ms = packet["cutoff"]["period"], packet["cutoff"]["elapsed_ms"]
    if (re.search(r"half[ -]?time|半场休息|中场休息", prose, re.I) and period == 1 and ms < 2_700_000
            or re.search(r"full[ -]?time|final whistle|比赛结束|终场", prose, re.I) and not (period == 2 and ms >= 2_700_000)
            or re.search(r"second half|下半场", prose, re.I) and period == 1 and ms < 2_700_000
            or re.search(r"(?:final|closing|dying)\s+(?:\d+[- ]?)?(?:minutes?|moments?)", prose, re.I) and ms < 2_400_000
            or period == 2 and re.search(r"before half[ -]?time|approaching half[ -]?time", prose, re.I)):
        raise ValueError("temporal_claim")
    for text in (reading.explanation, reading.alternative, reading.watch_next):
        if not re.search(r"[.!?。！？]$", text.strip()) or re.search(r"\b(?:and|or|if|because|whether)[,.!?]*$", text.strip(), re.I):
            raise ValueError("incomplete_sentence")


def validate_reading(reading: Reading, packet: dict, role: str) -> Reading:
    validate_temporal_and_sentence_prose(reading, packet)
    if reading.role != role:
        raise ValueError("wrong_role")
    evidence_ids = {x["id"] for x in packet["evidence"]}
    metrics = {x["id"]: x for x in packet["metrics"]}
    if not set(reading.evidence_ids) <= evidence_ids or not set(reading.metric_ids) <= metrics.keys():
        raise ValueError("unknown_reference")
    if len(set(reading.evidence_ids)) != len(reading.evidence_ids) or len(set(reading.metric_ids)) != len(reading.metric_ids):
        raise ValueError("duplicate_reference")
    if any(metrics[i].get("status") == "unavailable" or metrics[i].get("value") is None for i in reading.metric_ids):
        raise ValueError("unavailable_metric")
    linked = {i for signal in packet["signals"] if signal.get("role") == role for i in signal.get("metric_ids", [])}
    if any(metrics[i].get("role") != role and i not in linked for i in reading.metric_ids):
        raise ValueError("wrong_metric_role")
    prose = " ".join([reading.headline, reading.explanation, reading.alternative, reading.watch_next])
    if (not supported_numbers(prose, reading, packet) or _CERTAINTY.search(prose)
            or re.search(r"[零〇一二两三四五六七八九十百千万亿]+(?:次|球|脚|成|秒|分钟|米|人)|百分之|必须|必然|肯定|一定会", prose)):
        raise ValueError("unsupported_prose")
    if "http" in prose.lower() or "<" in prose or ">" in prose:
        raise ValueError("unsafe_prose")
    return reading


def role_packet(packet: dict, role: str) -> dict:
    result = dict(packet)
    available = {x["id"] for x in packet["metrics"] if x.get("status") != "unavailable" and x.get("value") is not None}
    result["signals"] = [x for x in packet["signals"] if x.get("role") == role
                         and set(x.get("metric_ids", [])) <= available]
    linked = {i for x in result["signals"] for i in x.get("metric_ids", [])}
    result["metrics"] = [x for x in packet["metrics"] if x["id"] in available
                         and (x.get("role") == role or x["id"] in linked)]
    used = {i for x in result["signals"] for i in x.get("evidence_ids", [])}
    result["evidence"] = [x for x in packet["evidence"] if not used or x["id"] in used][-64:]
    return result
