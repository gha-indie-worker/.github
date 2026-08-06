# Organization-wide coding-agent instructions

Read repository-local instructions first. The managed policy below is the organization minimum; local policy may strengthen it but may not weaken it.

<!-- BEGIN ORESOFTWARE MANAGED BRANCHING AND GITOPS POLICY -->
## Required `dev`/GitFlow/GitOps policy

Read and follow [`BRANCHING_AND_DEPLOYMENT.md`](../BRANCHING_AND_DEPLOYMENT.md) before reviewing, merging, releasing, or deploying changes.

- `dev` is the integration branch; strive for a GitFlow-style branch and promotion model.
- With all configured tests and required checks passing, merge feature/fix PRs into `dev` only when evidence-based AI confidence is strictly greater than **99.1%**.
- Merge `dev` into `main`/`master` only when integration, release, deployment, migration, security, and required checks pass and evidence-based AI confidence is strictly greater than **99.7%**.
- Record the score, evidence, checks, remaining uncertainty, deployment impact, immutable artifact identity, `*-infra` desired-state change, and rollback or roll-forward plan.
- Use the organization's canonical `*-infra` repository, GitHub Actions, immutable artifacts, and GitOps reconciliation for branch-based deployment promotion.
- Required reviews, branch protection, security/compliance gates, and environment approvals always take precedence over any confidence score.
<!-- END ORESOFTWARE MANAGED BRANCHING AND GITOPS POLICY -->

<!-- ore-org-baseline:begin -->
Read and obey [`../agents.md`](../agents.md); the lowercase file is canonical.

At minimum: preserve concurrent work; fetch before editing and before pushing; avoid git rebase in favor of git merge; never use `git stash`, `git reset`, `git clean`, `git filter-repo`, force-push, or another destructive operation without exact authorization; resolve conflicts semantically using the merge base, 3–10 relevant commits, tests, contracts, Linear context, and related repositories; never choose `ours` or `theirs` wholesale; scan for conflict markers; validate affected behavior; and never claim remote completion without authoritative evidence.
<!-- ore-org-baseline:end -->
