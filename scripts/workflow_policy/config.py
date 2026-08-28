from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from .model import (
    CONCURRENCY_EVENTS,
    RULES,
    TOOL_SCHEMA_VERSION,
    ExceptionRule,
    Finding,
    Policy,
    WorkflowPolicyError,
    sha256_json,
)

def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise WorkflowPolicyError(f"unable to read {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise WorkflowPolicyError(f"invalid JSON in {path}: {error}") from error


def load_policy(path: Path) -> Policy:
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise WorkflowPolicyError("policy must be a JSON object")
    required = {
        "schema_version",
        "policy_version",
        "immutable_refs",
        "concurrency_events",
        "scheduled_env",
        "deny_pull_request_target",
        "deny_untrusted_self_hosted",
        "require_checkout_persist_credentials_false",
    }
    if set(raw) != required:
        raise WorkflowPolicyError(
            f"policy fields must equal {sorted(required)}; got {sorted(raw)}"
        )
    if raw["schema_version"] != TOOL_SCHEMA_VERSION:
        raise WorkflowPolicyError(f"schema_version must equal {TOOL_SCHEMA_VERSION}")
    policy_version = raw["policy_version"]
    if not isinstance(policy_version, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.\d+", policy_version):
        raise WorkflowPolicyError("policy_version must use YYYY-MM-DD.N")
    immutable = raw["immutable_refs"]
    if not isinstance(immutable, dict) or set(immutable) != {
        "action_sha_length",
        "docker_digest_length",
    }:
        raise WorkflowPolicyError("immutable_refs has an invalid shape")
    action_sha_length = immutable["action_sha_length"]
    docker_digest_length = immutable["docker_digest_length"]
    if action_sha_length != 40 or docker_digest_length != 64:
        raise WorkflowPolicyError("immutable reference lengths must remain 40 and 64")
    concurrency_events = _string_sequence(raw["concurrency_events"], "concurrency_events")
    scheduled_env = _string_sequence(raw["scheduled_env"], "scheduled_env")
    if not set(CONCURRENCY_EVENTS).issubset(concurrency_events):
        raise WorkflowPolicyError("concurrency_events must include push, PR, PR target, and schedule")
    if set(scheduled_env) != {"SCHEDULE_TIMEZONE", "RUN_EVIDENCE_SCHEMA", "MISSED_RUN_POLICY"}:
        raise WorkflowPolicyError("scheduled_env must contain the three canonical evidence keys")
    booleans: dict[str, bool] = {}
    for key in (
        "deny_pull_request_target",
        "deny_untrusted_self_hosted",
        "require_checkout_persist_credentials_false",
    ):
        value = raw[key]
        if value is not True:
            raise WorkflowPolicyError(f"{key} must remain true")
        booleans[key] = value
    return Policy(
        schema_version=TOOL_SCHEMA_VERSION,
        policy_version=policy_version,
        action_sha_length=action_sha_length,
        docker_digest_length=docker_digest_length,
        concurrency_events=frozenset(concurrency_events),
        scheduled_env=tuple(scheduled_env),
        deny_pull_request_target=booleans["deny_pull_request_target"],
        deny_untrusted_self_hosted=booleans["deny_untrusted_self_hosted"],
        require_checkout_persist_credentials_false=booleans[
            "require_checkout_persist_credentials_false"
        ],
    )


def _string_sequence(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise WorkflowPolicyError(f"{field_name} must be a non-empty string array")
    if len(value) != len(set(value)):
        raise WorkflowPolicyError(f"{field_name} must not contain duplicates")
    return tuple(value)


def load_exceptions(path: Path | None, today: date) -> tuple[list[ExceptionRule], list[Finding], str]:
    if path is None:
        return [], [], sha256_json({"schema_version": 1, "exceptions": []})
    raw = _read_json(path)
    findings: list[Finding] = []
    rules: list[ExceptionRule] = []
    canonical_items: list[dict[str, object]] = []
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "exceptions"}:
        raise WorkflowPolicyError("exception document must contain schema_version and exceptions")
    if raw["schema_version"] != 1 or not isinstance(raw["exceptions"], list):
        raise WorkflowPolicyError("exception document has an invalid schema")
    for index, item in enumerate(raw["exceptions"]):
        location = f"{path.as_posix()}#exceptions[{index}]"
        try:
            rule = _parse_exception(item)
        except WorkflowPolicyError as error:
            findings.append(
                Finding(
                    "GHW901",
                    RULES["GHW901"]["level"],
                    path.as_posix(),
                    1,
                    f"{location}: {error}",
                )
            )
            continue
        canonical_items.append(
            {
                "rule_id": rule.rule_id,
                "path": rule.path,
                "job": rule.job,
                "owner": rule.owner,
                "rationale": rule.rationale,
                "expires": rule.expires.isoformat(),
            }
        )
        if rule.expires < today:
            findings.append(
                Finding(
                    "GHW901",
                    RULES["GHW901"]["level"],
                    path.as_posix(),
                    1,
                    f"{location}: exception expired on {rule.expires.isoformat()}",
                    job=rule.job,
                )
            )
            continue
        rules.append(rule)
    digest = sha256_json({"schema_version": 1, "exceptions": canonical_items})
    return rules, findings, digest


def _parse_exception(value: object) -> ExceptionRule:
    if not isinstance(value, dict):
        raise WorkflowPolicyError("exception must be an object")
    required = {"rule_id", "path", "owner", "rationale", "expires"}
    optional = {"job"}
    if not required.issubset(value) or not set(value).issubset(required | optional):
        raise WorkflowPolicyError("exception fields are incomplete or unknown")
    rule_id = value["rule_id"]
    path = value["path"]
    owner = value["owner"]
    rationale = value["rationale"]
    expires = value["expires"]
    job = value.get("job")
    if not isinstance(rule_id, str) or rule_id not in RULES or rule_id.startswith("GHW9"):
        raise WorkflowPolicyError("rule_id is unknown or cannot be suppressed")
    if not isinstance(path, str) or not path.startswith(".github/workflows/") or "*" in path:
        raise WorkflowPolicyError("path must name one exact workflow file")
    if not isinstance(owner, str) or len(owner.strip()) < 3:
        raise WorkflowPolicyError("owner must be explicit")
    if not isinstance(rationale, str) or len(rationale.strip()) < 12:
        raise WorkflowPolicyError("rationale must contain at least 12 characters")
    if job is not None and (not isinstance(job, str) or not job.strip()):
        raise WorkflowPolicyError("job must be a non-empty string when present")
    if not isinstance(expires, str):
        raise WorkflowPolicyError("expires must be an ISO date")
    try:
        expiry = date.fromisoformat(expires)
    except ValueError as error:
        raise WorkflowPolicyError("expires must be an ISO date") from error
    return ExceptionRule(rule_id, path, owner.strip(), rationale.strip(), expiry, job)


