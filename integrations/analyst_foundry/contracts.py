"""Small, fail-closed contracts shared by provisioning and runtime."""
from __future__ import annotations

import json
import re
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
    if not isinstance(raw, str) or len(raw) > MAX_PACKET_CHARS:
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


# Display quantitative values from trusted metric cards, never model prose.
# This also prevents e.g. an unsupported probability being smuggled into a reading.
_NUMBER = re.compile(r"\d|\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|percent|percentage)\b", re.I)
_CERTAINTY = re.compile(r"\b(?:guaranteed|certainly|definitely|must|should|will score|will win|needs? to|has to|have to)\b", re.I)


def validate_reading(reading: Reading, packet: dict, role: str) -> Reading:
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
    if (_NUMBER.search(prose) or _CERTAINTY.search(prose)
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
