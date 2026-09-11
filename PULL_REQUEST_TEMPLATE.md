## Purpose

Describe the problem, intended behavior, and why this repository owns the change.

## Scope and boundaries

- [ ] The change is focused and does not silently cross repository ownership boundaries.
- [ ] No `*-infra` repository is introduced as a Git submodule under `*-monorepo/apps`.
- [ ] Public contracts, migrations, compatibility, and rollback needs are documented.

## Validation

List formatters, linters, tests, builds, security checks, and manual verification performed.

## Safety

- [ ] No credentials, customer data, or private-repository inventory is included.
- [ ] Conflicts were resolved semantically using both sides and relevant history.
- [ ] Destructive Git recovery and history rewrites were not used.

## Salvage check

If this PR supersedes or replaces an older one, say which, and name at least one
concrete thing carried forward from it (a test, a fixture, an error message, a
pin, a doc paragraph). See [`docs/pr-salvage-policy.md`](../docs/pr-salvage-policy.md).

- [ ] Supersedes nothing, **or** the salvaged item is named above.
