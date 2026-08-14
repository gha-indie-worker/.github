from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import test_org_isolation as isolation

SOURCE_SHA = "a" * 40
REPOSITORY = "sample-test/isolation-canary"


class TestOrgIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.policy = isolation.load_policy(ROOT / "test-org-isolation-policy.json")

    def write_json(self, relative: str, value: object) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def write_text(self, relative: str, value: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        return path

    def write_manifest(self) -> None:
        self.write_json(
            ".github/test-org-isolation.json",
            {
                "schema_version": 1,
                "namespace_prefix": "isolation-canary-test",
                "domain_suffix": "isolation-canary.invalid",
                "service_account_prefix": "isolation-canary-test",
                "storage_prefix": "test/isolation-canary/",
                "outbound_send_enabled": False,
                "outbound_rate_limit_per_minute": 0,
                "production_connectivity_enabled": False,
            },
        )

    def scan(self) -> tuple[list[isolation.Finding], dict[str, str]]:
        return isolation.scan_inputs(self.root, REPOSITORY, self.policy)

    def test_valid_manifest_and_non_routable_test_config_pass(self) -> None:
        self.write_manifest()
        self.write_json(
            "config/test.json",
            {
                "DATABASE_URL": "postgresql://db.isolation-canary.invalid/test",
                "BUCKET": "isolation-canary-test",
                "OUTBOUND_SEND_ENABLED": False,
                "repository": "https://github.com/sample-test/isolation-canary",
                "twilio": "synthetic-sdk-dependency-only",
            },
        )
        manifest_findings, manifest_digest = isolation.validate_manifest(
            self.root, REPOSITORY, self.policy
        )
        findings, digests = self.scan()
        self.assertEqual(manifest_findings, [])
        self.assertIsNotNone(manifest_digest)
        self.assertEqual(findings, [])
        self.assertEqual(set(digests), {"config/test.json"})

    def test_missing_or_permissive_manifest_fails_closed(self) -> None:
        findings, digest = isolation.validate_manifest(
            self.root, REPOSITORY, self.policy
        )
        self.assertIsNone(digest)
        self.assertEqual([finding.rule_id for finding in findings], ["TST002"])

        self.write_manifest()
        manifest_path = self.root / ".github/test-org-isolation.json"
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
        value["outbound_send_enabled"] = True
        self.write_json(".github/test-org-isolation.json", value)
        findings, _digest = isolation.validate_manifest(
            self.root, REPOSITORY, self.policy
        )
        self.assertEqual([finding.rule_id for finding in findings], ["TST002"])

    def test_production_secret_runner_provider_and_identity_are_rejected(self) -> None:
        self.write_manifest()
        self.write_text(
            ".github/workflows/unsafe.yml",
            "environment: production\n"
            "runs-on: [self-hosted, privileged, production]\n"
            "token: ${{ secrets.PROD_DEPLOY_KEY }}\n"
            "TWILIO_ACCOUNT_ID: live-account\n"
            "CLOUD_PROJECT_ID: primary-customer-project\n"
            "API_BASE_URL: https://api.production.internal\n",
        )
        findings, _digests = self.scan()
        rules = {finding.rule_id for finding in findings}
        self.assertEqual(rules, {"TST003", "TST004", "TST005", "TST006", "TST009"})
        rendered = json.dumps([finding.__dict__ for finding in findings])
        self.assertNotIn("live-account", rendered)
        self.assertNotIn("primary-customer-project", rendered)
        self.assertNotIn("api.production.internal", rendered)

    def test_exact_reviewed_exception_suppresses_only_one_path_and_rule(self) -> None:
        self.write_manifest()
        self.write_text(
            ".github/workflows/legacy.yml",
            "environment: production\n",
        )
        exception_path = self.write_json(
            ".github/test-org-isolation-exceptions.json",
            {
                "schema_version": 1,
                "exceptions": [
                    {
                        "repository": REPOSITORY,
                        "path": ".github/workflows/legacy.yml",
                        "rule_id": "TST003",
                        "owner": "security-platform",
                        "rationale": "Temporary migration with outbound connectivity disabled.",
                        "review_url": "https://github.com/sample-test/isolation-canary/pull/1",
                        "expires": "2026-08-31",
                    }
                ],
            },
        )
        rules, exception_findings, digest = isolation.load_exceptions(
            exception_path, REPOSITORY, date(2026, 8, 14)
        )
        findings, _digests = self.scan()
        applied = isolation.apply_exceptions([*findings, *exception_findings], rules)
        self.assertTrue(digest.startswith("sha256:"))
        self.assertEqual(len(applied), 1)
        self.assertTrue(applied[0].suppressed)
        self.assertEqual(applied[0].exception_owner, "security-platform")

    def test_expired_exception_is_active_and_cannot_hide_finding(self) -> None:
        exception_path = self.write_json(
            ".github/test-org-isolation-exceptions.json",
            {
                "schema_version": 1,
                "exceptions": [
                    {
                        "repository": REPOSITORY,
                        "path": ".github/workflows/legacy.yml",
                        "rule_id": "TST003",
                        "owner": "security-platform",
                        "rationale": "Expired migration exception retained for test evidence.",
                        "review_url": "https://github.com/sample-test/isolation-canary/issues/2",
                        "expires": "2026-08-13",
                    }
                ],
            },
        )
        rules, findings, _digest = isolation.load_exceptions(
            exception_path, REPOSITORY, date(2026, 8, 14)
        )
        self.assertEqual(rules, [])
        self.assertEqual([finding.rule_id for finding in findings], ["TST007"])

    def test_report_and_sarif_are_digest_bound_and_content_free(self) -> None:
        self.write_manifest()
        self.write_text("config/unsafe.env", "DATABASE_URL=customer-primary\n")
        manifest_findings, manifest_digest = isolation.validate_manifest(
            self.root, REPOSITORY, self.policy
        )
        findings, digests = self.scan()
        report = isolation.build_report(
            REPOSITORY,
            SOURCE_SHA,
            self.policy,
            manifest_digest,
            isolation.digest_json({"schema_version": 1, "exceptions": []}),
            digests,
            [*manifest_findings, *findings],
        )
        repeated = isolation.build_report(
            REPOSITORY,
            SOURCE_SHA,
            self.policy,
            manifest_digest,
            isolation.digest_json({"schema_version": 1, "exceptions": []}),
            digests,
            [*manifest_findings, *findings],
        )
        self.assertEqual(report, repeated)
        self.assertEqual(report["source_sha"], SOURCE_SHA)
        self.assertTrue(str(report["report_sha256"]).startswith("sha256:"))
        sarif = isolation.to_sarif(report)
        rendered = json.dumps({"report": report, "sarif": sarif})
        self.assertNotIn("customer-primary", rendered)
        self.assertEqual(sarif["version"], "2.1.0")

    def test_symlinked_inputs_are_not_followed(self) -> None:
        self.write_manifest()
        outside = self.write_text("outside/unsafe.yml", "environment: production\n")
        link = self.root / "config" / "linked.yml"
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(outside)
        findings, digests = self.scan()
        self.assertNotIn("config/linked.yml", digests)
        self.assertEqual(
            [finding.path for finding in findings],
            ["outside/unsafe.yml"],
        )

    def test_generated_report_directory_is_never_rescanned(self) -> None:
        self.write_manifest()
        self.write_json(
            ".test-org-isolation/report.json",
            {"environment": "production", "secret": "do-not-rescan"},
        )
        findings, digests = self.scan()
        self.assertEqual(findings, [])
        self.assertNotIn(".test-org-isolation/report.json", digests)

    def test_cli_enforces_active_findings_but_audit_still_emits_evidence(self) -> None:
        self.write_manifest()
        report = self.root / ".test-org-isolation" / "report.json"
        common = [
            "--root",
            str(self.root),
            "--repository",
            REPOSITORY,
            "--source-sha",
            SOURCE_SHA,
            "--policy",
            str(ROOT / "test-org-isolation-policy.json"),
            "--format",
            "json",
            "--output",
            str(report),
        ]
        self.assertEqual(isolation.main(common), 0)
        self.assertTrue(
            json.loads(report.read_text(encoding="utf-8"))["summary"]["valid"]
        )

        self.write_text("config/unsafe.yml", "environment: production\n")
        self.assertEqual(isolation.main(common), 1)
        self.assertFalse(
            json.loads(report.read_text(encoding="utf-8"))["summary"]["valid"]
        )
        self.assertEqual(isolation.main([*common, "--mode", "audit"]), 0)


if __name__ == "__main__":
    unittest.main()
