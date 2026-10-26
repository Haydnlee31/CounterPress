"""Deterministic orchestration that executes INSIDE the Foundry hosted agent."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Awaitable, Callable
from .contracts import ROLES, SpecialistOutput, Selection, parse_packet, role_packet, validate_reading, clock_context


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class AnalystRuntime:
    def __init__(self, complete: Callable[[str, str, int], Awaitable[Completion]], *, max_runs: int = 1):
        if not 1 <= max_runs <= 4:
            raise ValueError("session_limit")
        self.complete = complete
        self.max_runs = max_runs
        self.runs = 0
        self.lock = asyncio.Lock()
        self.parallel = asyncio.Semaphore(2)

    async def run(self, raw: str, cancellation: asyncio.Event | None = None) -> dict:
        packet = parse_packet(raw)
        packet["clock"] = clock_context(packet)
        async with self.lock:
            if self.runs >= self.max_runs:
                raise ValueError("session_run_limit")
            self.runs += 1
        cancelled = cancellation or asyncio.Event()
        if cancelled.is_set():
            raise asyncio.CancelledError
        calls = 0
        usage = {"input_tokens": 0, "output_tokens": 0}
        failures = []
        failure_reasons = {}

        def reason(exc):
            if getattr(exc, "status_code", None) in (401, 403): return "authorization"
            if getattr(exc, "status_code", None) == 429: return "rate_limit"
            if isinstance(exc, (TimeoutError, asyncio.TimeoutError)): return "timeout"
            if isinstance(exc, ValueError): return "validation"
            return "provider"

        async def invoke(role: str, payload: dict, max_tokens: int) -> Completion:
            nonlocal calls
            async with self.parallel:
                if cancelled.is_set():
                    raise asyncio.CancelledError
                serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                if len(serialized) > 24_000 or len(serialized.encode("utf-8")) > 32_000:
                    raise ValueError("agent_input_size")
                calls += 1
                result = await asyncio.wait_for(self.complete(role, serialized, max_tokens), 32)
                usage["input_tokens"] += result.input_tokens
                usage["output_tokens"] += result.output_tokens
                if cancelled.is_set():
                    raise asyncio.CancelledError
                return result

        async def specialist(role: str):
            scoped = role_packet(packet, role)
            if not scoped["metrics"] or not scoped["evidence"]:
                return None
            try:
                result = await invoke(role, scoped, 600)
                parsed = SpecialistOutput.model_validate_json(result.text)
                return validate_reading(parsed.reading, scoped, role) if parsed.reading else None
            except (Exception, asyncio.TimeoutError) as exc:
                failures.append(role)
                failure_reasons[role] = reason(exc)
                return None

        async def work():
            readings = [r for r in await asyncio.gather(*(specialist(r) for r in ROLES)) if r]
            selected = None
            if readings:
                try:
                    cited_evidence = {i for r in readings for i in r.evidence_ids}
                    cited_metrics = {i for r in readings for i in r.metric_ids}
                    roles = {r.role for r in readings}
                    supporting_signals = [s for s in packet["signals"] if s.get("role") in roles]
                    cited_evidence.update(i for signal in supporting_signals for i in signal.get("evidence_ids", []))
                    cited_metrics.update(i for signal in supporting_signals for i in signal.get("metric_ids", []))
                    proof = {k: packet[k] for k in ("snapshot_id", "match_id", "cutoff", "clock", "clubs", "score", "players") if k in packet}
                    proof["evidence"] = [e for e in packet["evidence"] if e["id"] in cited_evidence]
                    proof["metrics"] = [m for m in packet["metrics"] if m["id"] in cited_metrics]
                    proof["signals"] = supporting_signals
                    proof["methods"] = packet.get("methods", {})
                    proof["windows"] = packet.get("windows", {})
                    response = await invoke("synthesis", {"readings": [r.model_dump() for r in readings],
                        "packet": proof, "focus_player_id": packet.get("focus_player_id"),
                        "depth": packet.get("depth")}, 1500)
                    selection = Selection.model_validate_json(response.text)
                    available = {r.role for r in readings}
                    accepted = set(selection.accepted_roles)
                    if (not accepted <= available or len(accepted) != len(selection.accepted_roles)
                            or bool(accepted) != (selection.selected_role is not None)
                            or selection.selected_role is not None and selection.selected_role not in accepted):
                        raise ValueError("invalid_verification_selection")
                    if accepted != available:
                        failures.append("verification")
                    readings = [r for r in readings if r.role in accepted]
                    selected = next((r for r in readings if r.role == selection.selected_role), None)
                except (Exception, asyncio.TimeoutError) as exc:
                    failures.append("synthesis")
                    failure_reasons["synthesis"] = reason(exc)
                    readings = []
            if cancelled.is_set():
                raise asyncio.CancelledError
            return {"snapshot_id": packet["snapshot_id"], "match_id": packet["match_id"],
                    "cutoff": packet["cutoff"], "through_sequence": packet["through_sequence"],
                    "status": "insufficient_evidence" if not readings else "partial" if failures else "complete",
                    "readings": [r.model_dump() for r in readings],
                    "summary": {"headline": selected.headline, "explanation": selected.explanation,
                                "evidence_ids": selected.evidence_ids, "metric_ids": selected.metric_ids} if selected else None,
                    "usage": {**usage, "model_calls": calls}, "failed_roles": sorted(failures), "failure_reasons": failure_reasons}

        task = asyncio.create_task(work())
        cancel_task = asyncio.create_task(cancelled.wait())
        try:
            done, _ = await asyncio.wait({task, cancel_task}, timeout=110, return_when=asyncio.FIRST_COMPLETED)
            if cancel_task in done or not done:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                if cancel_task in done:
                    raise asyncio.CancelledError
                raise TimeoutError("analysis_deadline")
            return await task
        finally:
            cancel_task.cancel()
            await asyncio.gather(cancel_task, return_exceptions=True)
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
