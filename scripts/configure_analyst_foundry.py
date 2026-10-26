#!/usr/bin/env python3
"""Plan or provision isolated native agents; never modifies existing Footie agents.

Default is a pure local plan. --apply creates immutable versions and a hosted
coordinator, but does not invoke models, create sessions or grant Azure roles.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
import json
import hashlib
import io
import zipfile
import stat
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from integrations.analyst_foundry.definitions import DIRECTOR_NAME, NAMES, definition, definition_hash


def build_plan(model: str, image: str, verifier_model: str = "gpt-5-mini") -> dict:
    return {"coordinator": DIRECTOR_NAME, "specialists": [
        {"role": role, "name": name, "model": verifier_model if role == "synthesis" else model, "hash": definition_hash(definition(role, verifier_model if role == "synthesis" else model))}
        for role, name in NAMES.items()], "image_pinned": "@sha256:" in image,
        "cpu": "1", "memory": "2Gi", "idle_timeout_seconds": 120,
        "max_calls_per_run": 5, "specialist_output_tokens": 600, "verifier_output_tokens": 1500, "max_parallel_calls": 2, "max_runs_per_session": 1}


def ensure_version(project, name: str, value: dict):
    digest = definition_hash(value)
    # Content-addressed idempotence avoids unnecessary versions on repeated runs.
    from azure.core.exceptions import ResourceNotFoundError
    try:
        existing_versions = list(project.agents.list_versions(name))
    except ResourceNotFoundError:
        existing_versions = []
    for existing in existing_versions:
        if (existing.metadata or {}).get("footie_definition_hash") == digest:
            return existing
    return project.agents.create_version(name, body={"definition": value,
        "metadata": {"footie_definition_hash": digest, "footie_component": "analyst-mode"}})


def source_bundle() -> bytes:
    stream = io.BytesIO()
    source = ROOT / "integrations" / "analyst_foundry"
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.glob("*.py")):
            info = zipfile.ZipInfo("integrations/analyst_foundry/" + path.name, (2026, 1, 1, 0, 0, 0))
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, path.read_bytes())
        info = zipfile.ZipInfo("requirements.txt", (2026, 1, 1, 0, 0, 0))
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        archive.writestr(info, (source / "requirements.txt").read_bytes())
    return stream.getvalue()


def manifest_fingerprint(agents: dict, coordinator: dict, hosted_definition: dict, code_sha256: str | None) -> str:
    return definition_hash({"agents": agents, "coordinator": coordinator,
                            "hosted_definition": hosted_definition, "code_sha256": code_sha256})


def pin_versions(project, references: list[dict]) -> None:
    """Explicit routing is authoritative; body agent_reference is not a pin."""
    for reference in references:
        project.agents.update_details(reference["name"], body={"agent_endpoint": {
            "version_selector": {"version_selection_rules": [{"type": "FixedRatio",
                "agent_version": reference["version"], "traffic_percentage": 100}]}}})
        actual = project.agents.get(agent_name=reference["name"]).as_dict()
        rules = actual.get("agent_endpoint", {}).get("version_selector", {}).get("version_selection_rules")
        if rules != [{"type": "FixedRatio", "agent_version": reference["version"], "traffic_percentage": 100}]:
            raise ValueError("endpoint_version_pin_failed")


def provision(project, model: str, image: str, endpoint: str, *, code: bool = False, verifier_model: str = "gpt-5-mini") -> dict:
    from azure.ai.projects.models import HostedAgentDefinition, ContainerConfiguration, SessionConfiguration, ProtocolVersionRecord, AgentEndpointProtocol
    if not code and "@sha256:" not in image:
        raise ValueError("coordinator image must be pinned by digest")
    manifest = {}
    bundle_hash = None
    for role, name in NAMES.items():
        agent = ensure_version(project, name, definition(role, verifier_model if role == "synthesis" else model))
        manifest[role] = {"name": agent.name, "version": agent.version}
    hosted = HostedAgentDefinition(cpu="1", memory="2Gi",
        protocol_versions=[ProtocolVersionRecord(protocol=AgentEndpointProtocol.RESPONSES, version="2.0.0")],
        session_configuration=SessionConfiguration(idle_timeout_seconds=timedelta(seconds=120)),
        environment_variables={"FOUNDRY_PROJECT_ENDPOINT": endpoint, "FOOTIE_SPECIALIST_MANIFEST": json.dumps(manifest, separators=(",", ":")),
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false"})
    if code:
        from azure.ai.projects.models import CodeConfiguration
        from azure.core.exceptions import ResourceNotFoundError
        bundle = source_bundle()
        bundle_hash = hashlib.sha256(bundle).hexdigest()
        hosted.code_configuration = CodeConfiguration(runtime="python_3_13",
            entry_point=["python", "-m", "integrations.analyst_foundry.server"], dependency_resolution="remote_build")
        fingerprint = definition_hash({"definition": hosted.as_dict(), "bundle": bundle_hash})
        try:
            existing = list(project.agents.list_versions(DIRECTOR_NAME))
        except ResourceNotFoundError:
            existing = []
        agent = next((a for a in existing if (a.metadata or {}).get("footie_definition_hash") == fingerprint), None)
        if agent is None:
            upload = io.BytesIO(bundle)
            upload.name = "footie-analyst.zip"
            agent = project.agents.create_version_from_code(DIRECTOR_NAME, definition=hosted,
                code=upload, code_zip_sha256=bundle_hash,
                metadata={"footie_definition_hash": fingerprint, "footie_component": "analyst-mode"})
    else:
        hosted.container_configuration = ContainerConfiguration(image=image)
        agent = ensure_version(project, DIRECTOR_NAME, hosted.as_dict())
    coordinator = {"name": agent.name, "version": agent.version}
    pin_versions(project, [*manifest.values(), coordinator])
    return {"manifest_id": manifest_fingerprint(manifest, coordinator, hosted.as_dict(), bundle_hash),
            "coordinator": coordinator, "agents": manifest, "code_sha256": bundle_hash,
            "models": {role: verifier_model if role == "synthesis" else model for role in NAMES},
            "limits": build_plan(model, image, verifier_model)}



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--model", default="gpt-4.1-mini")
    parser.add_argument("--verifier-model", default="gpt-5-mini")
    parser.add_argument("--image", default="")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--code", action="store_true", help="Use native ZIP remote build instead of ACR image")
    args = parser.parse_args()
    if not args.apply:
        print(json.dumps(build_plan(args.model, args.image, args.verifier_model), indent=2))
        return
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
    if not endpoint.startswith("https://") or not args.manifest:
        parser.error("--apply requires HTTPS FOUNDRY_PROJECT_ENDPOINT and --manifest")
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential
    try:
        with DefaultAzureCredential() as credential, AIProjectClient(endpoint=endpoint, credential=credential) as project:
            result = provision(project, args.model, args.image, endpoint, code=args.code, verifier_model=args.verifier_model)
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(result, indent=2) + "\n")
        print("Native Analyst Mode agent versions registered; no model calls or sessions started.")
    except Exception as exc:
        # SDK exception text may contain private endpoints/resource identifiers.
        code = getattr(getattr(exc, "error", None), "code", None)
        status = getattr(exc, "status_code", None)
        safe_code = str(code) if code and str(code).replace("_", "").isalnum() else "unknown"
        print(f"Provisioning failed ({type(exc).__name__}, status={status}, code={safe_code}); inspect locally with secured diagnostics.", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
