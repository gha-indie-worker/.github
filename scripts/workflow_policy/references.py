from __future__ import annotations

import re

from .model import Finding, Policy, make_finding

HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


def lint_uses(
    reference: str,
    path: str,
    line: int,
    job: str,
    policy: Policy,
) -> list[Finding]:
    if reference.startswith("./"):
        return []
    if reference.startswith("docker://"):
        marker = "@sha256:"
        if marker not in reference:
            return [make_finding("GHW005", path, line, "docker action is not digest-pinned", job)]
        digest = reference.rsplit(marker, 1)[1]
        if len(digest) != policy.docker_digest_length or HEX_RE.fullmatch(digest) is None:
            return [make_finding("GHW005", path, line, "docker action digest is invalid", job)]
        return []
    if "@" not in reference:
        return [make_finding("GHW004", path, line, "external action has no immutable ref", job)]
    ref = reference.rsplit("@", 1)[1]
    if len(ref) != policy.action_sha_length or HEX_RE.fullmatch(ref) is None:
        return [make_finding("GHW004", path, line, "external action ref is not a full commit SHA", job)]
    return []


def is_checkout(reference: str) -> bool:
    return reference.lower().startswith("actions/checkout@")


def is_download_artifact(reference: str) -> bool:
    return reference.lower().startswith("actions/download-artifact@")
