from __future__ import annotations

import json
from dataclasses import asdict
from typing import Mapping, Sequence

from .model import REPORT_SCHEMA, RULES, SARIF_SCHEMA, TOOL_SCHEMA_VERSION, Finding, Policy

def build_report(
    findings: Sequence[Finding],
    policy: Policy,
    input_digests: Mapping[str, str],
    exceptions_digest: str,
    source_sha: str | None,
    repository: str | None,
    mode: str,
) -> dict[str, object]:
    ordered = sorted(findings, key=Finding.sort_key)
    unsuppressed_errors = sum(
        item.level == "error" and not item.suppressed for item in ordered
    )
    return {
        "schema": REPORT_SCHEMA,
        "schema_version": TOOL_SCHEMA_VERSION,
        "policy_version": policy.policy_version,
        "policy_digest": policy.digest(),
        "exceptions_digest": exceptions_digest,
        "repository": repository,
        "source_sha": source_sha,
        "mode": mode,
        "input_digests": dict(sorted(input_digests.items())),
        "summary": {
            "files": len(input_digests),
            "findings": len(ordered),
            "suppressed": sum(item.suppressed for item in ordered),
            "unsuppressed_errors": unsuppressed_errors,
            "valid": unsuppressed_errors == 0,
        },
        "findings": [asdict(item) for item in ordered],
    }


def report_to_sarif(report: Mapping[str, object]) -> dict[str, object]:
    results: list[dict[str, object]] = []
    findings = report.get("findings", [])
    if not isinstance(findings, list):
        raise WorkflowPolicyError("report findings must be a list")
    for raw in findings:
        if not isinstance(raw, dict):
            continue
        result: dict[str, object] = {
            "ruleId": raw["rule_id"],
            "level": "none" if raw.get("suppressed") else raw["level"],
            "message": {"text": raw["message"]},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": raw["path"]},
                        "region": {"startLine": raw["line"]},
                    }
                }
            ],
            "properties": {
                "job": raw.get("job"),
                "suppressed": raw.get("suppressed", False),
                "exceptionOwner": raw.get("exception_owner"),
                "exceptionExpires": raw.get("exception_expires"),
            },
        }
        results.append(result)
    rules = []
    for rule_id, metadata in sorted(RULES.items()):
        rules.append(
            {
                "id": rule_id,
                "name": metadata["name"],
                "shortDescription": {"text": metadata["description"]},
                "defaultConfiguration": {"level": metadata["level"]},
            }
        )
    return {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "gha-indie-workflow-policy",
                        "version": str(report["policy_version"]),
                        "informationUri": "https://github.com/gha-indie-worker/.github",
                        "rules": rules,
                    }
                },
                "automationDetails": {
                    "id": f"{report.get('repository') or 'repository'}/{report.get('source_sha') or 'unknown'}"
                },
                "results": results,
                "properties": {
                    "policyDigest": report["policy_digest"],
                    "exceptionsDigest": report["exceptions_digest"],
                    "mode": report["mode"],
                },
            }
        ],
    }


def render_text(report: Mapping[str, object]) -> str:
    lines: list[str] = []
    findings = report.get("findings", [])
    if isinstance(findings, list):
        for raw in findings:
            if not isinstance(raw, dict):
                continue
            status = "suppressed" if raw.get("suppressed") else raw.get("level", "error")
            job = f" job={raw['job']}" if raw.get("job") else ""
            lines.append(
                f"{raw['path']}:{raw['line']}: {status} {raw['rule_id']}:{job} {raw['message']}"
            )
    summary = report["summary"]
    if isinstance(summary, dict):
        lines.append(
            "workflow policy: "
            f"files={summary['files']} findings={summary['findings']} "
            f"suppressed={summary['suppressed']} errors={summary['unsuppressed_errors']} "
            f"valid={str(summary['valid']).lower()}"
        )
    return "\n".join(lines) + "\n"


