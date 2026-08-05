#!/usr/bin/env python3
"""Validate gha-indie-worker's public organization governance contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

POLICY_VERSION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.\d+$")
TOKEN_PATTERNS = (
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


class PolicyError(RuntimeError):
    """Raised when organization policy or documentation drifts."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PolicyError(message)


def read_text(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise PolicyError(f"unable to read {path}: {error}") from error
    for pattern in TOKEN_PATTERNS:
        require(
            pattern.search(text) is None,
            f"{path}: credential-shaped material is forbidden",
        )
    require("<<<<<<< " not in text, f"{path}: unresolved Git conflict marker")
    require("=======\n" not in text, f"{path}: unresolved Git conflict marker")
    require(">>>>>>> " not in text, f"{path}: unresolved Git conflict marker")
    return text


def validate(root: Path) -> dict[str, object]:
    policy_path = root / "organization-policy.json"
    governance_path = root / "GOVERNANCE.md"
    review_path = root / "docs" / "REVIEW_GOVERNANCE.md"
    projects_path = root / "docs" / "PROJECTS.md"
    readme_path = root / "README.md"

    policy_text = read_text(policy_path)
    governance = read_text(governance_path)
    review = read_text(review_path)
    projects = read_text(projects_path)
    readme = read_text(readme_path)

    try:
        policy = json.loads(policy_text)
    except json.JSONDecodeError as error:
        raise PolicyError(f"{policy_path}: invalid JSON: {error}") from error

    require(policy.get("schema_version") == 3, "schema_version must remain 3")
    branching = policy.get("branching_and_delivery")
    require(isinstance(branching, dict), "branching_and_delivery must be an object")
    policy_version = branching.get("policy_version")
    require(
        isinstance(policy_version, str) and POLICY_VERSION_RE.fullmatch(policy_version),
        "branching_and_delivery.policy_version must be YYYY-MM-DD.N",
    )

    review_governance = policy.get("review_governance")
    require(isinstance(review_governance, dict), "review_governance must be an object")
    required = {
        "minimum_distinct_write_approvals": 1,
        "minimum_distinct_human_write_identities": 2,
        "self_approval_counts": False,
        "exact_head_merge_required": True,
        "dismiss_stale_approvals_on_head_change": True,
        "required_checks": "pass",
        "routine_admin_bypass": "forbidden",
        "below_capacity_behavior": "block_and_open_governance_issue",
    }
    for key, expected in required.items():
        require(
            review_governance.get(key) == expected,
            f"review_governance.{key} must equal {expected!r}",
        )

    docs = "\n".join((governance, review, projects, readme))
    required_markers = (
        "https://github.com/orgs/gha-indie-worker/projects/1",
        "https://linear.app/denman/project/githubcomgha-indie-worker-941d4102f7dc",
        "gha-indie-worker/gha-clone-server.rs#3",
        "gha-indie-worker/gha-indie-worker.rs#7",
        "distinct write-access reviewer",
        "Never weaken branch protection",
        "semantic",
    )
    for marker in required_markers:
        require(marker in docs, f"organization documentation is missing {marker!r}")

    require(
        "the1mills" in review and "read" in review.lower(),
        "review governance must record the current read-only collaborator audit",
    )
    require(
        "ORESoftware" in review and "admin" in review.lower(),
        "review governance must record the current administrator audit",
    )

    return {
        "schema_version": 1,
        "policy_version": policy_version,
        "minimum_distinct_write_approvals": review_governance[
            "minimum_distinct_write_approvals"
        ],
        "minimum_distinct_human_write_identities": review_governance[
            "minimum_distinct_human_write_identities"
        ],
        "exact_head_merge_required": review_governance["exact_head_merge_required"],
        "organization_project": "https://github.com/orgs/gha-indie-worker/projects/1",
        "linear_project": "https://linear.app/denman/project/githubcomgha-indie-worker-941d4102f7dc",
        "valid": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = validate(args.root.resolve())
    except PolicyError as error:
        print(f"organization policy validation failed: {error}", file=sys.stderr)
        return 1

    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered, encoding="utf-8")
    print(
        "validated organization review governance: "
        f"{report['minimum_distinct_write_approvals']} approval, "
        f"{report['minimum_distinct_human_write_identities']} write identities"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
