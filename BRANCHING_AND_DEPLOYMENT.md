# Branching, merge-confidence, and GitOps deployment policy

This document defines the default branching and delivery contract for repositories in this owner account.

<!-- BEGIN ORESOFTWARE MANAGED BRANCHING AND GITOPS POLICY -->
## Mandatory branching, merge-confidence, and GitOps policy

Policy version: `2026-08-05.1`.

### Branch names and GitFlow

- **`dev` is the integration branch.** Feature, fix, refactor, and routine dependency branches must normally branch from `dev` and open pull requests back into `dev`.
- The repository's existing **`main` or `master` branch is the production/release branch**. Do not rename a repository's production branch merely to satisfy this policy; document which of the two names that repository uses.
- Strive for a GitFlow-style model: `feature/*`, `fix/*`, and similar short-lived branches flow into `dev`; release promotion flows from `dev` into `main`/`master`; urgent `hotfix/*` work may branch from production but must be merged back into `dev` immediately after production is repaired.
- Avoid direct feature-to-production pull requests. Preserve branch protections, required reviews, security gates, environment approvals, and semantic conflict resolution.

### AI-assisted merge thresholds

The thresholds below are strict greater-than comparisons, not greater-than-or-equal comparisons.

1. **Feature or fix pull request -> `dev`:** merge when all configured tests and required checks pass and the reviewing AI records evidence-based confidence **greater than 99.1%** that the change satisfies its acceptance criteria without introducing material regressions.
2. **`dev` -> `main`/`master`:** merge when all integration, release, deployment, migration, security, and required checks pass and the reviewing AI records evidence-based confidence **greater than 99.7%** that the exact promoted revision is production-ready.
3. Record the numerical confidence score, supporting evidence, exact checks run, unresolved uncertainty, migration/deployment impact, and rollback or roll-forward plan in the pull request.
4. A confidence score never overrides a failed or missing required check, an unresolved review, a branch-protection rule, a security/compliance gate, an environment approval, or known contradictory evidence. Do not invent precision: confidence must be justified by review depth, test coverage, affected contracts, and deployment evidence.

### `*-infra`, GitHub Actions, branch-based promotion, and GitOps

- Each organization must designate a canonical infrastructure repository whose name ends in **`-infra`**. It owns deployable desired state: environment overlays, Kubernetes/Helm/Kustomize manifests, Terraform/Pulumi or other infrastructure code, GitOps controller configuration, environment policy, and repository-to-environment mappings.
- Individual application, service, library, CLI, web, API, worker, and client repositories own their source code, tests, build definitions, artifact metadata, and repository-specific GitHub Actions workflows. They must not become the source of truth for live cluster or cloud state.
- Pull requests and short-lived branches run CI. They may create bounded ephemeral preview environments, but they do not mutate persistent shared environments directly.
- A merge into **`dev`** builds and verifies an immutable integration artifact, normally identified by commit SHA and digest. GitHub Actions then opens or updates a reviewed change in the canonical `*-infra` repository for the integration/development/staging environment. The GitOps controller reconciles that desired state.
- A merge from **`dev` into `main`/`master`** promotes the already-tested immutable artifact whenever possible rather than rebuilding different bytes. GitHub Actions opens or updates the production desired-state change in `*-infra`; required approvals complete there; the GitOps controller performs reconciliation.
- Infrastructure-repository changes follow the same GitFlow intent: `dev` represents integration desired state and `main`/`master` represents production desired state, unless the infra repository explicitly documents an equally reviewable environment-directory model on one protected branch.
- GitHub Actions is the validation, build, attestation, and promotion orchestration layer. The GitOps controller is the normal deployment authority. Application workflows must not run routine imperative production mutations such as direct `kubectl apply`, ad hoc cloud-console changes, or unreviewed Terraform applies.
- Use least-privilege OIDC or short-lived credentials, protected GitHub environments, immutable action pins, explicit timeouts, concurrency controls, artifact provenance, and deployment status reporting. Never expose repository or cloud credentials to pull requests from untrusted contexts.
- Rollback normally means a reviewed revert or forward fix to desired state in `*-infra`, followed by GitOps reconciliation. Break-glass deployment paths must be exceptional, auditable, time-bounded, and reconciled back into Git immediately.

Repository-local policy may strengthen these requirements but must not weaken the `dev` integration-branch declaration, the strict confidence thresholds, required checks, GitFlow intent, or GitOps separation of responsibilities.
<!-- END ORESOFTWARE MANAGED BRANCHING AND GITOPS POLICY -->
