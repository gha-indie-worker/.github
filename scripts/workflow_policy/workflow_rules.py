from __future__ import annotations

from .model import Finding, Policy, WorkflowModel, make_finding


def lint_workflow_rules(model: WorkflowModel, policy: Policy) -> list[Finding]:
    findings: list[Finding] = []
    if not model.permissions_declared:
        findings.append(make_finding("GHW001", model.path, 1, "top-level permissions is missing"))
    for line, permission, value in model.permission_values:
        if permission.lower() == "write-all" or value.lower() == "write-all":
            findings.append(make_finding("GHW002", model.path, line, "workflow permissions uses write-all"))

    requires_concurrency = bool(model.events & policy.concurrency_events)
    if requires_concurrency and not model.concurrency_declared:
        findings.append(
            make_finding("GHW006", model.path, 1, "event-driven workflow is missing concurrency")
        )
    if model.concurrency_declared:
        if model.concurrency_group is None or model.concurrency_cancel is None:
            findings.append(
                make_finding(
                    "GHW007",
                    model.path,
                    1,
                    "concurrency must declare group and cancel-in-progress",
                )
            )
        else:
            group_line, group = model.concurrency_group
            cancel_line, cancel = model.concurrency_cancel
            if not group:
                findings.append(make_finding("GHW007", model.path, group_line, "concurrency group is empty"))
            lowered_group = group.lower()
            if "secrets." in lowered_group or (
                "github.event." in lowered_group and "github.event_name" not in lowered_group
            ):
                findings.append(
                    make_finding(
                        "GHW008",
                        model.path,
                        group_line,
                        "concurrency group uses an untrusted dynamic value",
                    )
                )
            if cancel.lower() not in {"true", "false"}:
                findings.append(
                    make_finding(
                        "GHW007",
                        model.path,
                        cancel_line,
                        "cancel-in-progress must be the static boolean true or false",
                    )
                )

    if "schedule" in model.events:
        for required in policy.scheduled_env:
            value = model.env.get(required)
            if value is None or not value[1]:
                findings.append(
                    make_finding(
                        "GHW014",
                        model.path,
                        1,
                        f"scheduled workflow is missing non-empty env.{required}",
                    )
                )

    if "pull_request_target" in model.events and policy.deny_pull_request_target:
        findings.append(
            make_finding(
                "GHW009",
                model.path,
                1,
                "pull_request_target is denied unless an exact expiring exception is reviewed",
            )
        )
    return findings
