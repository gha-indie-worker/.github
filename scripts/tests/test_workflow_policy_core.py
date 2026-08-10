from __future__ import annotations

import json
import tempfile
from pathlib import Path

from workflow_policy_test_support import (
    CHECKOUT_SHA,
    ROOT,
    UPLOAD_SHA,
    WorkflowPolicyTestCase,
    safe_workflow,
)

from workflow_policy import WorkflowPolicyError, load_policy


class WorkflowPolicyCoreTests(WorkflowPolicyTestCase):
    def test_safe_workflow_has_no_findings(self) -> None:
        self.assertEqual(self.lint(safe_workflow()), [])

    def test_missing_permissions_concurrency_timeout_and_mutable_action_fail(self) -> None:
        workflow = """name: Unsafe
on:
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""
        findings = self.lint(workflow)
        expected = {"GHW001", "GHW003", "GHW004", "GHW006", "GHW015"}
        self.assertTrue(expected.issubset(self.rule_ids(findings)))

    def test_write_all_and_dynamic_concurrency_are_rejected(self) -> None:
        workflow = f"""name: Unsafe permissions
on: [push]
permissions: write-all
concurrency:
  group: unsafe-${{{{ github.event.pull_request.title }}}}
  cancel-in-progress: ${{{{ github.ref == 'refs/heads/main' }}}}
jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@{CHECKOUT_SHA}
        with:
          persist-credentials: false
"""
        findings = self.lint(workflow)
        self.assertTrue({"GHW002", "GHW007", "GHW008"}.issubset(self.rule_ids(findings)))

    def test_pull_request_target_privilege_shell_and_artifacts_fail_closed(self) -> None:
        workflow = f"""name: Dangerous target
on:
  pull_request_target:
permissions:
  contents: write
concurrency:
  group: target-${{{{ github.workflow }}}}-${{{{ github.ref }}}}
  cancel-in-progress: true
jobs:
  privileged:
    permissions: write-all
    runs-on: [self-hosted, gha-indie-worker, linux, x64]
    timeout-minutes: 5
    environment: production
    secrets: inherit
    steps:
      - uses: actions/checkout@{CHECKOUT_SHA}
        with:
          persist-credentials: false
      - uses: actions/download-artifact@{UPLOAD_SHA}
      - run: echo "${{{{ github.event.pull_request.title }}}}"
"""
        findings = self.lint(workflow)
        expected = {"GHW002", "GHW009", "GHW010", "GHW011", "GHW012", "GHW013", "GHW016"}
        self.assertTrue(expected.issubset(self.rule_ids(findings)))

    def test_schedule_requires_timezone_evidence_and_missed_run_policy(self) -> None:
        missing = f"""name: Scheduled
on:
  schedule:
    - cron: '0 8 * * *'
permissions:
  contents: read
concurrency:
  group: scheduled-${{{{ github.workflow }}}}
  cancel-in-progress: false
jobs:
  run:
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@{CHECKOUT_SHA}
        with:
          persist-credentials: false
"""
        findings = [item for item in self.lint(missing) if item.rule_id == "GHW014"]
        self.assertEqual(len(findings), 3)
        complete = missing.replace(
            "permissions:\n",
            "env:\n  SCHEDULE_TIMEZONE: America/Lima\n  RUN_EVIDENCE_SCHEMA: example.run.v1\n  MISSED_RUN_POLICY: fail-closed\npermissions:\n",
        )
        self.assertNotIn("GHW014", self.rule_ids(self.lint(complete)))

    def test_local_and_immutable_docker_actions_are_allowed(self) -> None:
        workflow = safe_workflow().replace(
            f"      - name: Upload evidence\n        uses: actions/upload-artifact@{UPLOAD_SHA}",
            "      - name: Local action\n        uses: ./.github/actions/local\n      - name: Docker action\n        uses: docker://example.invalid/tool@sha256:" + "a" * 64,
        )
        self.assertNotIn("GHW004", self.rule_ids(self.lint(workflow)))
        self.assertNotIn("GHW005", self.rule_ids(self.lint(workflow)))

    def test_checkout_requires_persist_credentials_false(self) -> None:
        missing = safe_workflow().replace("        with:\n          persist-credentials: false\n", "")
        true_value = safe_workflow().replace("persist-credentials: false", "persist-credentials: true")
        self.assertIn("GHW015", self.rule_ids(self.lint(missing)))
        self.assertIn("GHW015", self.rule_ids(self.lint(true_value)))

    def test_policy_rejects_weakened_security_switch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "policy.json"
            payload = json.loads((ROOT / "workflow-policy.json").read_text(encoding="utf-8"))
            payload["deny_pull_request_target"] = False
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(WorkflowPolicyError, "deny_pull_request_target"):
                load_policy(path)
