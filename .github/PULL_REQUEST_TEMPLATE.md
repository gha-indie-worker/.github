<!-- BEGIN ORESOFTWARE MANAGED BRANCHING AND GITOPS POLICY -->
## Branching and promotion evidence

**Change path** (select one):
- [ ] Feature/fix/refactor/dependency branch -> `dev` (the integration branch)
- [ ] `dev` -> `main`/`master` production promotion
- [ ] Emergency `hotfix/*` -> production, with an immediate semantic merge back into `dev`

**AI review confidence:** `____.__%`

**Threshold gate:**
- [ ] For a PR into `dev`, confidence is strictly greater than **99.1%**
- [ ] For a `dev` promotion into `main`/`master`, confidence is strictly greater than **99.7%**

**Evidence:**
- Acceptance criteria and linked work item:
- Tests and required checks that passed:
- Review scope, affected contracts, and repositories inspected:
- Remaining uncertainty or known limitations:
- Migration and deployment impact:
- Exact immutable artifact SHA/digest being promoted:
- Canonical `*-infra` desired-state PR/commit and target environment:
- Rollback or roll-forward plan:

- [ ] No branch protection, required review, security/compliance gate, or environment approval is being bypassed.
- [ ] Deployment is represented in the canonical `*-infra` repository and reconciled through GitOps, or this PR documents an approved break-glass exception and immediate follow-up reconciliation.
<!-- END ORESOFTWARE MANAGED BRANCHING AND GITOPS POLICY -->
