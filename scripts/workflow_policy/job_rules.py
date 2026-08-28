from __future__ import annotations

from .model import Finding, Policy, WorkflowModel, make_finding
from .permissions import has_write_permission
from .references import is_checkout, is_download_artifact, lint_uses

DANGEROUS_SHELL_EXPRESSIONS = (
    "github.event.pull_request.title",
    "github.event.pull_request.body",
    "github.event.issue.title",
    "github.event.issue.body",
    "github.event.comment.body",
    "github.event.review.body",
    "github.event.review_comment.body",
    "github.head_ref",
)
UNTRUSTED_EVENTS = frozenset({"pull_request", "pull_request_target"})


def lint_job_rules(model: WorkflowModel, policy: Policy) -> list[Finding]:
    findings: list[Finding] = []
    workflow_writes = has_write_permission(model.permission_values)
    for job in model.jobs.values():
        for line, permission, value in job.permission_values:
            if permission.lower() == "write-all" or value.lower() == "write-all":
                findings.append(
                    make_finding("GHW002", model.path, line, "job permissions uses write-all", job.name)
                )
        if job.executable and job.reusable_uses is None and job.timeout_line is None:
            findings.append(
                make_finding("GHW003", model.path, job.line, "job is missing timeout-minutes", job.name)
            )
        if job.reusable_uses is not None:
            findings.extend(lint_uses(job.reusable_uses, model.path, job.line, job.name, policy))
        if (
            model.events & UNTRUSTED_EVENTS
            and job.self_hosted
            and policy.deny_untrusted_self_hosted
        ):
            findings.append(
                make_finding(
                    "GHW010",
                    model.path,
                    job.line,
                    "untrusted pull-request event targets a self-hosted runner",
                    job.name,
                )
            )
        job_writes = has_write_permission(job.permission_values)
        if model.events & UNTRUSTED_EVENTS and (
            workflow_writes or job_writes or job.environment_lines or job.secrets_inherit_lines
        ):
            line = (
                job.environment_lines[0]
                if job.environment_lines
                else job.secrets_inherit_lines[0]
                if job.secrets_inherit_lines
                else job.line
            )
            findings.append(
                make_finding(
                    "GHW011",
                    model.path,
                    line,
                    "untrusted pull-request path receives write permissions, an environment, or inherited secrets",
                    job.name,
                )
            )
        for line in job.secrets_inherit_lines:
            findings.append(
                make_finding("GHW013", model.path, line, "secrets: inherit is forbidden", job.name)
            )
        for step in job.steps:
            if step.uses:
                findings.extend(lint_uses(step.uses, model.path, step.line, job.name, policy))
                if is_checkout(step.uses) and policy.require_checkout_persist_credentials_false:
                    value = step.with_values.get("persist-credentials")
                    if value is None or value.lower() != "false":
                        findings.append(
                            make_finding(
                                "GHW015",
                                model.path,
                                step.line,
                                "actions/checkout must set persist-credentials: false",
                                job.name,
                            )
                        )
                if "pull_request_target" in model.events and is_download_artifact(step.uses):
                    findings.append(
                        make_finding(
                            "GHW016",
                            model.path,
                            step.line,
                            "pull_request_target cannot download artifacts without an exception",
                            job.name,
                        )
                    )
            for line, command in step.run_lines:
                lowered = command.lower()
                if any(expression in lowered for expression in DANGEROUS_SHELL_EXPRESSIONS):
                    findings.append(
                        make_finding(
                            "GHW012",
                            model.path,
                            line,
                            "attacker-controlled event text is interpolated directly into shell",
                            job.name,
                        )
                    )
    return findings
