# Time-windowed PR governance — standalone Rust evaluator (not yet enforcement)

The Rust engine in `src/lib.rs` evaluates verified GitHub PR snapshots against the **72-hour / 240-hour review windows** for `atto-lang` and `ores-truffle-oreslang`. It is a pure, non-enforcing prototype; no live GitHub App, repository ruleset or required review-policy check is installed by this PR.

## Review contract

| Age from immutable `pull_request.created_at` (UTC) | Reviews required |
| --- | --- |
| `0 <= age < 72h` | Two named humans: authenticated `ORESoftware` (GitHub ID 11139560) and `the1mills` (ID 2148448), plus two independently verified AI family approvals: OpenAI Codex/ChatGPT and Anthropic Claude/Opus |
| `72h <= age < 240h` | Any one independent write-authorized human review **or** one authenticated successful AI-family review. No explicit human override event is required. |
| `age >= 240h` | **Fresh** post-240h approvals from both named humans and both AI families; earlier approvals alone do not count. |

Every counted review must bind the exact current head commit SHA. Newer negative/dismissed, unverified or stale evidence supersedes older approvals. The policy must be recomputed immediately before merging and on head/review/check changes. A reviewer may not approve their own PR; when a required designated human is the author, only an independent authorized substitution can resolve the block. Do not silently waive it.

## Common gate, every age

- GitHub must confirm no merge conflict, not draft, not on hold, no critical risk and all protections satisfied.
- All configured required CI checks must actually succeed on the current exact SHA from expected App IDs. Pending, failed, skipped, neutral, ambiguous, absent or stale CI **does not** count.
- Unresolved changes-requested must be cleared, and approval evidence must be current and verified.
- Never bypass CODEOWNERS, branch protection, rulesets, protected status checks or security hold.
- Detect replay/duplicate reviewer IDs and untrusted evidence; repository identity and current PR age/head are supplied by a trusted integration, not PR-controlled files or labels.

The library models these GitHub facts as booleans and arrays to facilitate deterministic testing. **None of those fields are intrinsically trusted**: an installed integration must verify every assertion against authoritative GitHub APIs, signed webhook events and authenticated AI provenance. Treat false, unknown, or unavailable evidence as blocking. AI families must be independently authenticated; GitHub comments or unverified bot names are not approvals.

## Pending production enforcement

1. Implement or install a trusted least-privilege GitHub App using signed webhook validation and direct GitHub API reads for PR metadata, protections, current mergeability, reviews, and CI.
2. Authenticate OpenAI/Anthropic AI-provider evidence and publish a non-spoofable `review-policy` check bound to the head or merge-queue SHA.
3. Re-evaluate at exactly 72h and 240h, as well as after PR/commit/review/check/label events; fail closed if any evidence cannot be verified.
4. Reconcile native branch-protection/CODEOWNERS requirements in each authorized repository: native fixed reviewer counts cannot express these age windows by themselves.
5. Pilot in report-only mode, test authorization, then enable reviewed check enforcement. Do not disable existing protections without separate authorization.
6. Handle designated-reviewer PR authors via an explicitly approved independent substitution.
7. If source Actions minutes are insufficient, use a token-free mirror on an authorized test organization with source-tree/per-blob SHA verification. Distinguish unit tests from actual GitHub App enforcement.

## Test invocation

```sh
rustc --edition=2021 --deny warnings --test tools/pr-governance/src/lib.rs -o /tmp/pr-governance-tests
/tmp/pr-governance-tests
```

The read-only Actions workflow executes normal and optimized Rust unit tests. **A green workflow verifies this isolated evaluator only; it is not proof of deployed cross-organization review enforcement.**

## Scope

This change does not modify organization rulesets, GitHub App installations, branch protection, source CI, reviewer permissions, or hosted merge governance. The two canonical organization policy files are:
- https://github.com/atto-lang/.github/blob/main/AGENTS.md
- https://github.com/ores-truffle-oreslang/.github/blob/main/AGENTS.md
