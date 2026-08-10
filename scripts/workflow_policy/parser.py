from __future__ import annotations

import re

from .model import Job, Step, WorkflowModel, make_finding

KEY_VALUE_RE = re.compile(
    r"^(?P<key>'[^']+'|\"[^\"]+\"|[A-Za-z0-9_.${}-]+)\s*:\s*(?P<value>.*)$"
)

def _strip_comment(line: str) -> str:
    single = False
    double = False
    escaped = False
    for index, character in enumerate(line):
        if escaped:
            escaped = False
            continue
        if character == "\\" and double:
            escaped = True
            continue
        if character == "'" and not double:
            single = not single
            continue
        if character == '"' and not single:
            double = not double
            continue
        if character == "#" and not single and not double and (index == 0 or line[index - 1].isspace()):
            return line[:index].rstrip()
    return line.rstrip()


def _key_value(content: str) -> tuple[str, str] | None:
    candidate = content[2:].lstrip() if content.startswith("- ") else content
    match = KEY_VALUE_RE.match(candidate)
    if not match:
        return None
    key = match.group("key")
    if (key.startswith("'") and key.endswith("'")) or (
        key.startswith('"') and key.endswith('"')
    ):
        key = key[1:-1]
    return key, match.group("value").strip()


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _inline_list(value: str) -> list[str]:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        return [_unquote(item.strip()) for item in value[1:-1].split(",") if item.strip()]
    return [_unquote(value)] if value else []


def _inline_map(value: str) -> dict[str, str]:
    value = value.strip()
    if not (value.startswith("{") and value.endswith("}")):
        return {}
    result: dict[str, str] = {}
    for item in value[1:-1].split(","):
        parsed = _key_value(item.strip())
        if parsed:
            result[parsed[0]] = parsed[1]
    return result


