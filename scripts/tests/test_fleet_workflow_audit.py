from __future__ import annotations

import json
import subprocess
import sys

from workflow_policy_test_support import CHECKOUT_SHA, ROOT, SCRIPTS, WorkflowPolicyTestCase, safe_workflow

sys.path.insert(0, str(SCRIPTS))

from fleet_workflow_audit import (  # noqa: E402
    FetchError,
    GhFleetSource,
    Repository,
    RepositorySnapshot,
    WorkflowSource,
    audit_fleet,
    build_graphql_query,
    build_head_query,
)


def repository(name: str, *, archived: bool = False, disabled: bool = False) -> Repository:
    owner, short_name = name.split("/", 1)
    return Repository(name, owner, short_name, "main", archived, disabled, "private")


class FakeSource:
    def __init__(self) -> None:
        self.last_rate_limit = {"cost": 1, "remaining": 4999, "resetAt": "fixture"}
        self.repositories = [
            repository("example/clean"),
            repository("example/unsafe"),
            repository("example/archived", archived=True),
            repository("example/disabled", disabled=True),
        ]

    def list_repositories(self, affiliation: str) -> list[Repository]:
        assert affiliation == "owner,organization_member"
        return self.repositories

    def fetch_workflows(self, repositories):
        results = {}
        for item in repositories:
            if item.name == "clean":
                results[item.name_with_owner] = RepositorySnapshot(
                    "c" * 40,
                    (WorkflowSource(".github/workflows/ci.yml", "a" * 40, safe_workflow()),),
                )
            elif item.name == "unsafe":
                results[item.name_with_owner] = RepositorySnapshot(
                    "d" * 40,
                    (WorkflowSource(
                        ".github/workflows/ci.yml",
                        "b" * 40,
                        f"""name: unsafe
on:
  pull_request:
jobs:
  test:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@{CHECKOUT_SHA}
""",
                    ),),
                )
            else:
                results[item.name_with_owner] = RepositorySnapshot("e" * 40, ())
        return results, []


class FleetWorkflowAuditTests(WorkflowPolicyTestCase):
    def test_audit_is_exact_head_read_only_and_fail_closed(self) -> None:
        report = audit_fleet(FakeSource(), self.policy, scanner_source_sha="0" * 40)
        self.assertTrue(report["summary"]["complete"])
        self.assertEqual(report["summary"]["repositories_discovered"], 4)
        self.assertEqual(report["summary"]["repositories_scanned"], 2)
        self.assertEqual(report["summary"]["excluded_archived"], 1)
        self.assertEqual(report["summary"]["excluded_disabled"], 1)
        self.assertEqual(report["summary"]["workflows_scanned"], 2)
        self.assertEqual(report["summary"]["repositories_with_findings"], 1)
        unsafe = next(item for item in report["repositories"] if item["repository"] == "example/unsafe")
        self.assertEqual(unsafe["blob_oids"][".github/workflows/ci.yml"], "b" * 40)
        self.assertEqual(unsafe["source_sha"], "d" * 40)
        self.assertIn("GHW010", {item["rule_id"] for item in unsafe["findings"]})

    def test_fetch_error_marks_report_incomplete_without_hiding_clean_results(self) -> None:
        source = FakeSource()

        def failed_fetch(repositories):
            first = repositories[0]
            results = {
                item.name_with_owner: RepositorySnapshot("f" * 40, ())
                for item in repositories[1:]
            }
            return results, [FetchError(first.name_with_owner, "workflow_tree", "fixture failure")]

        source.fetch_workflows = failed_fetch
        report = audit_fleet(
            source,
            self.policy,
            scanner_source_sha="0" * 40,
            include_archived=True,
        )
        self.assertFalse(report["summary"]["complete"])
        self.assertEqual(report["summary"]["fetch_errors"], 1)
        self.assertEqual(report["summary"]["repositories_scanned"], 2)

    def test_batch_api_failure_is_recorded_and_later_batches_continue(self) -> None:
        source = FakeSource()
        calls = 0
        original = source.fetch_workflows

        def intermittent_fetch(repositories):
            nonlocal calls
            calls += 1
            if calls == 1:
                from fleet_workflow_audit import FleetAuditError

                raise FleetAuditError("fixture timeout")
            return original(repositories)

        source.fetch_workflows = intermittent_fetch
        report = audit_fleet(
            source,
            self.policy,
            scanner_source_sha="0" * 40,
            include_archived=True,
            batch_size=1,
        )
        self.assertFalse(report["summary"]["complete"])
        self.assertEqual(report["summary"]["fetch_errors"], 1)
        self.assertGreater(report["summary"]["repositories_scanned"], 0)

    def test_graphql_query_binds_default_branch_and_reads_only_workflow_blobs(self) -> None:
        head_query = build_head_query([repository("example/clean")])
        self.assertIn("defaultBranchRef", head_query)
        source_sha = "1" * 40
        query = build_graphql_query([repository("example/clean")], [source_sha])
        self.assertIn('repository(owner: "example", name: "clean")', query)
        self.assertIn(f'object(expression: "{source_sha}:.github/workflows")', query)
        self.assertIn("isBinary text", query)
        self.assertNotIn("mutation", query.casefold())

    def test_gh_inventory_paginates_and_deduplicates_case_insensitively(self) -> None:
        payload = {
            "owner": {"login": "Example"},
            "name": "Repo",
            "full_name": "Example/Repo",
            "default_branch": "dev",
            "archived": False,
            "disabled": False,
            "visibility": "private",
        }

        def runner(command, **kwargs):
            self.assertIn("--paginate", command)
            return subprocess.CompletedProcess(command, 0, json.dumps([[payload], [payload]]), "")

        repositories = GhFleetSource("gh-fixture", runner).list_repositories("owner")
        self.assertEqual(len(repositories), 1)
        self.assertEqual(repositories[0].default_branch, "dev")
