# Readiness-cycled PR governance — standalone Rust evaluator (not yet enforcement)

The Rust policy engine in `src/lib.rs` models the merge-first review windows for `atto-lang` and `ores-truffle-oreslang` using **ready-for-review-cycle age**, not raw pull-request age. This PR **does not** install a GitHub App, required status check, cross-repo draft agent, or ruleset enforcement.

## Authoritative readiness cycle

- A PR opened **ready** starts its first cycle at its GitHub creation timestamp.
- A PR opened **draft** starts no review clock until the first verified `ready_for_review` transition.
- A `converted_to_draft` event immediately ends the active cycle. The next `ready_for_review` event starts a **fresh** 72/240-hour review cycle; approvals from the previous cycle are not reusable.
- Neither pushes, rebases, labels, nor ordinary PR updates restart the clock.
- The trusted integration must supply the immutable creation timestamp, original draft status, **complete authenticated ordered** transition history, current draft state and event IDs. Unknown or contradictory histories fail closed. Don't toggle draft merely to avoid renewed reviews.

| Current ready-cycle age | Review requirement |
| --- | --- |
| `0 <= age < 72h` | Both designated humans (`ORESoftware`, GitHub ID 11139560 and `the1mills`, ID 2148448) **plus** verified OpenAI Codex/ChatGPT and Anthropic Claude/Opus reviews |
| `72h <= age < 240h` | One verified independent human or AI approval **and** a fresh attested competing/overlapping PR audit |
| `age >= 240h` | **Fresh** post-240-hour reviews from all four designated parties |

Reviews always bind the current exact head SHA and must be submitted within the current ready cycle. The evaluator enforces the transition boundary at the exact second. Author self-approval, stale approvals and unverifiable reviews do not qualify. A required designated reviewer who authored the PR needs an authorized substitute, not a silent exception.

## Automatic Draft-to-Ready promotion at 72 hours

The **Draft clock** is separate from the Ready review clock:
- If a PR was opened as Draft, its current Draft cycle starts at the original `pull_request.created_at`.
- If a Ready PR was legitimately converted back to Draft, its new Draft cycle starts at the latest verified `converted_to_draft` transition.
- At the first authorized check at or after **72 consecutive hours in that Draft cycle**, automatically mark Ready when substantive required/material CI has **actually succeeded on the exact current head SHA** and there is no blocking label.
- `keep-as-draft` is the canonical persistent block. `not-ready` also blocks promotion. Legacy `keep-draft` remains a blocking alias to prevent unexpected transitions. Holds must not be automatically removed.
- Investigate overlapping Draft/Ready PRs and reconcile implementations rather than discarding unique work. Explicit holds, unresolved critical safety issues or missing authorized permissions still block.
- If tests are missing, failed, skipped, pending or stale, keep the PR in Draft and retry once tests pass. A push/test rerun does not restart a Draft cycle.
- When the automation marks Ready, the Ready review clock starts at **0**, requiring the full initial four-party review until 72 Ready hours elapse. Three Draft days NEVER grant the one-review fast lane.

This evaluator makes an advisory promotion decision but DOES NOT call GitHub to mark Ready or create organization labels. The privileged GitHub integration must re-read exact head, CI, lifecycle events and labels immediately before any transition.

## Fast-lane competing PR audit

The reviewer/merger must search other relevant open PRs (including drafts and interdependent repositories) by files, symbols, features, APIs, issues and diffs. If changes overlap, **update this PR or the competing PR before merge** to preserve useful functionality and tests. An overlap record identifies candidates and explains their disposition (`incorporated`, `updated`, `superseded`, `independent`, or `unresolved`). **Unresolved overlap blocks fast-lane merges.**

The evaluator requires a provider-verified overlap audit bound to current head SHA and the latest trusted open-PR-index snapshot version. Changes to related PRs must invalidate earlier audit snapshots. The Rust model does not conduct remote PR searches itself; a future trusted integration must collect, verify and attach that evidence. As with all input facts, no PR-controlled flag or comment is inherently authoritative.

## Draft triage and safe automatic promotion

Draft PRs do not accrue review age. Agents must routinely assess drafts, finish missing work, resolve semantic conflicts, compare competing work and promote promptly once reviewable. The `evaluate_draft_promotion` function returns a **non-enforcing advisory decision** for a trusted draft recovery agent. It requires: draft state verified against timeline; readiness attested by an authorized source; semantic mergeability; no explicit hold/critical risk; a current verified overlap audit; and no hold label. Full CI required for merging can run after Ready transition.

**Label contract:**

- `keep-draft` — never automatically promote; only an authorized human/owner can remove this persistent hold.
- `not-ready` — never automatically promote while the blocker remains; removal must be authorized.
- Either label also blocks **automatic merge** even if the PR was manually marked ready.
- Optional `overlap-review-needed`, `needs-tests` and `blocked` can guide triage but are not substitutes for authenticated evidence.

The automation must re-read labels from GitHub **immediately before the state transition**, not from a stale workflow payload, and must never automatically clear hold labels. **This PR does not create labels or deploy an automatic draft promoter.**

## Other merge gates

- GitHub must affirm ready status, mergeability, protections and no outstanding blocking reviews, explicit holds, or critical risk.
- All configured required CI checks must succeed on the exact current head/integration SHA from expected App IDs. Missing, skipped, pending, neutral, ambiguous or failing checks block merge.
- Comply with native CODEOWNERS, GitHub branch protection and rulesets; no bypasses to force fast merges.
- An installed GitHub App must independently verify external AI-family attestations, lifecycle evidence, labels, open-PR index, review chronology, and mergeability. All policy facts are **untrusted until verified**.
- Evaluate again on review, SHA, CI, label, competing-PR landscape, draft/ready events, and before the final atomic merge. Use `expected_head_sha` on merge.

## Tests

```sh
rustc --edition=2021 --deny warnings --test tools/pr-governance/src/lib.rs -o /tmp/pr-governance-tests
/tmp/pr-governance-tests
rustc --edition=2021 --deny warnings -O --test tools/pr-governance/src/lib.rs -o /tmp/pr-governance-tests-opt
/tmp/pr-governance-tests-opt
```

The normal and optimized workflow suites cover 72/240-hour exact boundaries, late initial Ready, multiple draft cycles, historic-review invalidation, label holds, draft promotion, stale/unknown overlap evidence, competing-PR reconciliation, CI and review spoofing. A green run verifies **only this deterministic model**.

## Deployment still pending

1. Build a trusted least-privilege GitHub App with authenticated webhook events and full PR-readiness lifecycle reconciliation, plus current label and cross-repo PR-index scans.
2. Provide independently verified OpenAI/Anthropic review evidence; emit a trusted required `review-policy` status bound to head or merge-queue SHA.
3. Implement draft triage and auto-promotion that honors `keep-draft` / `not-ready`, with human-visible disposition for overlapping PRs. Provision label definitions explicitly in each target repo; GitHub labels alone do not implement the behavior.
4. Integrate rulesets, stage in report-only mode and seek separate authorization before changing protections.
5. If original org lacks Actions budget, run exact Git-tree mirrored tests in an authorized alternate org with per-blob SHA verification and no source secrets.

Canonical policies:
- https://github.com/atto-lang/.github/blob/main/AGENTS.md
- https://github.com/ores-truffle-oreslang/.github/blob/main/AGENTS.md
