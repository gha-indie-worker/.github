# Governance

Organization owners are accountable for repository creation, visibility, access, archival, and durable cross-repository policy. Repository maintainers own implementation quality and release decisions within published contracts.

## Durable engineering policy

- This repository defines public organization-wide defaults for `gha-indie-worker`.
- Never commit credentials, private keys, access tokens, customer data, or private-repository inventories.
- Resolve Git conflicts semantically: inspect both sides, the merge base, nearby tests and contracts, and normally 3–10 relevant prior commits. Never blindly select all of `ours` or all of `theirs`.
- Prefer focused pull requests, explicit validation, non-destructive Git operations, and documented tradeoffs.
- Cross-repository integration uses versioned interfaces, APIs, SDKs, events, or explicitly owned replicated read models. Services do not reach into another service's database by default.
- `*-infra` repositories and `*-monorepo` application source remain separate. A `*-infra` repository must never appear as a Git submodule under `*-monorepo/apps`.
- Git submodules are reserved for explicitly coordinated editable source composition. Zed packages or immutable artifacts are preferred for package dependencies. Production deploys immutable artifacts or OCI digests, not source clones.

## Protected review capacity

Protected promotion branches require at least one approval from a distinct write-access reviewer. The pull-request author cannot satisfy that requirement through self-approval, and routine administrator bypass is forbidden. Merge automation must verify the exact current head SHA and required checks before merging; a changed head invalidates earlier approval evidence.

The organization must maintain at least two distinct human identities with write or maintain access so required review is operational rather than ceremonial. If review capacity falls below that threshold, affected promotions remain blocked and a governance issue is opened or kept active. Never weaken branch protection merely to clear a queue.

Current review-capacity evidence, the exact blocked promotions, GitHub Project routing, Linear ownership, and the remediation checklist are maintained in [`docs/REVIEW_GOVERNANCE.md`](docs/REVIEW_GOVERNANCE.md). The canonical planning surfaces are:

- GitHub Project: https://github.com/orgs/gha-indie-worker/projects/1
- Linear project: https://linear.app/denman/project/githubcomgha-indie-worker-941d4102f7dc

Material architecture and governance decisions should be documented in the owning repository and reflected in interfaces, tests, deployment ownership, review evidence, and observability expectations.
