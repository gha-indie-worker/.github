from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from workflow_policy_test_support import ROOT, SCRIPTS, WorkflowPolicyTestCase, safe_workflow

from workflow_policy import build_report, report_to_sarif


class WorkflowPolicyReportingTests(WorkflowPolicyTestCase):
    def test_report_and_sarif_are_deterministic_and_bind_exact_head(self) -> None:
        findings = self.lint(safe_workflow().replace("permissions:\n  contents: read\n", "", 1))
        report = build_report(
            findings,
            self.policy,
            {".github/workflows/test.yml": "sha256:" + "a" * 64},
            "sha256:" + "b" * 64,
            "c" * 40,
            "gha-indie-worker/.github",
            "enforce",
        )
        self.assertEqual(json.dumps(report, sort_keys=True), json.dumps(report, sort_keys=True))
        self.assertEqual(report["source_sha"], "c" * 40)
        self.assertFalse(report["summary"]["valid"])
        sarif = report_to_sarif(report)
        self.assertEqual(sarif["version"], "2.1.0")
        expected_id = f"gha-indie-worker/.github/{'c' * 40}"
        self.assertEqual(sarif["runs"][0]["automationDetails"]["id"], expected_id)

    def test_cli_enforce_fails_and_audit_reports_without_executing_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".github/workflows").mkdir(parents=True)
            (root / "workflow-policy.json").write_text(
                (ROOT / "workflow-policy.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            workflow = root / ".github/workflows/unsafe.yml"
            workflow.write_text("name: unsafe\non: [push]\njobs: {}\n", encoding="utf-8")
            command = [
                sys.executable,
                str(SCRIPTS / "workflow_policy_linter.py"),
                "--root",
                str(root),
                "--format",
                "json",
                "--source-sha",
                "d" * 40,
                "--repository",
                "example/test",
            ]
            enforced = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertEqual(enforced.returncode, 1)
            enforced_report = json.loads(enforced.stdout)
            self.assertFalse(enforced_report["summary"]["valid"])
            self.assertEqual(
                set(enforced_report["input_digests"]),
                {".github/workflows/unsafe.yml"},
            )
            audited = subprocess.run(
                [*command, "--mode", "audit"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(audited.returncode, 0)
            self.assertFalse(json.loads(audited.stdout)["summary"]["valid"])
