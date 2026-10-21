# Contributing to `gha-indie-worker` repositories

## Rust-first scripts and automation

**Do not add or extend Python scripts; use Rust for first-party tooling.** This applies to build and CI helpers, code generation, data and schema migration tools, release/deploy helpers, project administration, local developer scripts, and one-off maintenance utilities. Prefer a versioned Rust CLI or `cargo xtask` command; thin shell/YAML wrappers may launch Rust programs where required.

**Existing Python automation is migration debt, not a reason to add new Python automation.** Inventory the current script, callers and environment requirements; port with behavioral parity before removing it. Preserve CLI arguments and exit statuses, output formats, error handling, security checks, and supported platforms. Validate positive and negative cases, then switch all CI, docs, hooks and other callers. Record follow-up issues rather than claiming this documentation change performs the migration.

**Python application code is a narrow, documented exception.** A real application/service or an application-specific test suite may use Python when the owning team documents its purpose, scope, alternatives, and reason Rust is unsuitable. Such approval does *not* cover general repository scripts, CI glue, code generators or maintenance automation disguised as app code. Existing Python app code is not automatically slated for deletion by this rule.

New Rust tooling should provide repeatable `cargo` invocations, clear CLI help and failures, appropriate tests, and pinned dependencies where the repository requires them. Prefer `cargo fmt --check`, `cargo clippy -- -D warnings`, `cargo test`, plus relevant end-to-end smoke checks on the actual changed head. No check can be reported as passing unless it actually ran.

This is an organization-wide **contributor policy** via the canonical public `.github` repository. GitHub does not automatically distribute standalone `AGENTS.md`, workflow, or custom policy files to every repository; sibling repositories must explicitly synchronize or reference this guidance and enable their own enforcement where required.


## Durable engineering policy

- This repository defines public organization-wide defaults for `gha-indie-worker`.
- Never commit credentials, private keys, access tokens, customer data, or private-repository inventories.
- Resolve Git conflicts semantically: inspect both sides, the merge base, nearby tests and contracts, and normally 3–10 relevant prior commits. Never blindly select all of `ours` or all of `theirs`.
- Prefer focused pull requests, explicit validation, non-destructive Git operations, and documented tradeoffs.
- Cross-repository integration uses versioned interfaces, APIs, SDKs, events, or explicitly owned replicated read models. Services do not reach into another service's database by default.
- `*-infra` repositories and `*-monorepo` application source remain separate. A `*-infra` repository must never appear as a Git submodule under `*-monorepo/apps`.
- Git submodules are reserved for explicitly coordinated editable source composition. Zed packages or immutable artifacts are preferred for package dependencies. Production deploys immutable artifacts or OCI digests, not source clones.

## Pull requests

Keep pull requests focused and reviewable. Describe motivation, changed behavior, interface or migration impact, security considerations, validation performed, and rollback or compatibility plans where relevant.

<!-- ore-org-baseline:begin -->
Thank you for contributing to repositories owned by [`gha-indie-worker`](https://github.com/gha-indie-worker). Repository-local instructions take precedence when they are stricter.

## Before proposing a change

1. Read the repository README, contribution notes, lowercase `agents.md`, architecture documentation, linked issues, and relevant [Linear project](https://linear.app/denman/project/githubcomgha-indie-worker-941d4102f7dc).
2. Confirm the authoritative source repository and whether files are generated, vendored, mirrored, or owned by another repository.
3. Fetch current remote state and preserve concurrent work. Avoid git rebase in favor of git merge.
4. Do not use `git stash`, `git reset`, `git clean`, `git filter-repo`, force-push, destructive worktree/submodule operations, or broad deletion/rewrite commands without exact authorization.
5. Never include secrets, credentials, customer data, legal records, or other private information in issues, commits, test fixtures, screenshots, or logs.

## Pull requests

Use a focused feature branch and a draft pull request. Link the relevant issue or Linear work; explain behavior, risk, security impact, migration and rollback considerations, tests, and cross-repository dependencies. Resolve conflicts semantically with full context—normally including the merge base and 3–10 relevant commits—rather than selecting one side wholesale. Run all affected checks and scan the complete worktree for conflict markers.

External GitHub Actions must be pinned to full commit SHAs. Workflows must use explicit least-privilege permissions, explicit timeouts, and non-persisted checkout credentials.
<!-- ore-org-baseline:end -->
