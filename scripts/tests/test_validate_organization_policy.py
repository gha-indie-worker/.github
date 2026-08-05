from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from validate_organization_policy import PolicyError, validate  # noqa: E402


class OrganizationPolicyTests(unittest.TestCase):
    def copy_fixture(self, target: Path) -> None:
        for relative in (
            "organization-policy.json",
            "GOVERNANCE.md",
            "README.md",
            "docs/PROJECTS.md",
            "docs/REVIEW_GOVERNANCE.md",
        ):
            source = ROOT / relative
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)

    def test_committed_policy_is_valid(self) -> None:
        report = validate(ROOT)
        self.assertTrue(report["valid"])
        self.assertEqual(report["minimum_distinct_write_approvals"], 1)
        self.assertEqual(report["minimum_distinct_human_write_identities"], 2)
        self.assertTrue(report["exact_head_merge_required"])

    def test_self_approval_cannot_be_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.copy_fixture(root)
            path = root / "organization-policy.json"
            policy = json.loads(path.read_text(encoding="utf-8"))
            policy["review_governance"]["self_approval_counts"] = True
            path.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaisesRegex(PolicyError, "self_approval_counts"):
                validate(root)

    def test_review_capacity_cannot_be_reduced_to_one_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.copy_fixture(root)
            path = root / "organization-policy.json"
            policy = json.loads(path.read_text(encoding="utf-8"))
            policy["review_governance"]["minimum_distinct_human_write_identities"] = 1
            path.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaisesRegex(PolicyError, "minimum_distinct_human_write_identities"):
                validate(root)

    def test_project_and_linear_links_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.copy_fixture(root)
            for relative in (
                "GOVERNANCE.md",
                "README.md",
                "docs/PROJECTS.md",
                "docs/REVIEW_GOVERNANCE.md",
            ):
                path = root / relative
                path.write_text(
                    path.read_text(encoding="utf-8").replace(
                        "https://github.com/orgs/gha-indie-worker/projects/1",
                        "https://example.invalid/project",
                    ),
                    encoding="utf-8",
                )
            with self.assertRaisesRegex(PolicyError, "projects/1"):
                validate(root)

    def test_credential_shaped_material_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.copy_fixture(root)
            path = root / "docs/REVIEW_GOVERNANCE.md"
            path.write_text(
                path.read_text(encoding="utf-8")
                + "\nforbidden example: ghp_"
                + "a" * 30
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(PolicyError, "credential-shaped"):
                validate(root)

    def test_conflict_markers_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.copy_fixture(root)
            path = root / "GOVERNANCE.md"
            path.write_text(
                path.read_text(encoding="utf-8")
                + "\n<<<<<<< ours\n=======\n>>>>>>> theirs\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(PolicyError, "conflict marker"):
                validate(root)


if __name__ == "__main__":
    unittest.main()
