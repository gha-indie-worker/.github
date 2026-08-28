#!/usr/bin/env python3
"""Statically lint GitHub Actions workflows without executing them."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Sequence

from workflow_policy.config import load_exceptions, load_policy
from workflow_policy.lint import apply_exceptions, lint_paths
from workflow_policy.model import WorkflowPolicyError
from workflow_policy.report import build_report, render_text, report_to_sarif

def discover_workflows(root: Path) -> list[Path]:
    workflows = root / ".github" / "workflows"
    return sorted(
        [*workflows.glob("*.yml"), *workflows.glob("*.yaml")],
        key=lambda item: item.as_posix(),
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--policy", type=Path, default=Path("workflow-policy.json"))
    parser.add_argument("--exceptions", type=Path)
    parser.add_argument("--format", choices=("text", "json", "sarif"), default="text")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mode", choices=("audit", "enforce"), default="enforce")
    parser.add_argument("--source-sha")
    parser.add_argument("--repository")
    parser.add_argument("--today", help="ISO date override for deterministic exception tests")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    policy_path = args.policy if args.policy.is_absolute() else root / args.policy
    exception_path = args.exceptions
    if exception_path is not None and not exception_path.is_absolute():
        exception_path = root / exception_path
    try:
        policy = load_policy(policy_path)
        today = date.fromisoformat(args.today) if args.today else date.today()
        exceptions, exception_findings, exceptions_digest = load_exceptions(
            exception_path, today
        )
    except (WorkflowPolicyError, ValueError) as error:
        print(f"workflow policy configuration failed: {error}", file=sys.stderr)
        return 2

    paths = args.paths or discover_workflows(root)
    resolved_paths = [path if path.is_absolute() else root / path for path in paths]
    raw_findings, input_digests = lint_paths(resolved_paths, policy, root)
    findings = apply_exceptions([*raw_findings, *exception_findings], exceptions)
    report = build_report(
        findings,
        policy,
        input_digests,
        exceptions_digest,
        args.source_sha,
        args.repository,
        args.mode,
    )
    if args.format == "json":
        rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    elif args.format == "sarif":
        rendered = json.dumps(report_to_sarif(report), indent=2, sort_keys=True) + "\n"
    else:
        rendered = render_text(report)
    if args.output:
        output = args.output if args.output.is_absolute() else root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    valid = bool(report["summary"]["valid"])
    return 0 if args.mode == "audit" or valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
