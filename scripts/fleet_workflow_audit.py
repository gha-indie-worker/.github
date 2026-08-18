#!/usr/bin/env python3
"""Audit GitHub Actions workflows across every repository visible to ``gh``.

The target workflows are treated as untrusted text.  This program never checks
out a repository, evaluates an expression, invokes an action, restores a cache,
downloads an artifact, starts a container, or contacts an endpoint named by a
workflow.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence
from urllib.parse import urlencode

from workflow_policy import lint_model, load_policy, parse_workflow
from workflow_policy.model import Finding, Policy

FLEET_REPORT_SCHEMA = "gha-indie-worker.workflow-fleet-report.v1"
DEFAULT_AFFILIATION = "owner,organization_member"
DEFAULT_BATCH_SIZE = 12
MAX_BATCH_SIZE = 25
REQUEST_TIMEOUT_SECONDS = 60


class FleetAuditError(RuntimeError):
    """Raised when the fleet cannot be enumerated or audited safely."""


@dataclass(frozen=True)
class Repository:
    name_with_owner: str
    owner: str
    name: str
    default_branch: str
    archived: bool
    disabled: bool
    visibility: str


@dataclass(frozen=True)
class WorkflowSource:
    path: str
    oid: str
    text: str


@dataclass(frozen=True)
class RepositorySnapshot:
    source_sha: str | None
    workflows: tuple[WorkflowSource, ...]
    empty_repository: bool = False


@dataclass(frozen=True)
class FetchError:
    repository: str
    stage: str
    message: str


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _run(
    command: Sequence[str],
    *,
    input_text: str | None = None,
    runner: Runner = subprocess.run,
) -> str:
    try:
        completed = runner(
            list(command),
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
            env=os.environ.copy(),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise FleetAuditError(
            f"{command[0]} API request exceeded {REQUEST_TIMEOUT_SECONDS} seconds"
        ) from error
    except OSError as error:
        raise FleetAuditError(f"unable to execute {command[0]}: {error}") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "command failed").strip()
        # GitHub/gh errors do not need the command environment or request body.
        raise FleetAuditError(f"{command[0]} API request failed: {detail[:1000]}")
    return completed.stdout


class GhFleetSource:
    """Read repository metadata and workflow blobs through authenticated ``gh``."""

    def __init__(self, gh: str = "gh", runner: Runner = subprocess.run) -> None:
        self.gh = gh
        self.runner = runner
        self.last_rate_limit: dict[str, object] | None = None

    def list_repositories(self, affiliation: str) -> list[Repository]:
        endpoint = "user/repos?" + urlencode(
            {"per_page": 100, "affiliation": affiliation}
        )
        raw = _run(
            [self.gh, "api", "--paginate", "--slurp", endpoint],
            runner=self.runner,
        )
        try:
            pages = json.loads(raw)
        except json.JSONDecodeError as error:
            raise FleetAuditError(f"repository inventory was not valid JSON: {error}") from error
        if not isinstance(pages, list):
            raise FleetAuditError("repository inventory must be a list of pages")
        repositories: list[Repository] = []
        for page in pages:
            if not isinstance(page, list):
                raise FleetAuditError("repository inventory page must be a list")
            for item in page:
                repositories.append(parse_repository(item))
        unique = {item.name_with_owner.casefold(): item for item in repositories}
        return sorted(unique.values(), key=lambda item: item.name_with_owner.casefold())

    def fetch_workflows(
        self, repositories: Sequence[Repository]
    ) -> tuple[dict[str, RepositorySnapshot], list[FetchError]]:
        if not repositories:
            return {}, []
        head_data, head_graph_errors = self._graphql(build_head_query(repositories))
        errors: list[FetchError] = []
        if head_graph_errors:
            errors.append(FetchError("<batch>", "head_graphql", head_graph_errors))
        results: dict[str, RepositorySnapshot] = {}
        bound_repositories: list[Repository] = []
        source_shas: list[str] = []
        for index, repository in enumerate(repositories):
            node = head_data.get(f"r{index}")
            if not isinstance(node, dict):
                errors.append(FetchError(repository.name_with_owner, "repository", "missing repository data"))
                continue
            remote_default = node.get("defaultBranchRef")
            if node.get("isEmpty") is True:
                if remote_default is not None:
                    errors.append(
                        FetchError(
                            repository.name_with_owner,
                            "default_branch",
                            "empty repository unexpectedly has a default branch",
                        )
                    )
                    continue
                results[repository.name_with_owner] = RepositorySnapshot(None, (), True)
                continue
            if not isinstance(remote_default, dict) or remote_default.get("name") != repository.default_branch:
                errors.append(
                    FetchError(
                        repository.name_with_owner,
                        "default_branch",
                        "default branch changed during exact-head audit",
                    )
                )
                continue
            target = remote_default.get("target")
            source_sha = target.get("oid") if isinstance(target, dict) else None
            if not isinstance(source_sha, str) or len(source_sha) != 40:
                errors.append(
                    FetchError(
                        repository.name_with_owner,
                        "source_sha",
                        "default-branch commit identity is missing",
                    )
                )
                continue
            bound_repositories.append(repository)
            source_shas.append(source_sha)
        if not bound_repositories:
            return results, errors

        data, workflow_graph_errors = self._graphql(
            build_graphql_query(bound_repositories, source_shas)
        )
        if workflow_graph_errors:
            errors.append(FetchError("<batch>", "workflow_graphql", workflow_graph_errors))
        for index, (repository, source_sha) in enumerate(
            zip(bound_repositories, source_shas, strict=True)
        ):
            node = data.get(f"r{index}")
            if not isinstance(node, dict):
                errors.append(FetchError(repository.name_with_owner, "repository", "missing exact-SHA repository data"))
                continue
            workflow_tree = node.get("workflows")
            if workflow_tree is None:
                results[repository.name_with_owner] = RepositorySnapshot(source_sha, ())
                continue
            if not isinstance(workflow_tree, dict) or not isinstance(workflow_tree.get("entries"), list):
                errors.append(FetchError(repository.name_with_owner, "workflow_tree", "invalid workflow tree"))
                continue
            sources: list[WorkflowSource] = []
            for entry in workflow_tree["entries"]:
                source, error = parse_workflow_entry(repository, entry)
                if error is not None:
                    errors.append(error)
                elif source is not None:
                    sources.append(source)
            results[repository.name_with_owner] = RepositorySnapshot(
                source_sha,
                tuple(sorted(sources, key=lambda item: item.path)),
            )
        return results, errors

    def _graphql(self, query: str) -> tuple[dict[str, object], str | None]:
        payload = _run(
            [self.gh, "api", "graphql", "--input", "-"],
            input_text=json.dumps({"query": query}),
            runner=self.runner,
        )
        try:
            response = json.loads(payload)
        except json.JSONDecodeError as error:
            raise FleetAuditError(f"workflow response was not valid JSON: {error}") from error
        if not isinstance(response, dict):
            raise FleetAuditError("workflow response must be a JSON object")
        data = response.get("data")
        if not isinstance(data, dict):
            raise FleetAuditError("workflow response is missing GraphQL data")
        rate_limit = data.get("rateLimit")
        if isinstance(rate_limit, dict):
            self.last_rate_limit = dict(rate_limit)
        graph_errors = response.get("errors")
        return data, _compact_graphql_errors(graph_errors) if graph_errors else None


def parse_repository(value: object) -> Repository:
    if not isinstance(value, dict):
        raise FleetAuditError("repository inventory item must be an object")
    owner = value.get("owner")
    owner_login = owner.get("login") if isinstance(owner, dict) else None
    name = value.get("name")
    full_name = value.get("full_name") or value.get("nameWithOwner")
    default_branch = value.get("default_branch")
    if not all(isinstance(item, str) and item for item in (owner_login, name, full_name, default_branch)):
        raise FleetAuditError("repository inventory item is missing identity or default branch")
    if full_name.casefold() != f"{owner_login}/{name}".casefold():
        raise FleetAuditError(f"repository identity mismatch for {full_name}")
    return Repository(
        name_with_owner=full_name,
        owner=owner_login,
        name=name,
        default_branch=default_branch,
        archived=value.get("archived") is True,
        disabled=value.get("disabled") is True,
        visibility=str(value.get("visibility") or "unknown"),
    )


def build_head_query(repositories: Sequence[Repository]) -> str:
    if not 1 <= len(repositories) <= MAX_BATCH_SIZE:
        raise FleetAuditError(f"GraphQL batch size must be between 1 and {MAX_BATCH_SIZE}")
    selections: list[str] = []
    for index, repository in enumerate(repositories):
        owner = json.dumps(repository.owner)
        name = json.dumps(repository.name)
        selections.append(
            f"""r{index}: repository(owner: {owner}, name: {name}) {{
              nameWithOwner
              isEmpty
              defaultBranchRef {{ name target {{ ... on Commit {{ oid }} }} }}
            }}"""
        )
    return "query FleetWorkflowHeads {\n" + "\n".join(selections) + "\nrateLimit { cost remaining resetAt }\n}"


def build_graphql_query(
    repositories: Sequence[Repository], source_shas: Sequence[str]
) -> str:
    if not 1 <= len(repositories) <= MAX_BATCH_SIZE or len(repositories) != len(source_shas):
        raise FleetAuditError(
            f"GraphQL repository/SHA batch must contain 1 to {MAX_BATCH_SIZE} matching items"
        )
    selections: list[str] = []
    for index, (repository, source_sha) in enumerate(
        zip(repositories, source_shas, strict=True)
    ):
        if len(source_sha) != 40 or any(character not in "0123456789abcdefABCDEF" for character in source_sha):
            raise FleetAuditError(f"invalid exact source SHA for {repository.name_with_owner}")
        owner = json.dumps(repository.owner)
        name = json.dumps(repository.name)
        expression = json.dumps(f"{source_sha}:.github/workflows")
        selections.append(
            f"""r{index}: repository(owner: {owner}, name: {name}) {{
              nameWithOwner
              workflows: object(expression: {expression}) {{
                ... on Tree {{
                  entries {{
                    name
                    type
                    oid
                    object {{ ... on Blob {{ byteSize isBinary text }} }}
                  }}
                }}
              }}
            }}"""
        )
    return "query ExactFleetWorkflowAudit {\n" + "\n".join(selections) + "\nrateLimit { cost remaining resetAt }\n}"


def parse_workflow_entry(
    repository: Repository, value: object
) -> tuple[WorkflowSource | None, FetchError | None]:
    if not isinstance(value, dict):
        return None, FetchError(repository.name_with_owner, "workflow_blob", "invalid tree entry")
    name = value.get("name")
    if not isinstance(name, str) or not name.endswith((".yml", ".yaml")):
        return None, None
    path = f".github/workflows/{name}"
    if value.get("type") != "blob":
        return None, FetchError(repository.name_with_owner, path, "workflow path is not a blob")
    blob = value.get("object")
    oid = value.get("oid")
    if not isinstance(blob, dict) or not isinstance(oid, str) or len(oid) != 40:
        return None, FetchError(repository.name_with_owner, path, "workflow blob metadata is incomplete")
    if blob.get("isBinary") is True or not isinstance(blob.get("text"), str):
        return None, FetchError(repository.name_with_owner, path, "workflow is binary or too large to inspect")
    return WorkflowSource(path, oid, blob["text"]), None


def audit_repository(
    repository: Repository,
    source_sha: str | None,
    sources: Sequence[WorkflowSource],
    policy: Policy,
    *,
    empty_repository: bool = False,
) -> dict[str, object]:
    if empty_repository:
        if source_sha is not None or sources:
            raise FleetAuditError(
                f"empty repository {repository.name_with_owner} has commit or workflow inputs"
            )
    elif source_sha is None:
        raise FleetAuditError(
            f"non-empty repository {repository.name_with_owner} is missing an exact source SHA"
        )
    findings: list[Finding] = []
    input_digests: dict[str, str] = {}
    blob_oids: dict[str, str] = {}
    for source in sorted(sources, key=lambda item: item.path):
        digest = "sha256:" + hashlib.sha256(source.text.encode("utf-8")).hexdigest()
        input_digests[source.path] = digest
        blob_oids[source.path] = source.oid
        findings.extend(lint_model(parse_workflow(source.text, source.path), policy))
    ordered = sorted(findings, key=Finding.sort_key)
    return {
        "repository": repository.name_with_owner,
        "default_branch": repository.default_branch,
        "source_sha": source_sha,
        "empty_repository": empty_repository,
        "archived": repository.archived,
        "disabled": repository.disabled,
        "visibility": repository.visibility,
        "input_digests": dict(sorted(input_digests.items())),
        "blob_oids": dict(sorted(blob_oids.items())),
        "summary": {
            "workflows": len(sources),
            "findings": len(ordered),
            "valid": not ordered,
        },
        "findings": [asdict(item) for item in ordered],
    }


def audit_fleet(
    source: GhFleetSource,
    policy: Policy,
    *,
    scanner_source_sha: str,
    affiliation: str = DEFAULT_AFFILIATION,
    owners: Iterable[str] = (),
    include_archived: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_repositories: int | None = None,
) -> dict[str, object]:
    if len(scanner_source_sha) != 40 or any(
        character not in "0123456789abcdefABCDEF" for character in scanner_source_sha
    ):
        raise FleetAuditError("scanner_source_sha must be one immutable 40-character commit")
    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise FleetAuditError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")
    discovered = source.list_repositories(affiliation)
    owner_set = {owner.casefold() for owner in owners}
    selected: list[Repository] = []
    excluded_archived = 0
    excluded_disabled = 0
    for repository in discovered:
        if owner_set and repository.owner.casefold() not in owner_set:
            continue
        if repository.disabled:
            excluded_disabled += 1
            continue
        if repository.archived and not include_archived:
            excluded_archived += 1
            continue
        selected.append(repository)
    if max_repositories is not None:
        selected = selected[:max_repositories]

    reports: list[dict[str, object]] = []
    errors: list[FetchError] = []
    for start in range(0, len(selected), batch_size):
        batch = selected[start : start + batch_size]
        try:
            snapshots, fetch_errors = source.fetch_workflows(batch)
        except FleetAuditError as error:
            errors.append(
                FetchError(
                    f"<batch:{start}-{start + len(batch) - 1}>",
                    "api",
                    str(error),
                )
            )
            continue
        errors.extend(fetch_errors)
        failed = {item.repository.casefold() for item in fetch_errors if item.repository != "<batch>"}
        for repository in batch:
            if repository.name_with_owner.casefold() in failed:
                continue
            snapshot = snapshots.get(repository.name_with_owner)
            if snapshot is None:
                errors.append(FetchError(repository.name_with_owner, "workflow_tree", "repository result missing"))
                continue
            reports.append(
                audit_repository(
                    repository,
                    snapshot.source_sha,
                    snapshot.workflows,
                    policy,
                    empty_repository=snapshot.empty_repository,
                )
            )

    workflow_count = sum(int(item["summary"]["workflows"]) for item in reports)
    finding_count = sum(int(item["summary"]["findings"]) for item in reports)
    repositories_with_findings = sum(not bool(item["summary"]["valid"]) for item in reports)
    no_workflows = sum(int(item["summary"]["workflows"]) == 0 for item in reports)
    empty_repositories = sum(bool(item["empty_repository"]) for item in reports)
    ordered_errors = sorted(errors, key=lambda item: (item.repository.casefold(), item.stage, item.message))
    return {
        "schema": FLEET_REPORT_SCHEMA,
        "schema_version": 1,
        "policy_version": policy.policy_version,
        "policy_digest": policy.digest(),
        "scanner_source_sha": scanner_source_sha.lower(),
        "scope": {
            "affiliation": affiliation,
            "owners": sorted(owner_set),
            "include_archived": include_archived,
            "max_repositories": max_repositories,
        },
        "rate_limit": source.last_rate_limit,
        "summary": {
            "repositories_discovered": len(discovered),
            "repositories_selected": len(selected),
            "repositories_scanned": len(reports),
            "repositories_with_findings": repositories_with_findings,
            "repositories_without_workflows": no_workflows,
            "empty_repositories": empty_repositories,
            "workflows_scanned": workflow_count,
            "findings": finding_count,
            "fetch_errors": len(ordered_errors),
            "excluded_archived": excluded_archived,
            "excluded_disabled": excluded_disabled,
            "complete": len(reports) == len(selected) and not ordered_errors,
        },
        "fetch_errors": [asdict(item) for item in ordered_errors],
        "repositories": sorted(reports, key=lambda item: str(item["repository"]).casefold()),
    }


def render_text(report: Mapping[str, object]) -> str:
    summary = report["summary"]
    if not isinstance(summary, dict):
        raise FleetAuditError("fleet report summary is invalid")
    lines = [
        (
            "workflow fleet: "
            f"discovered={summary['repositories_discovered']} "
            f"selected={summary['repositories_selected']} "
            f"scanned={summary['repositories_scanned']} "
            f"workflows={summary['workflows_scanned']} "
            f"repositories_with_findings={summary['repositories_with_findings']} "
            f"findings={summary['findings']} "
            f"fetch_errors={summary['fetch_errors']} "
            f"complete={str(summary['complete']).lower()}"
        )
    ]
    repositories = report.get("repositories")
    if isinstance(repositories, list):
        for item in repositories:
            if not isinstance(item, dict) or not isinstance(item.get("summary"), dict):
                continue
            item_summary = item["summary"]
            if item_summary.get("findings"):
                lines.append(
                    f"{item['repository']}: workflows={item_summary['workflows']} findings={item_summary['findings']}"
                )
    errors = report.get("fetch_errors")
    if isinstance(errors, list):
        for item in errors:
            if isinstance(item, dict):
                lines.append(f"{item['repository']}: fetch-error stage={item['stage']} {item['message']}")
    return "\n".join(lines) + "\n"


def _compact_graphql_errors(value: object) -> str:
    if not isinstance(value, list):
        return "GraphQL returned an unknown error"
    messages = []
    for item in value:
        if isinstance(item, dict) and isinstance(item.get("message"), str):
            messages.append(item["message"])
    return "; ".join(messages)[:1000] or "GraphQL returned an unknown error"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=Path("workflow-policy.json"))
    parser.add_argument("--scanner-source-sha", required=True)
    parser.add_argument("--gh", default="gh")
    parser.add_argument("--affiliation", default=DEFAULT_AFFILIATION)
    parser.add_argument("--owner", action="append", default=[])
    parser.add_argument("--include-archived", action="store_true")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--max-repositories", type=int)
    parser.add_argument("--format", choices=("json", "text"), default="text")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="return zero despite fetch errors; the report still records complete=false",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.max_repositories is not None and args.max_repositories < 1:
        print("--max-repositories must be positive", file=sys.stderr)
        return 2
    try:
        policy = load_policy(args.policy)
        report = audit_fleet(
            GhFleetSource(args.gh),
            policy,
            scanner_source_sha=args.scanner_source_sha,
            affiliation=args.affiliation,
            owners=args.owner,
            include_archived=args.include_archived,
            batch_size=args.batch_size,
            max_repositories=args.max_repositories,
        )
        rendered = (
            json.dumps(report, indent=2, sort_keys=True) + "\n"
            if args.format == "json"
            else render_text(report)
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
    except (FleetAuditError, ValueError) as error:
        print(f"fleet workflow audit failed: {error}", file=sys.stderr)
        return 2
    complete = bool(report["summary"]["complete"])
    return 0 if complete or args.allow_partial else 2


if __name__ == "__main__":
    raise SystemExit(main())
