#!/usr/bin/env python3
"""Fail closed when a *-test repository can target production resources.

The scanner is intentionally static: it reads bounded local text files, never
evaluates workflow expressions, executes repository code, or contacts a value
that it discovers. Reports contain source locations and digests, never matched
credential or endpoint values.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlsplit

REPORT_SCHEMA = "gha-indie-worker.test-org-isolation-report.v1"
SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
POLICY_VERSION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.\d+$")
SAFE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]{1,127}$")
SECRET_REFERENCE_RE = re.compile(r"\bsecrets\.([A-Za-z_][A-Za-z0-9_]*)")
URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
ASSIGNMENT_RE = re.compile(
    r"^\s*(?:[-]\s*)?(?:export\s+)?['\"]?([A-Za-z_][A-Za-z0-9_.-]*)['\"]?\s*[:=]\s*(.+?)\s*$"
)
ENVIRONMENT_RE = re.compile(r"^\s*environment\s*:\s*([^#\s]+)", re.IGNORECASE)
RUNNER_RE = re.compile(r"^\s*runs-on\s*:\s*(.+)$", re.IGNORECASE)
SAFE_TLDS = (".invalid", ".test", ".example")
IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".github-hardening",
        ".hg",
        ".svn",
        ".test-org-isolation",
        "env/dec",
        "node_modules",
        "target",
        "vendor",
    }
)

RULES: dict[str, str] = {
    "TST001": "repository owner is not a test organization",
    "TST002": "test-isolation manifest is missing or invalid",
    "TST003": "production-like environment or secret scope is referenced",
    "TST004": "privileged self-hosted runner scope is referenced",
    "TST005": "production-like endpoint or infrastructure identity is referenced",
    "TST006": "paid outbound provider or production messaging scope is referenced",
    "TST007": "test-isolation exception is malformed or expired",
    "TST008": "configured input could not be bounded and inspected",
    "TST009": "deploy key, PAT, or cross-organization write credential is referenced",
}


class IsolationError(RuntimeError):
    """A public-safe policy, manifest, or input error."""


@dataclass(frozen=True)
class Policy:
    version: str
    organization_suffix: str
    manifest_path: str
    max_file_bytes: int
    extensions: frozenset[str]
    exact_names: frozenset[str]
    required_manifest_fields: tuple[str, ...]
    forbidden_secret_fragments: tuple[str, ...]
    privileged_runner_fragments: tuple[str, ...]
    digest: str


@dataclass(frozen=True)
class ExceptionRule:
    repository: str
    path: str
    rule_id: str
    owner: str
    rationale: str
    review_url: str
    expires: date


@dataclass(frozen=True)
class Finding:
    rule_id: str
    repository: str
    path: str
    line: int
    message: str
    fingerprint: str
    suppressed: bool = False
    exception_owner: str | None = None
    exception_review_url: str | None = None
    exception_expires: str | None = None

    def sort_key(self) -> tuple[object, ...]:
        return (self.path, self.line, self.rule_id, self.fingerprint)


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest_json(value: object) -> str:
    return digest_bytes(canonical_json(value).encode("utf-8"))


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise IsolationError(f"unable to read {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise IsolationError(f"invalid JSON in {path}: line {error.lineno}") from error


def string_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise IsolationError(f"{field} must be a non-empty string array")
    if not all(isinstance(item, str) and item for item in value):
        raise IsolationError(f"{field} must contain non-empty strings")
    if len(value) != len(set(value)):
        raise IsolationError(f"{field} must not contain duplicates")
    return tuple(value)


def load_policy(path: Path) -> Policy:
    value = read_json(path)
    required = {
        "schema_version",
        "policy_version",
        "test_organization_suffix",
        "manifest_path",
        "max_file_bytes",
        "scan_extensions",
        "scan_exact_names",
        "required_manifest_fields",
        "forbidden_secret_name_fragments",
        "privileged_runner_fragments",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise IsolationError("test-org isolation policy has an unsupported shape")
    if value["schema_version"] != 1:
        raise IsolationError("policy schema_version must equal 1")
    version = value["policy_version"]
    if not isinstance(version, str) or not POLICY_VERSION_RE.fullmatch(version):
        raise IsolationError("policy_version must use YYYY-MM-DD.N")
    suffix = value["test_organization_suffix"]
    if not isinstance(suffix, str) or not re.fullmatch(r"-[a-z0-9-]+", suffix):
        raise IsolationError("test_organization_suffix is invalid")
    manifest_path = value["manifest_path"]
    if (
        not isinstance(manifest_path, str)
        or manifest_path != ".github/test-org-isolation.json"
    ):
        raise IsolationError(
            "manifest_path must remain .github/test-org-isolation.json"
        )
    max_file_bytes = value["max_file_bytes"]
    if not isinstance(max_file_bytes, int) or isinstance(max_file_bytes, bool):
        raise IsolationError("max_file_bytes must be an integer")
    if not 4096 <= max_file_bytes <= 4 * 1024 * 1024:
        raise IsolationError("max_file_bytes must be between 4096 and 4194304")
    extensions = string_list(value["scan_extensions"], "scan_extensions")
    if any(not item.startswith(".") or item != item.lower() for item in extensions):
        raise IsolationError("scan_extensions must be lowercase suffixes")
    exact_names = string_list(value["scan_exact_names"], "scan_exact_names")
    required_fields = string_list(
        value["required_manifest_fields"], "required_manifest_fields"
    )
    expected_fields = {
        "namespace_prefix",
        "domain_suffix",
        "service_account_prefix",
        "storage_prefix",
        "outbound_send_enabled",
        "outbound_rate_limit_per_minute",
        "production_connectivity_enabled",
    }
    if set(required_fields) != expected_fields:
        raise IsolationError(
            "required_manifest_fields does not match the safety contract"
        )
    secret_fragments = string_list(
        value["forbidden_secret_name_fragments"],
        "forbidden_secret_name_fragments",
    )
    runner_fragments = string_list(
        value["privileged_runner_fragments"], "privileged_runner_fragments"
    )
    normalized = canonical_json(value).encode("utf-8")
    return Policy(
        version=version,
        organization_suffix=suffix,
        manifest_path=manifest_path,
        max_file_bytes=max_file_bytes,
        extensions=frozenset(extensions),
        exact_names=frozenset(exact_names),
        required_manifest_fields=required_fields,
        forbidden_secret_fragments=tuple(item.upper() for item in secret_fragments),
        privileged_runner_fragments=tuple(item.lower() for item in runner_fragments),
        digest=digest_bytes(normalized),
    )


def validate_repository(value: str) -> tuple[str, str]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise IsolationError("repository must use exact owner/name syntax")
    return tuple(value.split("/", 1))  # type: ignore[return-value]


def _finding(
    rule_id: str,
    repository: str,
    path: str,
    line: int,
    evidence: str,
    message: str | None = None,
) -> Finding:
    fingerprint = digest_json(
        {
            "rule_id": rule_id,
            "repository": repository.lower(),
            "path": path,
            "line": line,
            "evidence_sha256": digest_bytes(evidence.encode("utf-8")),
        }
    )
    return Finding(
        rule_id=rule_id,
        repository=repository,
        path=path,
        line=line,
        message=message or RULES[rule_id],
        fingerprint=fingerprint,
    )


def validate_manifest(
    root: Path, repository: str, policy: Policy
) -> tuple[list[Finding], str | None]:
    path = root / policy.manifest_path
    relative = policy.manifest_path
    if not path.is_file() or path.is_symlink():
        return [_finding("TST002", repository, relative, 1, "manifest-missing")], None
    try:
        raw_bytes = path.read_bytes()
        value = json.loads(raw_bytes)
    except (OSError, json.JSONDecodeError):
        return [
            _finding("TST002", repository, relative, 1, "manifest-unreadable")
        ], None
    allowed = {"schema_version", *policy.required_manifest_fields}
    if (
        not isinstance(value, dict)
        or set(value) != allowed
        or value.get("schema_version") != 1
    ):
        return [
            _finding("TST002", repository, relative, 1, "manifest-shape")
        ], digest_bytes(raw_bytes)
    errors: list[str] = []
    for field in ("namespace_prefix", "service_account_prefix"):
        item = value.get(field)
        if not isinstance(item, str) or not re.fullmatch(
            r"[a-z0-9][a-z0-9-]{2,62}-test", item
        ):
            errors.append(field)
    domain = value.get("domain_suffix")
    if not isinstance(domain, str) or not domain.endswith(SAFE_TLDS):
        errors.append("domain_suffix")
    storage = value.get("storage_prefix")
    if (
        not isinstance(storage, str)
        or not storage.startswith("test/")
        or not storage.endswith("/")
        or not SAFE_NAME_RE.fullmatch(storage)
    ):
        errors.append("storage_prefix")
    if value.get("outbound_send_enabled") is not False:
        errors.append("outbound_send_enabled")
    if value.get("outbound_rate_limit_per_minute") != 0:
        errors.append("outbound_rate_limit_per_minute")
    if value.get("production_connectivity_enabled") is not False:
        errors.append("production_connectivity_enabled")
    if errors:
        return [
            _finding(
                "TST002",
                repository,
                relative,
                1,
                ",".join(sorted(errors)),
                "test-isolation manifest has invalid safety fields: "
                + ", ".join(sorted(errors)),
            )
        ], digest_bytes(raw_bytes)
    return [], digest_bytes(raw_bytes)


def is_scan_candidate(root: Path, path: Path, policy: Policy) -> bool:
    relative = path.relative_to(root)
    parts = tuple(part.lower() for part in relative.parts)
    name = path.name.lower()
    if path.name in policy.exact_names:
        return True
    if len(parts) >= 3 and parts[:2] == (".github", "workflows"):
        return True
    if name == ".env" or name.startswith(".env.") or path.suffix.lower() == ".env":
        return True
    if set(parts[:-1]) & {
        "config",
        "deploy",
        "infra",
        "k8s",
        "kubernetes",
        "ops",
        "terraform",
    }:
        return True
    return any(
        marker in name
        for marker in (
            "compose",
            "config",
            "deployment",
            "kustomization",
            "settings",
            "values",
        )
    )


def discover_inputs(root: Path, policy: Policy) -> list[Path]:
    inputs: list[Path] = []
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        relative_current = current_path.relative_to(root).as_posix()
        directories[:] = sorted(
            directory
            for directory in directories
            if not (current_path / directory).is_symlink()
            and directory not in IGNORED_DIRECTORIES
            and f"{relative_current}/{directory}".strip("./") not in IGNORED_DIRECTORIES
        )
        for name in sorted(files):
            path = current_path / name
            if path.is_symlink():
                continue
            if name in {
                "test-org-isolation-exceptions.json",
                "test-org-isolation-policy.json",
            }:
                continue
            if (
                path.suffix.lower() in policy.extensions or name in policy.exact_names
            ) and is_scan_candidate(root, path, policy):
                if path.relative_to(root).as_posix() == policy.manifest_path:
                    continue
                inputs.append(path)
    return sorted(inputs, key=lambda item: item.relative_to(root).as_posix())


def safe_host(host: str) -> bool:
    normalized = host.rstrip(".").lower()
    if normalized in {"localhost", "example.com", "example.org", "example.net"}:
        return True
    if normalized.endswith(SAFE_TLDS):
        return True
    try:
        address = ipaddress.ip_address(normalized.strip("[]"))
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address.is_link_local


def test_scoped(value: str) -> bool:
    lowered = value.lower()
    if any(
        fragment in lowered for fragment in ("test", "sandbox", "mock", "local")
    ) or any(lowered.endswith(tld) for tld in SAFE_TLDS):
        return True
    if "://" in value:
        try:
            host = urlsplit(value).hostname
        except ValueError:
            host = None
        return host is not None and safe_host(host)
    return False


def name_contains_fragment(name: str, fragment: str) -> bool:
    normalized = name.upper()
    components = {item for item in re.split(r"[^A-Z0-9]+", normalized) if item}
    if fragment in {"PAT", "PROD"}:
        return fragment in components
    return fragment in normalized


def scan_text(
    repository: str, relative: str, source: str, policy: Policy
) -> list[Finding]:
    findings: list[Finding] = []
    for number, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//")):
            continue
        lowered = stripped.lower()
        environment = ENVIRONMENT_RE.match(line)
        if environment and environment.group(1).strip("'\"").lower() in {
            "prod",
            "production",
        }:
            findings.append(_finding("TST003", repository, relative, number, line))

        runner = RUNNER_RE.match(line)
        if (
            runner
            and "self-hosted" in runner.group(1).lower()
            and any(
                fragment in runner.group(1).lower()
                for fragment in policy.privileged_runner_fragments
            )
        ):
            findings.append(_finding("TST004", repository, relative, number, line))

        for secret_name in SECRET_REFERENCE_RE.findall(line):
            upper = secret_name.upper()
            if any(
                name_contains_fragment(upper, fragment)
                for fragment in policy.forbidden_secret_fragments
            ):
                rule = (
                    "TST009"
                    if any(
                        name_contains_fragment(upper, item)
                        for item in ("PAT", "DEPLOY_KEY", "CROSS_ORG_WRITE")
                    )
                    else "TST003"
                )
                findings.append(_finding(rule, repository, relative, number, line))

        assignment = ASSIGNMENT_RE.match(line)
        assignment_key = ""
        if assignment:
            key = assignment.group(1).upper().replace("-", "_").replace(".", "_")
            assignment_key = key
            raw_value = assignment.group(2).strip().strip("'\"")
            if any(fragment in key for fragment in ("SENDGRID", "TWILIO")) and any(
                fragment in key
                for fragment in (
                    "ACCOUNT",
                    "API",
                    "AUTH",
                    "ENABLED",
                    "FROM",
                    "KEY",
                    "SECRET",
                    "TOKEN",
                )
            ):
                findings.append(_finding("TST006", repository, relative, number, line))
            if any(
                name_contains_fragment(key, fragment)
                for fragment in ("PAT", "DEPLOY_KEY", "CROSS_ORG_WRITE_TOKEN")
            ):
                findings.append(_finding("TST009", repository, relative, number, line))
            infrastructure_keys = (
                "ACCOUNT_ID",
                "AUDIENCE",
                "BUCKET",
                "CLUSTER",
                "DATABASE_URL",
                "KUBERNETES_CONTEXT",
                "KUBE_CONTEXT",
                "PROJECT_ID",
                "ROLE_ARN",
                "SERVICE_ACCOUNT",
                "SUBJECT",
                "SUPABASE",
                "ZONE_ID",
            )
            if any(
                fragment in key for fragment in infrastructure_keys
            ) and not test_scoped(raw_value):
                findings.append(_finding("TST005", repository, relative, number, line))

        if any(
            fragment in assignment_key
            for fragment in (
                "API_BASE",
                "DATABASE",
                "DOMAIN",
                "ENDPOINT",
                "HOST",
                "ORIGIN",
                "SUPABASE_URL",
                "URI",
                "URL",
            )
        ):
            for candidate in URL_RE.findall(line):
                try:
                    host = urlsplit(candidate.rstrip(".,);]")).hostname
                except ValueError:
                    host = None
                if host and not safe_host(host):
                    findings.append(
                        _finding("TST005", repository, relative, number, line)
                    )
                    break

        if any(word in lowered for word in ("production", "prod-", "prod_")) and any(
            signal in lowered
            for signal in (
                "account",
                "audience",
                "bucket",
                "cluster",
                "context",
                "database",
                "namespace",
                "project",
                "role",
                "service_account",
                "subject",
                "supabase",
                "zone",
            )
        ):
            findings.append(_finding("TST005", repository, relative, number, line))
    return findings


def scan_inputs(
    root: Path, repository: str, policy: Policy
) -> tuple[list[Finding], dict[str, str]]:
    findings: list[Finding] = []
    digests: dict[str, str] = {}
    for path in discover_inputs(root, policy):
        relative = path.relative_to(root).as_posix()
        try:
            size = path.stat().st_size
            if size > policy.max_file_bytes:
                findings.append(
                    _finding("TST008", repository, relative, 1, "oversized")
                )
                continue
            raw = path.read_bytes()
        except OSError:
            findings.append(_finding("TST008", repository, relative, 1, "unreadable"))
            continue
        digests[relative] = digest_bytes(raw)
        if b"\x00" in raw:
            findings.append(_finding("TST008", repository, relative, 1, "binary"))
            continue
        source = raw.decode("utf-8", errors="replace")
        findings.extend(scan_text(repository, relative, source, policy))
    unique = {finding.sort_key(): finding for finding in findings}
    return sorted(unique.values(), key=Finding.sort_key), dict(sorted(digests.items()))


def parse_exception(value: object, index: int) -> ExceptionRule:
    required = {
        "repository",
        "path",
        "rule_id",
        "owner",
        "rationale",
        "review_url",
        "expires",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise IsolationError(f"exception {index} has an unsupported shape")
    repository = value["repository"]
    path = value["path"]
    rule_id = value["rule_id"]
    owner = value["owner"]
    rationale = value["rationale"]
    review_url = value["review_url"]
    expires = value["expires"]
    if not isinstance(repository, str):
        raise IsolationError(f"exception {index} repository is invalid")
    validate_repository(repository)
    if (
        not isinstance(path, str)
        or path.startswith("/")
        or ".." in Path(path).parts
        or any(marker in path for marker in ("*", "?", "[", "]"))
    ):
        raise IsolationError(
            f"exception {index} path must be exact and repository-relative"
        )
    if (
        not isinstance(rule_id, str)
        or rule_id not in RULES
        or rule_id
        in {
            "TST001",
            "TST002",
            "TST007",
            "TST008",
        }
    ):
        raise IsolationError(f"exception {index} rule_id is unknown or unsuppressible")
    if not isinstance(owner, str) or len(owner.strip()) < 3:
        raise IsolationError(f"exception {index} owner is not explicit")
    if not isinstance(rationale, str) or len(rationale.strip()) < 16:
        raise IsolationError(f"exception {index} rationale is too short")
    if not isinstance(review_url, str) or not re.fullmatch(
        r"https://github\.com/[^/]+/[^/]+/(?:pull|issues)/\d+", review_url
    ):
        raise IsolationError(
            f"exception {index} review_url is not an exact GitHub review"
        )
    if not isinstance(expires, str):
        raise IsolationError(f"exception {index} expires is invalid")
    try:
        expiry = date.fromisoformat(expires)
    except ValueError as error:
        raise IsolationError(f"exception {index} expires is invalid") from error
    return ExceptionRule(
        repository=repository,
        path=path,
        rule_id=rule_id,
        owner=owner.strip(),
        rationale=rationale.strip(),
        review_url=review_url,
        expires=expiry,
    )


def load_exceptions(
    path: Path | None, repository: str, today: date
) -> tuple[list[ExceptionRule], list[Finding], str]:
    empty = {"schema_version": 1, "exceptions": []}
    if path is None:
        return [], [], digest_json(empty)
    value = read_json(path)
    if not isinstance(value, dict) or set(value) != {"schema_version", "exceptions"}:
        raise IsolationError("exception document has an unsupported shape")
    if value["schema_version"] != 1 or not isinstance(value["exceptions"], list):
        raise IsolationError("exception document schema is invalid")
    rules: list[ExceptionRule] = []
    findings: list[Finding] = []
    canonical: list[dict[str, str]] = []
    for index, raw in enumerate(value["exceptions"]):
        try:
            rule = parse_exception(raw, index)
        except IsolationError as error:
            findings.append(
                _finding(
                    "TST007",
                    repository,
                    path.as_posix(),
                    1,
                    f"invalid:{index}",
                    str(error),
                )
            )
            continue
        canonical.append(
            {
                "repository": rule.repository,
                "path": rule.path,
                "rule_id": rule.rule_id,
                "owner": rule.owner,
                "rationale": rule.rationale,
                "review_url": rule.review_url,
                "expires": rule.expires.isoformat(),
            }
        )
        if rule.expires < today:
            findings.append(
                _finding(
                    "TST007",
                    repository,
                    path.as_posix(),
                    1,
                    f"expired:{index}:{rule.expires.isoformat()}",
                    f"exception {index} expired on {rule.expires.isoformat()}",
                )
            )
        else:
            rules.append(rule)
    return rules, findings, digest_json({"schema_version": 1, "exceptions": canonical})


def apply_exceptions(
    findings: Iterable[Finding], rules: Sequence[ExceptionRule]
) -> list[Finding]:
    result: list[Finding] = []
    for finding in findings:
        match = next(
            (
                rule
                for rule in rules
                if rule.repository.lower() == finding.repository.lower()
                and rule.path == finding.path
                and rule.rule_id == finding.rule_id
            ),
            None,
        )
        if match is None:
            result.append(finding)
        else:
            result.append(
                replace(
                    finding,
                    suppressed=True,
                    exception_owner=match.owner,
                    exception_review_url=match.review_url,
                    exception_expires=match.expires.isoformat(),
                )
            )
    return sorted(result, key=Finding.sort_key)


def build_report(
    repository: str,
    source_sha: str,
    policy: Policy,
    manifest_digest: str | None,
    exceptions_digest: str,
    input_digests: dict[str, str],
    findings: Sequence[Finding],
) -> dict[str, object]:
    finding_values = [
        {
            "rule_id": finding.rule_id,
            "level": "error",
            "path": finding.path,
            "line": finding.line,
            "message": finding.message,
            "fingerprint": finding.fingerprint,
            "suppressed": finding.suppressed,
            "exception_owner": finding.exception_owner,
            "exception_review_url": finding.exception_review_url,
            "exception_expires": finding.exception_expires,
        }
        for finding in findings
    ]
    active = sum(not finding.suppressed for finding in findings)
    body: dict[str, object] = {
        "schema_version": REPORT_SCHEMA,
        "repository": repository,
        "source_sha": source_sha,
        "policy_version": policy.version,
        "policy_sha256": policy.digest,
        "manifest_sha256": manifest_digest,
        "exceptions_sha256": exceptions_digest,
        "inputs": [
            {"path": path, "sha256": digest}
            for path, digest in sorted(input_digests.items())
        ],
        "findings": finding_values,
        "summary": {
            "inputs": len(input_digests),
            "findings": len(findings),
            "active_findings": active,
            "suppressed_findings": len(findings) - active,
            "valid": active == 0,
        },
    }
    body["report_sha256"] = digest_json(body)
    return body


def to_sarif(report: dict[str, object]) -> dict[str, object]:
    findings = report["findings"]
    assert isinstance(findings, list)
    results = []
    for item in findings:
        assert isinstance(item, dict)
        if item["suppressed"]:
            continue
        results.append(
            {
                "ruleId": item["rule_id"],
                "level": "error",
                "message": {"text": item["message"]},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": item["path"]},
                            "region": {"startLine": item["line"]},
                        }
                    }
                ],
                "partialFingerprints": {"testOrgIsolation/v1": item["fingerprint"]},
            }
        )
    return {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "test-org-isolation",
                        "version": str(report["policy_version"]),
                        "rules": [
                            {
                                "id": rule_id,
                                "shortDescription": {"text": description},
                            }
                            for rule_id, description in RULES.items()
                        ],
                    }
                },
                "automationDetails": {"id": report["source_sha"]},
                "results": results,
            }
        ],
    }


def to_markdown(report: dict[str, object]) -> str:
    summary = report["summary"]
    assert isinstance(summary, dict)
    lines = [
        "# Test-organization isolation",
        "",
        f"- Repository: `{report['repository']}`",
        f"- Source SHA: `{report['source_sha']}`",
        f"- Policy: `{report['policy_version']}` (`{report['policy_sha256']}`)",
        f"- Report: `{report['report_sha256']}`",
        f"- Result: `{'PASS' if summary['valid'] else 'FAIL'}`",
        f"- Inputs: `{summary['inputs']}`",
        f"- Active findings: `{summary['active_findings']}`",
        f"- Suppressed findings: `{summary['suppressed_findings']}`",
        "",
    ]
    findings = report["findings"]
    assert isinstance(findings, list)
    if not findings:
        lines.append("No findings.")
    else:
        lines.extend(
            ["| Rule | Location | Status | Fingerprint |", "| --- | --- | --- | --- |"]
        )
        for raw in findings:
            assert isinstance(raw, dict)
            status = "suppressed" if raw["suppressed"] else "active"
            lines.append(
                f"| {raw['rule_id']} | `{raw['path']}:{raw['line']}` | {status} | `{raw['fingerprint']}` |"
            )
    return "\n".join(lines) + "\n"


def write_output(path: Path | None, rendered: str) -> None:
    if path is None:
        print(rendered, end="")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    os.replace(temporary, path)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--exceptions", type=Path)
    parser.add_argument("--today")
    parser.add_argument("--mode", choices=("audit", "enforce"), default="enforce")
    parser.add_argument(
        "--format", choices=("json", "sarif", "markdown"), default="markdown"
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    try:
        owner, _name = validate_repository(args.repository)
        if not SHA_RE.fullmatch(args.source_sha):
            raise IsolationError(
                "source-sha must be an immutable 40-character commit SHA"
            )
        policy = load_policy(args.policy.resolve())
        today = (
            date.fromisoformat(args.today)
            if args.today
            else datetime.now(tz=UTC).date()
        )
        exception_rules, exception_findings, exception_digest = load_exceptions(
            args.exceptions.resolve() if args.exceptions else None,
            args.repository,
            today,
        )
    except (IsolationError, ValueError) as error:
        print(f"test-org isolation configuration failed: {error}", file=sys.stderr)
        return 2

    findings: list[Finding] = list(exception_findings)
    if not owner.lower().endswith(policy.organization_suffix):
        findings.append(
            _finding(
                "TST001",
                args.repository,
                ".github/test-org-isolation.json",
                1,
                owner.lower(),
            )
        )
    manifest_findings, manifest_digest = validate_manifest(
        root, args.repository, policy
    )
    findings.extend(manifest_findings)
    input_findings, input_digests = scan_inputs(root, args.repository, policy)
    findings.extend(input_findings)
    final_findings = apply_exceptions(findings, exception_rules)
    report = build_report(
        args.repository,
        args.source_sha,
        policy,
        manifest_digest,
        exception_digest,
        input_digests,
        final_findings,
    )
    if args.format == "json":
        rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    elif args.format == "sarif":
        rendered = json.dumps(to_sarif(report), indent=2, sort_keys=True) + "\n"
    else:
        rendered = to_markdown(report)
    write_output(args.output.resolve() if args.output else None, rendered)
    summary = report["summary"]
    assert isinstance(summary, dict)
    return 0 if args.mode == "audit" or summary["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
