# Organization-wide agent instructions

<!-- BEGIN ORESOFTWARE MANAGED BRANCHING AND GITOPS POLICY -->
## Required `dev`/GitFlow/GitOps policy

Read and follow [`BRANCHING_AND_DEPLOYMENT.md`](BRANCHING_AND_DEPLOYMENT.md) before reviewing, merging, releasing, or deploying changes.

- `dev` is the integration branch; strive for a GitFlow-style branch and promotion model.
- With all configured tests and required checks passing, merge feature/fix PRs into `dev` only when evidence-based AI confidence is strictly greater than **99.1%**.
- Merge `dev` into `main`/`master` only when integration, release, deployment, migration, security, and required checks pass and evidence-based AI confidence is strictly greater than **99.7%**.
- Record the score, evidence, checks, remaining uncertainty, deployment impact, immutable artifact identity, `*-infra` desired-state change, and rollback or roll-forward plan.
- Use the organization's canonical `*-infra` repository, GitHub Actions, immutable artifacts, and GitOps reconciliation for branch-based deployment promotion.
- Required reviews, branch protection, security/compliance gates, and environment approvals always take precedence over any confidence score.
<!-- END ORESOFTWARE MANAGED BRANCHING AND GITOPS POLICY -->
