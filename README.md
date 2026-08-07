# `.github`

Organization-wide GitHub, branching, review, agent, and delivery policy for `gha-indie-worker`.

## Planning and governance

- [Native Windows and macOS runner fleet](NATIVE_RUNNER_FLEET.md)
- [GitHub Project and Linear routing](docs/PROJECTS.md)
- [Protected review capacity](docs/REVIEW_GOVERNANCE.md)
- [Organization governance](GOVERNANCE.md)
- [Branching and deployment](BRANCHING_AND_DEPLOYMENT.md)
- [Repository boundaries](REPOSITORY_BOUNDARIES.md)

Canonical planning surfaces:

- GitHub Project: https://github.com/orgs/gha-indie-worker/projects/1
- Linear project: https://linear.app/denman/project/githubcomgha-indie-worker-941d4102f7dc

The native Windows/macOS program is tracked in Linear under DEN-2582 through DEN-2589. The first typed runner-target and three-OS reference-conformance implementation is proposed in `gha-indie-worker/gha-indie-worker.rs#14`.

The organization currently has two green standalone continuity promotions waiting for a distinct write-access reviewer: `gha-indie-worker/gha-clone-server.rs#3` and `gha-indie-worker/gha-indie-worker.rs#7`. Never weaken branch protection or count self-approval to merge them.

<!-- ore-org-baseline:begin -->
## Account-wide defaults

This public repository is the canonical source for GitHub-supported fallback community files, organization profile content, reusable workflow examples, and public contributor guidance for [`gha-indie-worker`](https://github.com/gha-indie-worker).

- GitHub owner: [`gha-indie-worker`](https://github.com/gha-indie-worker)
- Linear project: [github.com/gha-indie-worker](https://linear.app/denman/project/githubcomgha-indie-worker-941d4102f7dc)
- Public context: [`ORG_CONTEXT.md`](ORG_CONTEXT.md)
- Canonical agent policy for this repository: [`agents.md`](agents.md)
- Governance: [`GOVERNANCE.md`](GOVERNANCE.md)
- Public repository graph: [`repository-relationships.json`](repository-relationships.json)
- Relationship guide: [`docs/REPOSITORY_RELATIONSHIPS.md`](docs/REPOSITORY_RELATIONSHIPS.md)
- Security reporting: [`SECURITY.md`](SECURITY.md)

GitHub applies only its documented fallback community files automatically. Agent instructions, relationship files, and reusable workflows are **not copied into sibling repositories**; repositories that need local enforcement must carry their own lowercase `agents.md` and explicitly call or copy the provided workflow.

`repository-relationships.json` is generated from GitHub owner membership plus reviewed declarations in `repository-relationships.manual.json`. It is public-safe: private repository names are omitted. The complete graph is synchronized separately to the approved private project registry.

## Safety baseline

Changes are pull-request driven. Contributors and agents must preserve concurrent work, avoid destructive Git operations, resolve conflicts semantically with full history and cross-repository context, validate affected contracts, and never claim a remote action completed without authoritative evidence.

Generated baseline version: `2026-08-04`.
<!-- ore-org-baseline:end -->
