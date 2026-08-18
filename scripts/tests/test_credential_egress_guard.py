from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from credential_egress_guard import (
    BUILTIN_SECRET_NAMES,
    GuardError,
    Policy,
    ScanInput,
    content_sha,
    filesystem_inputs,
    finding_fingerprint,
    introduced_inputs,
    is_high_confidence_secret,
    load_policy,
    render_human,
    scan_all,
    scan_input,
    staged_inputs,
    tracked_inputs,
)


def synthetic(*parts: str) -> str:
    """Build invalid credential-shaped test data without storing a usable credential."""

    return "".join(parts)


def policy(*, suppressions: tuple[dict[str, str], ...] = ()) -> Policy:
    return Policy(
        policy_version="2099-01-01.1",
        allowed_ciphertext_paths=frozenset(
            ("env/enc/dev.env.enc", "env/enc/prod.env.enc")
        ),
        repository_secret_names=("REPOSITORY_PROVIDER_SECRET",),
        suppressions=suppressions,
    )


def item(path: str, text: str, *, symlink: bool = False) -> ScanInput:
    content = text.encode("utf-8")
    return ScanInput(
        path=path,
        content=content,
        source_sha=content_sha(content),
        is_symlink=symlink,
    )


class CredentialEgressGuardTests(unittest.TestCase):
    def detector_ids(self, path: str, text: str) -> set[str]:
        return {
            finding.detector_id
            for finding in scan_input(item(path, text), policy(), 1024 * 1024)
        }

    def test_synthetic_positive_corpus_covers_every_content_detector(self) -> None:
        private_key = synthetic(
            "-----BEGIN ",
            "PRIVATE KEY-----\n",
            "c3ludGhldGljLWludmFsaWQta2V5LW1hdGVyaWFs\n",
            "-----END ",
            "PRIVATE KEY-----",
        )
        cases = {
            "credential.github.legacy-token": synthetic("ghp", "_", "A1" * 18),
            "credential.github.fine-grained-token": synthetic(
                "github", "_pat_", "synthetic_", "A1" * 24
            ),
            "credential.linear.api-key": synthetic("lin", "_api_", "A1" * 18),
            "credential.aws.access-key-id": synthetic("AK", "IA", "A1" * 8),
            "credential.sendgrid.api-key": synthetic(
                "S", "G.", "A1" * 10, ".", "B2" * 10
            ),
            "credential.slack.token": synthetic("xox", "b-", "A1-" * 10),
            "credential.stripe.live-secret": synthetic("sk", "_live_", "A1" * 12),
            "credential.private-key": private_key,
            "credential.private-key-header": private_key,
            "credential.connection-string-userinfo": synthetic(
                "postgres://user:", "aB3!dE6_fG9-hJ2$kL5%mN8", "@db.invalid/app"
            ),
            "credential.signed-url": synthetic(
                "https://example.invalid/file?X-Amz-",
                "Signature=",
                "aB3_dE6-fG9+hJ2.kL5/mN8=pQ4%",
            ),
            "credential.authorization-header": synthetic(
                "Authorization: Bearer ", "aB3_dE6-fG9+hJ2.kL5/mN8=pQ4%"
            ),
            "credential.session-cookie": synthetic(
                "Set-Cookie: session=", "aB3_dE6-fG9+hJ2.kL5/mN8=pQ4%", "; Secure"
            ),
            "credential.secret-assignment": synthetic(
                "REPOSITORY_PROVIDER_SECRET=", "A1b2-C3d4_E5f6.G7h8" * 3
            ),
        }
        for expected, value in cases.items():
            with self.subTest(detector_id=expected):
                self.assertIn(expected, self.detector_ids("artifact.log", value))

    def test_human_and_json_shapes_never_need_matched_values(self) -> None:
        secret = synthetic("ghp", "_", "A1" * 18)
        findings, input_count, suppressed_count = scan_all(
            (item("job.log", secret),), policy(), 1024 * 1024
        )
        output = render_human(
            findings,
            input_count,
            suppressed_count,
            policy(),
        )
        self.assertNotIn(secret, output)
        self.assertIn("intentionally redacted", output)
        serialized = json.dumps([finding.__dict__ for finding in findings])
        self.assertNotIn(secret, serialized)

    def test_dotenv_and_ciphertext_path_policy(self) -> None:
        self.assertIn(
            "egress.plaintext-dotenv-path",
            self.detector_ids("env/dec/prod.env", "PLACEHOLDER=true"),
        )
        self.assertIn(
            "egress.plaintext-dotenv-path",
            self.detector_ids("config/.env.production", "PLACEHOLDER=true"),
        )
        self.assertIn(
            "egress.noncanonical-ciphertext-path",
            self.detector_ids("env/enc/staging.env.enc", "sops: {}"),
        )
        self.assertEqual(
            self.detector_ids("env/enc/prod.env.enc", "sops: {}"),
            set(),
        )
        self.assertEqual(
            self.detector_ids(".env.example", "API_KEY=placeholder"),
            set(),
        )

    def test_symlinks_and_oversized_inputs_fail_closed(self) -> None:
        symlink_findings = scan_input(
            item("env/enc/prod.env.enc", "elsewhere", symlink=True),
            policy(),
            1024,
        )
        self.assertIn(
            "egress.symlink", {finding.detector_id for finding in symlink_findings}
        )
        large_findings = scan_input(item("build.bin", "x" * 20), policy(), 10)
        self.assertIn(
            "egress.file-size-limit",
            {finding.detector_id for finding in large_findings},
        )

    def test_filesystem_scope_does_not_follow_a_symlink_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "synthetic-target.txt"
            secret = synthetic("ghp", "_", "A1" * 18)
            outside.write_text(secret, encoding="utf-8")
            link = root / "artifact-link"
            link.symlink_to(outside)
            inputs = list(filesystem_inputs(root, (link,)))
            self.assertEqual(len(inputs), 1)
            self.assertTrue(inputs[0].is_symlink)
            self.assertNotIn(secret.encode("utf-8"), inputs[0].content)
            findings, _, _ = scan_all(inputs, policy(), 1024 * 1024)
            self.assertEqual(
                {finding.detector_id for finding in findings},
                {"egress.symlink"},
            )

    def test_negative_corpus_avoids_hashes_and_placeholders(self) -> None:
        values = (
            "API_KEY=placeholder",
            "ACCESS_TOKEN=redacted",
            "PASSWORD=changeme",
            "DATABASE_URL=" + "a" * 64,
            '"integrity": "sha512-' + "A" * 80 + '"',
            "ordinary documentation text",
        )
        for value in values:
            with self.subTest(value=value[:20]):
                self.assertEqual(self.detector_ids("README.md", value), set())
        self.assertFalse(is_high_confidence_secret("a" * 64))

    def test_exact_expiring_suppression_cannot_hide_a_new_finding(self) -> None:
        old_secret = synthetic("ghp", "_", "A1" * 18)
        new_secret = synthetic("ghp", "_", "B2" * 18)
        suppression = {
            "detector_id": "credential.github.legacy-token",
            "path": "fixture.txt",
            "fingerprint": finding_fingerprint(
                "credential.github.legacy-token", old_secret.encode("utf-8")
            ),
            "owner": "security@example.invalid",
            "rationale": "Synthetic invalid canary during migration",
            "expires": (
                dt.datetime.now(tz=dt.UTC).date() + dt.timedelta(days=1)
            ).isoformat(),
        }
        findings, _, suppressed = scan_all(
            (item("fixture.txt", old_secret),),
            policy(suppressions=(suppression,)),
            1024 * 1024,
        )
        self.assertEqual(findings, [])
        self.assertEqual(suppressed, 1)

        findings, _, suppressed = scan_all(
            (item("fixture.txt", new_secret),),
            policy(suppressions=(suppression,)),
            1024 * 1024,
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(suppressed, 0)

    def test_policy_requires_exact_scope_owner_rationale_and_future_expiry(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "policy.json"
            base = {
                "schema_version": 1,
                "policy_version": "2099-01-01.1",
                "allowed_ciphertext_paths": [
                    "env/enc/dev.env.enc",
                    "env/enc/prod.env.enc",
                ],
                "repository_secret_names": list(BUILTIN_SECRET_NAMES[:1]),
                "suppressions": [
                    {
                        "detector_id": "credential.test",
                        "path": "fixture.txt",
                        "fingerprint": "sha256:" + "0" * 64,
                        "owner": "security@example.invalid",
                        "rationale": "Synthetic invalid migration fixture",
                        "expires": "2000-01-01",
                    }
                ],
            }
            path.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaisesRegex(GuardError, "expired"):
                load_policy(path)

            del base["suppressions"][0]["owner"]
            path.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaisesRegex(GuardError, "exactly"):
                load_policy(path)

    def test_staged_and_introduced_scopes_read_git_blobs_not_unstaged_content(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "guard@example.invalid"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Guard Test"], cwd=root, check=True
            )
            target = root / "fixture.txt"
            target.write_text("clean\n", encoding="utf-8")
            subprocess.run(["git", "add", "fixture.txt"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            staged_secret = synthetic("ghp", "_", "A1" * 18)
            target.write_text(staged_secret + "\n", encoding="utf-8")
            subprocess.run(["git", "add", "fixture.txt"], cwd=root, check=True)
            target.write_text("unstaged clean replacement\n", encoding="utf-8")
            staged_findings, _, _ = scan_all(staged_inputs(root), policy(), 1024 * 1024)
            self.assertIn(
                "credential.github.legacy-token",
                {finding.detector_id for finding in staged_findings},
            )

            subprocess.run(
                ["git", "commit", "-qm", "synthetic canary"], cwd=root, check=True
            )
            secret_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(["git", "add", "fixture.txt"], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "-qm", "remove synthetic canary"],
                cwd=root,
                check=True,
            )
            tracked_findings, _, _ = scan_all(
                tracked_inputs(root), policy(), 1024 * 1024
            )
            self.assertEqual(tracked_findings, [])

            introduced_findings, _, _ = scan_all(
                introduced_inputs(root, base), policy(), 1024 * 1024
            )
            self.assertIn(
                "credential.github.legacy-token",
                {finding.detector_id for finding in introduced_findings},
            )
            self.assertIn(
                secret_commit,
                {finding.source_sha for finding in introduced_findings},
            )


if __name__ == "__main__":
    unittest.main()
