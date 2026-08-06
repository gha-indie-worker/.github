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

<!-- ore-org-baseline:begin -->
## Sources of truth

- GitHub is authoritative for source, policy, architecture records, public organization context, reviewed implementation, and immutable commit history.
- [github.com/gha-indie-worker](https://linear.app/denman/project/githubcomgha-indie-worker-941d4102f7dc) is the planning and delivery ledger.
- Repository-local documentation is authoritative for repository-specific behavior and may strengthen this baseline.
- `repository-relationships.manual.json` is authoritative for reviewed public relationship declarations; the generated JSON graph is a deterministic projection.
- The approved private project registry is authoritative for private repository inventory and private-only edges.
- Private member context belongs in an approved private system, such as `.github-private`, never in this public repository.

## Change control

Material policy and architecture changes use issues or pull requests, focused commits, reviewable diffs, tests, and linked planning context. Existing content must be preserved unless a change explicitly supersedes it. Generated and mirrored artifacts must be updated from their authoritative source. Inferred relationship edges remain advisory until reviewed and declared.

Conflicts are resolved semantically with full history and cross-repository context. Destructive operations, history rewrites, force pushes, bypasses, and deletion of shared resources are default-deny and require exact authorization.

## Precedence

A repository may impose stricter requirements. It must not weaken secret handling, non-destructive collaboration, semantic conflict resolution, evidence-backed completion, or required review and checks.
<!-- ore-org-baseline:end -->