def parse_workflow(text: str, path: str) -> WorkflowModel:
    model = WorkflowModel(path=path)
    lines = text.splitlines()
    top_section: str | None = None
    current_job: Job | None = None
    current_job_property: str | None = None
    current_step: Step | None = None
    current_step_property: str | None = None
    run_block_indent: int | None = None

    for number, raw_line in enumerate(lines, 1):
        if raw_line.startswith("\t") or (raw_line[: len(raw_line) - len(raw_line.lstrip())].find("\t") >= 0):
            model.syntax_findings.append(
                make_finding("GHW000", path, number, "tabs are not supported in workflow indentation")
            )
            continue
        without_comment = _strip_comment(raw_line)
        if not without_comment.strip():
            continue
        indent = len(without_comment) - len(without_comment.lstrip(" "))
        content = without_comment[indent:]

        if run_block_indent is not None:
            if indent > run_block_indent:
                if current_step is not None:
                    current_step.run_lines.append((number, content))
                continue
            run_block_indent = None

        if content in {"---", "..."}:
            continue
        if content.startswith(("&", "*", "!")) or "<<:" in content:
            model.syntax_findings.append(
                make_finding(
                    "GHW000",
                    path,
                    number,
                    "YAML anchors, aliases, tags, and merge keys require explicit review",
                    current_job.name if current_job else None,
                )
            )

        parsed = _key_value(content)
        if indent == 0:
            current_job = None
            current_job_property = None
            current_step = None
            current_step_property = None
            if parsed is None:
                model.syntax_findings.append(
                    make_finding("GHW000", path, number, "top-level workflow entry is not a key")
                )
                top_section = None
                continue
            key, value = parsed
            top_section = key
            if key == "on":
                model.events.update(_inline_list(value))
            elif key == "permissions":
                model.permissions_declared = True
                if value:
                    inline = _inline_map(value)
                    if inline:
                        for permission, setting in inline.items():
                            model.permission_values.append((number, permission, _unquote(setting)))
                    else:
                        model.permission_values.append((number, "*", _unquote(value)))
            elif key == "concurrency":
                model.concurrency_declared = True
                if value:
                    inline = _inline_map(value)
                    if inline:
                        if "group" in inline:
                            model.concurrency_group = (number, _unquote(inline["group"]))
                        if "cancel-in-progress" in inline:
                            model.concurrency_cancel = (
                                number,
                                _unquote(inline["cancel-in-progress"]),
                            )
                    else:
                        model.concurrency_group = (number, _unquote(value))
            continue

        if top_section == "on":
            if indent == 2 and parsed is not None:
                model.events.add(parsed[0])
            continue
        if top_section == "permissions":
            if indent == 2 and parsed is not None:
                model.permission_values.append((number, parsed[0], _unquote(parsed[1])))
            continue
        if top_section == "concurrency":
            if indent == 2 and parsed is not None:
                key, value = parsed
                if key == "group":
                    model.concurrency_group = (number, _unquote(value))
                elif key == "cancel-in-progress":
                    model.concurrency_cancel = (number, _unquote(value))
            continue
        if top_section == "env":
            if indent == 2 and parsed is not None:
                model.env[parsed[0]] = (number, _unquote(parsed[1]))
            continue
        if top_section != "jobs":
            continue

        if indent == 2 and parsed is not None and not content.startswith("- "):
            name, _value = parsed
            current_job = Job(name=name, line=number)
            model.jobs[name] = current_job
            current_job_property = None
            current_step = None
            current_step_property = None
            continue
        if current_job is None:
            model.syntax_findings.append(
                make_finding("GHW000", path, number, "job property appears before a job identifier")
            )
            continue

        if indent == 4 and parsed is not None:
            key, value = parsed
            current_job_property = key
            current_step = None
            current_step_property = None
            if key == "timeout-minutes":
                current_job.timeout_line = number
            elif key == "uses":
                current_job.reusable_uses = _unquote(value)
            elif key == "runs-on":
                current_job.runs_on.extend(_inline_list(value))
            elif key == "permissions" and value:
                inline = _inline_map(value)
                if inline:
                    for permission, setting in inline.items():
                        current_job.permission_values.append(
                            (number, permission, _unquote(setting))
                        )
                else:
                    current_job.permission_values.append((number, "*", _unquote(value)))
            elif key == "environment":
                current_job.environment_lines.append(number)
            elif key == "secrets" and _unquote(value).lower() == "inherit":
                current_job.secrets_inherit_lines.append(number)
            continue

        if current_job_property == "runs-on" and indent >= 6 and content.startswith("- "):
            current_job.runs_on.append(_unquote(content[2:].strip()))
            continue
        if current_job_property == "permissions" and indent == 6 and parsed is not None:
            current_job.permission_values.append((number, parsed[0], _unquote(parsed[1])))
            continue
        if current_job_property == "secrets" and parsed is not None:
            if parsed[0] == "inherit" or _unquote(parsed[1]).lower() == "inherit":
                current_job.secrets_inherit_lines.append(number)
            continue
        if current_job_property != "steps":
            if parsed is not None and parsed[0] == "secrets" and _unquote(parsed[1]).lower() == "inherit":
                current_job.secrets_inherit_lines.append(number)
            continue

        if indent == 6 and content.startswith("- "):
            current_step = Step(line=number)
            current_job.steps.append(current_step)
            current_step_property = None
            step_parsed = _key_value(content)
            if step_parsed is not None:
                key, value = step_parsed
                current_step_property = key
                if key == "uses":
                    current_step.uses = _unquote(value)
                elif key == "run":
                    if value in {"|", "|-", "|+", ">", ">-", ">+"}:
                        run_block_indent = indent
                    else:
                        current_step.run_lines.append((number, value))
            continue
        if current_step is None:
            model.syntax_findings.append(
                make_finding("GHW000", path, number, "step property appears before a list item", current_job.name)
            )
            continue
        if indent == 8 and parsed is not None:
            key, value = parsed
            current_step_property = key
            if key == "uses":
                current_step.uses = _unquote(value)
            elif key == "run":
                if value in {"|", "|-", "|+", ">", ">-", ">+"}:
                    run_block_indent = indent
                else:
                    current_step.run_lines.append((number, value))
            continue
        if current_step_property == "with" and indent >= 10 and parsed is not None:
            current_step.with_values[parsed[0]] = _unquote(parsed[1])

    return model


