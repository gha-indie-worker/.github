from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date

TOOL_SCHEMA_VERSION = 1
REPORT_SCHEMA = "gha-indie-worker.workflow-policy-report.v1"
SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
CONCURRENCY_EVENTS = frozenset({"push", "pull_request", "pull_request_target", "schedule"})

RULES: dict[str, dict[str, str]] = {
    "GHW000": {
        "name": "ambiguous-workflow-syntax",
        "level": "error",
        "description": "The conservative parser could not prove the workflow structure safe.",
    },
    "GHW001": {
        "name": "explicit-workflow-permissions",
        "level": "error",
        "description": "Every workflow must declare top-level permissions explicitly.",
    },
    "GHW002": {
        "name": "forbid-write-all",
        "level": "error",
        "description": "write-all is never an acceptable workflow or job permission.",
    },
    "GHW003": {
        "name": "bounded-job-timeout",
        "level": "error",
        "description": "Every executable job must declare timeout-minutes.",
    },
    "GHW004": {
        "name": "immutable-action-pin",
        "level": "error",
        "description": "External actions and reusable workflows must use immutable commit SHAs.",
    },
    "GHW005": {
        "name": "immutable-docker-action-pin",
        "level": "error",
        "description": "docker:// action references must use an immutable sha256 digest.",
    },
    "GHW006": {
        "name": "explicit-workflow-concurrency",
        "level": "error",
        "description": "Concurrent event-driven workflows must declare a bounded concurrency policy.",
    },
    "GHW007": {
        "name": "complete-static-concurrency",
        "level": "error",
        "description": "Concurrency requires a group and an explicit static cancel-in-progress decision.",
    },
    "GHW008": {
        "name": "trusted-concurrency-expression",
        "level": "error",
        "description": "Concurrency groups must not interpolate attacker-controlled event payloads or secrets.",
    },
    "GHW009": {
        "name": "pull-request-target-review",
        "level": "error",
        "description": "pull_request_target requires an explicit expiring exception and independent review.",
    },
    "GHW010": {
        "name": "untrusted-self-hosted-runner",
        "level": "error",
        "description": "Untrusted pull-request events cannot run on self-hosted infrastructure.",
    },
    "GHW011": {
        "name": "untrusted-privilege",
        "level": "error",
        "description": "Untrusted triggers cannot receive write permissions, environments, or inherited secrets.",
    },
    "GHW012": {
        "name": "shell-expression-injection",
        "level": "error",
        "description": "Attacker-controlled event text must not be interpolated directly into shell scripts.",
    },
    "GHW013": {
        "name": "forbid-secrets-inherit",
        "level": "error",
        "description": "Reusable workflow calls must enumerate required secrets instead of inheriting all secrets.",
    },
    "GHW014": {
        "name": "scheduled-run-evidence-metadata",
        "level": "error",
        "description": "Scheduled workflows must declare timezone, evidence schema, and missed-run policy metadata.",
    },
    "GHW015": {
        "name": "checkout-without-persisted-credentials",
        "level": "error",
        "description": "actions/checkout must set persist-credentials to false.",
    },
    "GHW016": {
        "name": "untrusted-artifact-download",
        "level": "error",
        "description": "pull_request_target workflows cannot download artifacts without a reviewed exception.",
    },
    "GHW900": {
        "name": "invalid-policy",
        "level": "error",
        "description": "The workflow policy document is invalid.",
    },
    "GHW901": {
        "name": "invalid-or-expired-exception",
        "level": "error",
        "description": "An exception is malformed, unknown, expired, or too broad.",
    },
}


class WorkflowPolicyError(RuntimeError):
    """Raised when policy or exception configuration is invalid."""


@dataclass(frozen=True)
class Policy:
    schema_version: int
    policy_version: str
    action_sha_length: int
    docker_digest_length: int
    concurrency_events: frozenset[str]
    scheduled_env: tuple[str, ...]
    deny_pull_request_target: bool
    deny_untrusted_self_hosted: bool
    require_checkout_persist_credentials_false: bool

    def canonical_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "immutable_refs": {
                "action_sha_length": self.action_sha_length,
                "docker_digest_length": self.docker_digest_length,
            },
            "concurrency_events": sorted(self.concurrency_events),
            "scheduled_env": list(self.scheduled_env),
            "deny_pull_request_target": self.deny_pull_request_target,
            "deny_untrusted_self_hosted": self.deny_untrusted_self_hosted,
            "require_checkout_persist_credentials_false": self.require_checkout_persist_credentials_false,
        }

    def digest(self) -> str:
        return sha256_json(self.canonical_payload())


@dataclass
class Step:
    line: int
    uses: str | None = None
    with_values: dict[str, str] = field(default_factory=dict)
    run_lines: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class Job:
    name: str
    line: int
    timeout_line: int | None = None
    reusable_uses: str | None = None
    runs_on: list[str] = field(default_factory=list)
    permission_values: list[tuple[int, str, str]] = field(default_factory=list)
    environment_lines: list[int] = field(default_factory=list)
    secrets_inherit_lines: list[int] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)

    @property
    def executable(self) -> bool:
        return bool(self.steps) or self.reusable_uses is not None

    @property
    def self_hosted(self) -> bool:
        return any("self-hosted" in value.lower() for value in self.runs_on)


@dataclass
class WorkflowModel:
    path: str
    events: set[str] = field(default_factory=set)
    permissions_declared: bool = False
    permission_values: list[tuple[int, str, str]] = field(default_factory=list)
    concurrency_declared: bool = False
    concurrency_group: tuple[int, str] | None = None
    concurrency_cancel: tuple[int, str] | None = None
    env: dict[str, tuple[int, str]] = field(default_factory=dict)
    jobs: dict[str, Job] = field(default_factory=dict)
    syntax_findings: list["Finding"] = field(default_factory=list)


@dataclass(frozen=True)
class Finding:
    rule_id: str
    level: str
    path: str
    line: int
    message: str
    job: str | None = None
    suppressed: bool = False
    exception_owner: str | None = None
    exception_expires: str | None = None

    def sort_key(self) -> tuple[object, ...]:
        return (self.path, self.line, self.rule_id, self.job or "", self.message)


@dataclass(frozen=True)
class ExceptionRule:
    rule_id: str
    path: str
    owner: str
    rationale: str
    expires: date
    job: str | None = None

    def matches(self, finding: Finding) -> bool:
        if self.rule_id != finding.rule_id or self.path != finding.path:
            return False
        if self.job is not None and self.job != finding.job:
            return False
        return True




def make_finding(
    rule_id: str,
    path: str,
    line: int,
    message: str,
    job: str | None = None,
) -> Finding:
    return Finding(rule_id, RULES[rule_id]["level"], path, line, message, job)


def sha256_json(value: object) -> str:
    rendered = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(rendered).hexdigest()
