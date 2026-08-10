from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, Sequence

from .job_rules import lint_job_rules
from .model import ExceptionRule, Finding, Policy, WorkflowModel, make_finding
from .parser import parse_workflow
from .workflow_rules import lint_workflow_rules


def lint_model(model: WorkflowModel, policy: Policy) -> list[Finding]:
    findings = list(model.syntax_findings)
    findings.extend(lint_workflow_rules(model, policy))
    findings.extend(lint_job_rules(model, policy))
    return sorted(_deduplicate(findings), key=Finding.sort_key)


def _deduplicate(findings: Iterable[Finding]) -> list[Finding]:
    unique: dict[tuple[object, ...], Finding] = {}
    for finding in findings:
        unique[finding.sort_key()] = finding
    return list(unique.values())


def apply_exceptions(
    findings: Sequence[Finding],
    exceptions: Sequence[ExceptionRule],
) -> list[Finding]:
    result: list[Finding] = []
    for finding in findings:
        matching = next((item for item in exceptions if item.matches(finding)), None)
        if matching is None:
            result.append(finding)
        else:
            result.append(
                Finding(
                    finding.rule_id,
                    finding.level,
                    finding.path,
                    finding.line,
                    finding.message,
                    finding.job,
                    suppressed=True,
                    exception_owner=matching.owner,
                    exception_expires=matching.expires.isoformat(),
                )
            )
    return result


def lint_paths(
    paths: Sequence[Path],
    policy: Policy,
    root: Path | None = None,
) -> tuple[list[Finding], dict[str, str]]:
    findings: list[Finding] = []
    digests: dict[str, str] = {}
    resolved_root = root.resolve() if root is not None else None
    for path in sorted(paths, key=lambda item: item.as_posix()):
        resolved_path = path.resolve()
        if resolved_root is not None:
            try:
                rendered_path = resolved_path.relative_to(resolved_root).as_posix()
            except ValueError:
                rendered_path = resolved_path.as_posix()
        else:
            rendered_path = path.as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            findings.append(
                make_finding("GHW000", rendered_path, 1, f"unable to read workflow: {error}")
            )
            continue
        digests[rendered_path] = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
        findings.extend(lint_model(parse_workflow(text, rendered_path), policy))
    return sorted(_deduplicate(findings), key=Finding.sort_key), dict(sorted(digests.items()))
