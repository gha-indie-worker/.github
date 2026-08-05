# Review capacity and protected promotion governance

This document makes the organization’s protected-branch review requirement operational and auditable.

## Canonical planning

- GitHub organization: https://github.com/gha-indie-worker
- GitHub Project: https://github.com/orgs/gha-indie-worker/projects/1
- Linear project: https://linear.app/denman/project/githubcomgha-indie-worker-941d4102f7dc
- Durable blocker issue: https://github.com/gha-indie-worker/.github/issues/7

GitHub is authoritative for repository permissions, pull requests, reviews, checks, merge results, releases, and artifacts. Linear is authoritative for planning, ownership, dependencies, milestones, and status.

## Protected promotions waiting for independent review

| Repository | Pull request | Exact reviewed head | Required action |
|---|---|---|---|
| `gha-indie-worker/gha-clone-server.rs` | `gha-indie-worker/gha-clone-server.rs#3` | `26cc273d1a6c2b25c51d42f4c767baba510aefe3` | One approval from a distinct write-access reviewer, then exact-head merge |
| `gha-indie-worker/gha-indie-worker.rs` | `gha-indie-worker/gha-indie-worker.rs#7` | `5947a405f5a0473cfb6c85d12b13272a2bb558f9` | One approval from a distinct write-access reviewer, then exact-head merge |

The promotions implement a bounded GitHub Actions continuity subset. They do not claim full proprietary GitHub Actions parity. Unsupported expressions, arbitrary marketplace actions, service containers, proprietary token/check/artifact behavior, and other unimplemented semantics remain fail-closed or explicitly unsupported.

## Current collaborator audit

As of August 5, 2026, the repository collaborator API reports:

- `ORESoftware`: `admin` / write-capable; also the author of both promotion pull requests.
- `the1mills`: `read`; review may be useful but cannot satisfy a branch rule requiring a write-access approval.

The organization therefore has only one visible write-capable identity for these repositories. That is a governance-capacity defect, not a reason to weaken branch protection.

## Required remediation

Before the two promotions can merge through their existing protection rules, an organization owner must do one of the following:

1. promote a distinct trusted human reviewer, such as `the1mills`, to write or maintain access after confirming the intended authority; or
2. add another distinct trusted human or team with write/maintain access and responsibility for continuity reviews.

After access is granted, the reviewer must inspect the exact current heads, confirm required checks are green, and submit the approval. If either head changes, the approval must be treated as stale and the new head reviewed.

Never weaken branch protection, count self-approval, dismiss required review, or use routine administrator bypass merely to clear a delivery queue. If the organization falls below two distinct human write-capable identities, protected promotions must remain blocked and the governance issue must stay open.

## Semantic conflict policy

Concurrent changes must be reconciled semantically against the latest default branch. Inspect both sides, the merge base, affected tests/contracts, and relevant recent history. Preserve the intended bounded-continuity and fail-closed semantics from both branches. Never resolve a conflict by blindly selecting all of `ours` or all of `theirs`.

## Verification checklist

- [ ] At least two distinct human identities have write or maintain access.
- [ ] The approver is not the pull-request author.
- [ ] The reviewed head SHA matches the current pull-request head.
- [ ] All required checks pass on that exact head.
- [ ] No branch-protection or review rule was relaxed for the merge.
- [ ] The merge result and resulting `main` SHA are recorded in Linear.
- [ ] GitHub Project issue #7 is updated or closed only after both promotions merge.
