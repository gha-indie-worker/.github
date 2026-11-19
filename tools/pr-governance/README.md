# Age-aware PR governance: non-enforcing prototype

The Rust engine in src/lib.rs implements the 72-hour review policy as pure decision logic. No GitHub App or enforcement is deployed by this change.

## Contract

- At or below 72 hours: require valid approvals from ORESoftware (GitHub ID 11139560) AND the1mills (ID 2148448), plus verified independent OpenAI and Anthropic reviews on the exact current head.
- After 72 hours: a designated, independent write-capable human may request an explicit authenticated exception, bound to the exact PR and head SHA. Then require one named human approval and no AI reviews.
- Always: required CI must be successful for the exact current head from expected source App IDs; drafts, stale or dismissed reviews, changes requested, missing or duplicate checks, and self-approval block.
- All existing GitHub branch rules, CODEOWNERS, security gates, merge queues, CI and environment checks remain authoritative. No routine bypass is authorized.

The trusted backend must independently verify PR creation time, current SHA, write permissions, review chronology, AI provider identity/attestations and each required check from GitHub APIs. Only a trusted GitHub App can set the boolean attestation assertions used by the pure evaluator. Never accept PR labels, comments, PR-supplied JSON or untrusted Actions artifacts as verification.

The explicit exception must be created as an authenticated, immutable audit event with actor ID, repository, PR number, timestamp and HEAD SHA. A label alone is insufficient. Crossing 72 hours never implicitly authorizes an exception.

## Pending production integration

1. Build and install a cross-organization GitHub App with least-privilege read permissions and checks:write.
2. Implement webhook signature verification, GitHub API snapshot materialization, AI source App validation, audit event persistence, and a non-spoofable review-policy check.
3. Re-evaluate on checks, reviews, commits, drafts, merge queues, and after the age threshold. Check merge-group CI for the actual merge-group SHA.
4. Run observation-mode pilots in authorized organizations and resolve native ruleset conflicts.
5. Enable reviewed organization/repository rulesets requiring both a minimum native human approval and the named policy App check. Never replace independently mandatory CI with a single aggregate job.
6. Define an additional trusted human reviewer for PRs authored by one of the two named reviewers; self-approval is never permitted.
7. Verify real CI and source-tree integrity when running exact-source private mirrors in alternate organizations.

## Test invocation

rustc --edition=2021 --deny warnings --test tools/pr-governance/src/lib.rs -o /tmp/pr-governance-tests
/tmp/pr-governance-tests

The pinned read-only Actions workflow runs these tests. A passing unit test is not proof that a GitHub App has been installed or that merge enforcement works.

## Scope

This PR does not modify organization rulesets, branch protection, CI requirements, GitHub App installations, reviewer permissions, or existing governance text. The fleet rollout is a separate, reviewed change.
