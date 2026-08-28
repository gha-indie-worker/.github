#!/usr/bin/env python3
"""Detect secret-bearing Git, artifact, and log egress without printing secrets."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = 1
DEFAULT_MAX_FILE_BYTES = 20 * 1024 * 1024
EXAMPLE_ENV_SUFFIXES = (".example", ".sample", ".template")
BUILTIN_SECRET_NAMES = (
    "ACCESS_TOKEN",
    "API_KEY",
    "API_TOKEN",
    "AUTH_TOKEN",
    "CLIENT_SECRET",
    "COOKIE_SECRET",
    "DATABASE_URL",
    "PASSWORD",
    "PRIVATE_KEY",
    "REFRESH_TOKEN",
    "SESSION_SECRET",
)


class GuardError(RuntimeError):
    """Raised for invalid policy or an incomplete scan."""


@dataclass(frozen=True)
class Detector:
    detector_id: str
    pattern: re.Pattern[str]
    secret_group: str | None = None


@dataclass(frozen=True)
class ScanInput:
    path: str
    content: bytes
    source_sha: str
    is_symlink: bool = False


@dataclass(frozen=True)
class Finding:
    detector_id: str
    path: str
    line: int
    source_sha: str
    fingerprint: str


@dataclass(frozen=True)
class Policy:
    policy_version: str
    allowed_ciphertext_paths: frozenset[str]
    repository_secret_names: tuple[str, ...]
    suppressions: tuple[dict[str, str], ...]


STRUCTURED_DETECTORS = (
    Detector(
        "credential.github.legacy-token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    ),
    Detector(
        "credential.github.fine-grained-token",
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    ),
    Detector(
        "credential.linear.api-key",
        re.compile(r"\blin_api_[A-Za-z0-9]{24,}\b"),
    ),
    Detector(
        "credential.aws.access-key-id",
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    ),
    Detector(
        "credential.sendgrid.api-key",
        re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b"),
    ),
    Detector(
        "credential.slack.token",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    ),
    Detector(
        "credential.stripe.live-secret",
        re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b"),
    ),
    Detector(
        "credential.private-key",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"
            r".*?"
            r"-----END (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    Detector(
        "credential.private-key-header",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    ),
    Detector(
        "credential.connection-string-userinfo",
        re.compile(
            r"\b[a-z][a-z0-9+.-]{1,20}://[^\s/:@]{1,128}:"
            r"(?P<secret>[^\s/@]{8,})@",
            re.IGNORECASE,
        ),
        "secret",
    ),
    Detector(
        "credential.signed-url",
        re.compile(
            r"(?:[?&](?:X-Amz-Signature|X-Goog-Signature|Signature|sig|token)=)"
            r"(?P<secret>[A-Za-z0-9%_+./=-]{16,})",
            re.IGNORECASE,
        ),
        "secret",
    ),
    Detector(
        "credential.authorization-header",
        re.compile(
            r"\bAuthorization\s*:\s*(?:Bearer|Basic)\s+"
            r"(?P<secret>[A-Za-z0-9%_+./=-]{16,})",
            re.IGNORECASE,
        ),
        "secret",
    ),
    Detector(
        "credential.session-cookie",
        re.compile(
            r"\b(?:Cookie|Set-Cookie)\s*:\s*[^\r\n=;]{1,80}="
            r"(?P<secret>[^\s;]{16,})",
            re.IGNORECASE,
        ),
        "secret",
    ),
)
ENTROPY_REQUIRED_DETECTORS = frozenset(
    (
        "credential.authorization-header",
        "credential.connection-string-userinfo",
        "credential.secret-assignment",
        "credential.session-cookie",
        "credential.signed-url",
    )
)


def run_git(root: Path, *args: str, text: bool = False) -> bytes | str:
    process = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=text,
    )
    if process.returncode != 0:
        stderr = process.stderr.strip()
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        raise GuardError(f"git {' '.join(args)} failed: {stderr}")
    return process.stdout


def git_root(path: Path) -> Path:
    process = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=path,
        check=False,
        capture_output=True,
        text=True,
    )
    if process.returncode != 0:
        raise GuardError("the selected scope requires a Git repository")
    return Path(process.stdout.strip()).resolve()


def normalized_path(value: str) -> str:
    normalized = PurePosixPath(value.replace("\\", "/")).as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


def content_sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def finding_fingerprint(detector_id: str, secret: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(detector_id.encode("utf-8"))
    digest.update(b"\0")
    digest.update(secret)
    return f"sha256:{digest.hexdigest()}"


def load_policy(path: Path) -> Policy:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GuardError(f"unable to load policy {path}: {error}") from error

    if raw.get("schema_version") != SCHEMA_VERSION:
        raise GuardError(f"policy schema_version must be {SCHEMA_VERSION}")
    policy_version = raw.get("policy_version")
    if not isinstance(policy_version, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}\.\d+", policy_version
    ):
        raise GuardError("policy_version must use YYYY-MM-DD.N")

    allowed = raw.get("allowed_ciphertext_paths")
    if not isinstance(allowed, list) or not all(
        isinstance(item, str) for item in allowed
    ):
        raise GuardError("allowed_ciphertext_paths must be a string array")
    normalized_allowed = frozenset(normalized_path(item) for item in allowed)
    required = frozenset(("env/enc/dev.env.enc", "env/enc/prod.env.enc"))
    if normalized_allowed != required:
        raise GuardError(
            "allowed_ciphertext_paths must contain only canonical dev/prod SOPS paths"
        )

    names = raw.get("repository_secret_names", [])
    if not isinstance(names, list) or not all(
        isinstance(item, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item)
        for item in names
    ):
        raise GuardError("repository_secret_names must contain environment-style names")

    suppressions = raw.get("suppressions", [])
    if not isinstance(suppressions, list):
        raise GuardError("suppressions must be an array")
    required_suppression = {
        "detector_id",
        "path",
        "fingerprint",
        "owner",
        "rationale",
        "expires",
    }
    today = dt.datetime.now(tz=dt.UTC).date()
    checked_suppressions: list[dict[str, str]] = []
    for index, suppression in enumerate(suppressions):
        if (
            not isinstance(suppression, dict)
            or set(suppression) != required_suppression
        ):
            raise GuardError(
                f"suppression {index} must have exactly {sorted(required_suppression)}"
            )
        if not all(
            isinstance(value, str) and value.strip() for value in suppression.values()
        ):
            raise GuardError(f"suppression {index} values must be non-empty strings")
        if not re.fullmatch(r"[a-z0-9.-]+", suppression["detector_id"]):
            raise GuardError(f"suppression {index} detector_id is invalid")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", suppression["fingerprint"]):
            raise GuardError(
                f"suppression {index} fingerprint must be a SHA-256 digest"
            )
        try:
            expires = dt.date.fromisoformat(suppression["expires"])
        except ValueError as error:
            raise GuardError(
                f"suppression {index} expires must be YYYY-MM-DD"
            ) from error
        if expires < today:
            raise GuardError(f"suppression {index} expired on {expires.isoformat()}")
        checked = dict(suppression)
        checked["path"] = normalized_path(checked["path"])
        checked_suppressions.append(checked)

    return Policy(
        policy_version=policy_version,
        allowed_ciphertext_paths=normalized_allowed,
        repository_secret_names=tuple(sorted(set(names))),
        suppressions=tuple(checked_suppressions),
    )


def is_plaintext_env_path(path: str) -> bool:
    normalized = normalized_path(path)
    parts = PurePosixPath(normalized).parts
    if len(parts) >= 2 and parts[0:2] == ("env", "dec"):
        return True
    name = parts[-1] if parts else normalized
    lower = name.lower()
    if lower.endswith(EXAMPLE_ENV_SUFFIXES):
        return False
    return lower == ".env" or lower.startswith(".env.") or lower.endswith(".env")


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = {character: value.count(character) for character in set(value)}
    length = len(value)
    return -sum(
        (count / length) * math.log2(count / length) for count in counts.values()
    )


def is_high_confidence_secret(value: str) -> bool:
    if len(value) < 20 or len(value) > 8192:
        return False
    lowered = value.lower()
    if any(
        marker in lowered
        for marker in ("example", "placeholder", "redacted", "changeme")
    ):
        return False
    if re.fullmatch(r"[0-9a-fA-F]{32,128}", value):
        return False
    classes = sum(
        bool(re.search(pattern, value))
        for pattern in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9]")
    )
    return classes >= 3 and shannon_entropy(value) >= 3.5


def secret_assignment_detector(secret_names: Sequence[str]) -> Detector:
    escaped = "|".join(re.escape(name) for name in secret_names)
    return Detector(
        "credential.secret-assignment",
        re.compile(
            rf"(?im)^\s*(?:export\s+)?(?:{escaped})\s*[:=]\s*"
            r"[\"']?(?P<secret>[^\s\"'`;#]{20,})",
            re.IGNORECASE,
        ),
        "secret",
    )


def make_finding(
    detector_id: str,
    scan_input: ScanInput,
    line: int,
    secret: bytes,
) -> Finding:
    return Finding(
        detector_id=detector_id,
        path=normalized_path(scan_input.path),
        line=line,
        source_sha=scan_input.source_sha,
        fingerprint=finding_fingerprint(detector_id, secret),
    )


def scan_input(
    item: ScanInput,
    policy: Policy,
    max_file_bytes: int,
) -> list[Finding]:
    findings: list[Finding] = []
    path = normalized_path(item.path)

    if item.is_symlink:
        findings.append(make_finding("egress.symlink", item, 0, path.encode("utf-8")))
    if path.startswith("env/enc/") and path not in policy.allowed_ciphertext_paths:
        findings.append(
            make_finding(
                "egress.noncanonical-ciphertext-path", item, 0, path.encode("utf-8")
            )
        )
    if is_plaintext_env_path(path):
        findings.append(
            make_finding("egress.plaintext-dotenv-path", item, 0, path.encode("utf-8"))
        )
    if len(item.content) > max_file_bytes:
        findings.append(
            make_finding(
                "egress.file-size-limit",
                item,
                0,
                f"{path}:{len(item.content)}".encode(),
            )
        )
        return findings

    text = item.content.decode("utf-8", errors="replace")
    detectors = (
        *STRUCTURED_DETECTORS,
        secret_assignment_detector(
            (*BUILTIN_SECRET_NAMES, *policy.repository_secret_names)
        ),
    )
    seen: set[tuple[str, int, str]] = set()
    for detector in detectors:
        for match in detector.pattern.finditer(text):
            secret_text = (
                match.group(detector.secret_group)
                if detector.secret_group
                else match.group(0)
            )
            if (
                detector.detector_id in ENTROPY_REQUIRED_DETECTORS
                and not is_high_confidence_secret(secret_text)
            ):
                continue
            line = text.count("\n", 0, match.start()) + 1
            finding = make_finding(
                detector.detector_id,
                item,
                line,
                secret_text.encode("utf-8", errors="replace"),
            )
            key = (finding.detector_id, finding.line, finding.fingerprint)
            if key not in seen:
                findings.append(finding)
                seen.add(key)
    return findings


def split_nul(raw: bytes) -> list[str]:
    return [
        entry.decode("utf-8", errors="surrogateescape")
        for entry in raw.split(b"\0")
        if entry
    ]


def git_blob_input(
    root: Path,
    revision: str,
    path: str,
    *,
    source_sha: str | None = None,
) -> ScanInput:
    content = run_git(root, "show", f"{revision}:{path}")
    assert isinstance(content, bytes)
    metadata = run_git(root, "ls-tree", revision, "--", path, text=True)
    assert isinstance(metadata, str)
    fields = metadata.split(maxsplit=3) if metadata.strip() else []
    mode = fields[0] if fields else ""
    blob_sha = fields[2] if len(fields) >= 3 else content_sha(content)
    return ScanInput(
        path=path,
        content=content,
        source_sha=source_sha or blob_sha,
        is_symlink=mode == "120000",
    )


def staged_blob_input(root: Path, path: str) -> ScanInput:
    content = run_git(root, "show", f":{path}")
    assert isinstance(content, bytes)
    metadata = run_git(root, "ls-files", "--stage", "--", path, text=True)
    assert isinstance(metadata, str)
    fields = metadata.split(maxsplit=3) if metadata.strip() else []
    mode = fields[0] if fields else ""
    blob_sha = fields[1] if len(fields) >= 2 else content_sha(content)
    return ScanInput(
        path=path,
        content=content,
        source_sha=blob_sha,
        is_symlink=mode == "120000",
    )


def tracked_inputs(root: Path) -> Iterable[ScanInput]:
    raw = run_git(root, "ls-files", "-z")
    assert isinstance(raw, bytes)
    for path in split_nul(raw):
        absolute = root / path
        try:
            is_symlink = absolute.is_symlink()
            content = (
                os.readlink(absolute).encode("utf-8", errors="surrogateescape")
                if is_symlink
                else absolute.read_bytes()
            )
        except OSError as error:
            raise GuardError(f"unable to read tracked path {path}: {error}") from error
        yield ScanInput(
            path=path,
            content=content,
            source_sha=content_sha(content),
            is_symlink=is_symlink,
        )


def staged_inputs(root: Path) -> Iterable[ScanInput]:
    raw = run_git(
        root,
        "diff",
        "--cached",
        "--name-only",
        "--diff-filter=ACMR",
        "-z",
    )
    assert isinstance(raw, bytes)
    for path in split_nul(raw):
        yield staged_blob_input(root, path)


def introduced_inputs(root: Path, base_ref: str) -> Iterable[ScanInput]:
    run_git(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
    commits_raw = run_git(root, "rev-list", "--reverse", f"{base_ref}..HEAD", text=True)
    assert isinstance(commits_raw, str)
    for commit in commits_raw.splitlines():
        for path in commit_changed_paths(root, commit):
            yield git_blob_input(root, commit, path, source_sha=commit)


def commit_changed_paths(root: Path, commit: str) -> list[str]:
    paths_raw = run_git(
        root,
        "diff-tree",
        "--root",
        "--no-commit-id",
        "--name-only",
        "--diff-filter=ACMR",
        "-r",
        "-z",
        commit,
    )
    assert isinstance(paths_raw, bytes)
    return split_nul(paths_raw)


def history_inputs(root: Path, depth: int) -> Iterable[ScanInput]:
    if depth < 1 or depth > 500:
        raise GuardError("history depth must be between 1 and 500")
    commits_raw = run_git(root, "rev-list", f"--max-count={depth}", "HEAD", text=True)
    assert isinstance(commits_raw, str)
    for commit in commits_raw.splitlines():
        for path in commit_changed_paths(root, commit):
            yield git_blob_input(root, commit, path, source_sha=commit)


def filesystem_inputs(root: Path, selected: Sequence[Path]) -> Iterable[ScanInput]:
    for chosen in selected:
        absolute = chosen if chosen.is_absolute() else root / chosen
        if not absolute.exists() and not absolute.is_symlink():
            raise GuardError(f"scan path does not exist: {chosen}")
        candidates = [absolute]
        if absolute.is_dir() and not absolute.is_symlink():
            candidates = sorted(
                path
                for path in absolute.rglob("*")
                if ".git" not in path.parts and (path.is_file() or path.is_symlink())
            )
        for path in candidates:
            if path.is_dir() and not path.is_symlink():
                continue
            try:
                is_symlink = path.is_symlink()
                content = (
                    os.readlink(path).encode("utf-8", errors="surrogateescape")
                    if is_symlink
                    else path.read_bytes()
                )
            except OSError as error:
                raise GuardError(f"unable to read scan path {path}: {error}") from error
            try:
                display_path = path.relative_to(root).as_posix()
            except ValueError:
                display_path = path.name
            yield ScanInput(
                path=display_path,
                content=content,
                source_sha=content_sha(content),
                is_symlink=is_symlink,
            )


def is_suppressed(finding: Finding, policy: Policy) -> bool:
    for suppression in policy.suppressions:
        if (
            suppression["detector_id"] == finding.detector_id
            and suppression["path"] == finding.path
            and suppression["fingerprint"] == finding.fingerprint
        ):
            return True
    return False


def scan_all(
    inputs: Iterable[ScanInput],
    policy: Policy,
    max_file_bytes: int,
) -> tuple[list[Finding], int, int]:
    findings: list[Finding] = []
    input_count = 0
    suppressed_count = 0
    for item in inputs:
        input_count += 1
        for finding in scan_input(item, policy, max_file_bytes):
            if is_suppressed(finding, policy):
                suppressed_count += 1
            else:
                findings.append(finding)
    findings.sort(
        key=lambda finding: (
            finding.path,
            finding.line,
            finding.detector_id,
            finding.fingerprint,
        )
    )
    return findings, input_count, suppressed_count


def render_human(
    findings: Sequence[Finding],
    input_count: int,
    suppressed_count: int,
    policy: Policy,
) -> str:
    if not findings:
        return (
            "credential egress guard: clean "
            f"({input_count} inputs, {suppressed_count} exact suppressions, "
            f"policy {policy.policy_version})"
        )
    lines = [
        "credential egress guard: blocked; matched values are intentionally redacted",
    ]
    for finding in findings:
        location = f"{finding.path}:{finding.line}" if finding.line else finding.path
        lines.append(
            f"{finding.detector_id} {location} source={finding.source_sha} "
            f"fingerprint={finding.fingerprint}"
        )
    lines.append(
        f"{len(findings)} finding(s) across {input_count} inputs; "
        f"{suppressed_count} exact suppression(s)"
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scope",
        choices=("tracked", "staged", "introduced", "paths", "history"),
        default="tracked",
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--base-ref")
    parser.add_argument("--path", action="append", type=Path, default=[])
    parser.add_argument("--history-depth", type=int)
    parser.add_argument("--max-file-bytes", type=int, default=DEFAULT_MAX_FILE_BYTES)
    parser.add_argument("--format", choices=("human", "json"), default="human")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        root = args.root.resolve()
        if args.scope != "paths":
            root = git_root(root)
        policy_path = args.policy or root / "credential-egress-policy.json"
        policy = load_policy(policy_path.resolve())
        if args.max_file_bytes < 1:
            raise GuardError("max-file-bytes must be positive")

        if args.scope == "tracked":
            inputs = tracked_inputs(root)
        elif args.scope == "staged":
            inputs = staged_inputs(root)
        elif args.scope == "introduced":
            if not args.base_ref:
                raise GuardError("--base-ref is required for introduced scope")
            inputs = introduced_inputs(root, args.base_ref)
        elif args.scope == "history":
            if args.history_depth is None:
                raise GuardError(
                    "--history-depth is required for explicit incident scans"
                )
            inputs = history_inputs(root, args.history_depth)
        else:
            if not args.path:
                raise GuardError("at least one --path is required for paths scope")
            inputs = filesystem_inputs(root, args.path)

        findings, input_count, suppressed_count = scan_all(
            inputs,
            policy,
            args.max_file_bytes,
        )
    except GuardError as error:
        print(f"credential egress guard failed closed: {error}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "policy_version": policy.policy_version,
                    "valid": not findings,
                    "input_count": input_count,
                    "suppressed_count": suppressed_count,
                    "findings": [asdict(finding) for finding in findings],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(render_human(findings, input_count, suppressed_count, policy))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
