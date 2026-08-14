# `.github`

Organization-wide GitHub, branching, review, agent, and delivery policy for `gha-indie-worker`.

## Planning and governance

- [GitHub Project and Linear routing](docs/PROJECTS.md)
- [Protected review capacity](docs/REVIEW_GOVERNANCE.md)
- [Organization governance](GOVERNANCE.md)
- [Branching and deployment](BRANCHING_AND_DEPLOYMENT.md)
- [Repository boundaries](REPOSITORY_BOUNDARIES.md)
- [Credential egress guard and incident runbook](docs/CREDENTIAL_EGRESS_GUARD.md)

Canonical planning surfaces:

- GitHub Project: https://github.com/orgs/gha-indie-worker/projects/1
- Linear project: https://linear.app/denman/project/githubcomgha-indie-worker-941d4102f7dc

The organization currently has two green standalone continuity promotions waiting for a distinct write-access reviewer: `gha-indie-worker/gha-clone-server.rs#3` and `gha-indie-worker/gha-indie-worker.rs#7`. Never weaken branch protection or count self-approval to merge them.

<!-- ore-org-baseline:begin -->
## Organization-wide defaults

This public repository is the canonical source for GitHub-supported community-health fallbacks, organization profile content, contribution guidance, public security/support policy, issue and pull-request templates, and agent-governance declarations for [`gha-indie-worker`](https://github.com/gha-indie-worker).

## Canonical organization links

- GitHub organization: https://github.com/gha-indie-worker
- Public organization defaults: https://github.com/gha-indie-worker/.github
- Canonical Linear project: https://linear.app/denman/project/githubcomgha-indie-worker-941d4102f7dc
- Fleet tracking issue: https://github.com/ORESoftware/k8s-cluster/issues/1222

## Safety baseline

All Git conflicts must be resolved semantically with full historical, repository-wide, organization-wide, and relevant external-organization context. Automated agents are hard-denied from destructive or history-rewriting operations, including all forms of `git stash`, `git reset`, `git clean`, `git filter-repo`, force pushing, destructive deletion, data or infrastructure teardown, credential revocation, and policy bypass.

## GitHub inheritance boundary

GitHub can use supported community-health files from a public organization `.github` repository as fallbacks and can render `profile/README.md` on the organization page. `agents.md`, `AGENTS.md`, Copilot instructions, workflows, settings, rulesets, branch protections, permissions, and secrets are not automatically inherited merely because they exist here. Each repository must carry or synchronize compatible local policy and explicitly call reusable workflows where enforcement is required.

Generated managed-policy version: `2026-08-08`.
<!-- ore-org-baseline:end -->

<!-- BEGIN MANAGED REPOSITORY RELATIONSHIPS v1 -->
## Repository relationship registry

`gha-indie-worker` declares repository roles, dependency edges, cross-organization capabilities, deployment ownership, and the git-submodule/Zed-package contract:

- [Human-readable map](architecture/REPOSITORY_RELATIONSHIPS.md)
- [Machine-readable manifest](architecture/repository-relationships.json)
- [JSON Schema](architecture/repository-relationships.schema.json)

The public registry withholds private repository names and edges.
<!-- END MANAGED REPOSITORY RELATIONSHIPS v1 -->
