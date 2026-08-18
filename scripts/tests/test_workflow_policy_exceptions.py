from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path

from workflow_policy_test_support import WorkflowPolicyTestCase, safe_workflow

from workflow_policy import Finding, apply_exceptions, load_exceptions


class WorkflowPolicyExceptionTests(WorkflowPolicyTestCase):
    def test_expiring_exact_exception_suppresses_only_matching_rule_and_job(self) -> None:
        findings = self.lint(
            safe_workflow().replace("    timeout-minutes: 10\n", ""),
            ".github/workflows/canary.yml",
        )
        timeout = next(item for item in findings if item.rule_id == "GHW003")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "exceptions.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "exceptions": [
                            {
                                "rule_id": "GHW003",
                                "path": ".github/workflows/canary.yml",
                                "job": "verify",
                                "owner": "platform-security",
                                "rationale": "Temporary canary compatibility investigation",
                                "expires": "2026-08-31",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            exceptions, exception_findings, digest = load_exceptions(path, date(2026, 8, 10))
        self.assertEqual(exception_findings, [])
        self.assertTrue(digest.startswith("sha256:"))
        applied = apply_exceptions([timeout], exceptions)
        self.assertTrue(applied[0].suppressed)
        self.assertEqual(applied[0].exception_owner, "platform-security")
        wrong_job = Finding(
            timeout.rule_id,
            timeout.level,
            timeout.path,
            timeout.line,
            timeout.message,
            job="other",
        )
        self.assertFalse(apply_exceptions([wrong_job], exceptions)[0].suppressed)

    def test_expired_or_wildcard_exception_is_not_silently_applied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expired = root / "expired.json"
            expired.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "exceptions": [
                            {
                                "rule_id": "GHW003",
                                "path": ".github/workflows/test.yml",
                                "owner": "platform-security",
                                "rationale": "Temporary compatibility investigation",
                                "expires": "2026-08-09",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            rules, findings, _digest = load_exceptions(expired, date(2026, 8, 10))
            self.assertEqual(rules, [])
            self.assertEqual(self.rule_ids(findings), {"GHW901"})

            wildcard = root / "wildcard.json"
            wildcard.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "exceptions": [
                            {
                                "rule_id": "GHW003",
                                "path": ".github/workflows/*.yml",
                                "owner": "platform-security",
                                "rationale": "Overly broad compatibility investigation",
                                "expires": "2026-08-31",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            rules, findings, _digest = load_exceptions(wildcard, date(2026, 8, 10))
            self.assertEqual(rules, [])
            self.assertEqual(self.rule_ids(findings), {"GHW901"})
