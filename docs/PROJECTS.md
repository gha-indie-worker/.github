<!-- org-project-routing:start -->
# Project routing

- **GitHub organization:** [gha-indie-worker](https://github.com/gha-indie-worker)
- **Canonical GitHub Project:** [gha-indie-worker-project](https://github.com/orgs/gha-indie-worker/projects/1) (project 1)
- **Canonical Linear project:** [planning workspace](https://linear.app/denman/project/githubcomgha-indie-worker-941d4102f7dc)
- **Organization documentation repository:** [gha-indie-worker/.github](https://github.com/gha-indie-worker/.github)

## Source-of-truth boundaries

GitHub is authoritative for repositories, commits, pull requests, reviews, CI checks, releases, deployable artifacts, and runtime evidence. Linear is authoritative for product planning, priorities, ownership, dependencies, milestones, and status reporting. The GitHub Project is the organization-level execution board and should contain the organization governance issue plus active program execution mirrors.

## Current native-runner execution mirror

- **GitHub tracker:** [gha-indie-worker.rs#15](https://github.com/gha-indie-worker/gha-indie-worker.rs/issues/15)
- **Worker protocol PR:** [gha-indie-worker.rs#14](https://github.com/gha-indie-worker/gha-indie-worker.rs/pull/14)
- **Fleet operating contract:** [Native Windows and macOS runner fleet](../NATIVE_RUNNER_FLEET.md)
- **Linear parent:** [DEN-2582](https://linear.app/denman/issue/DEN-2582/gha-indie-worker-native-windows-and-macos-runner-program)

Issue #15 is the durable board-ready checklist and evidence mirror for the native Windows/macOS program. It links the exact implementation head, hosted reference run, Linear work breakdown, and remaining native-host gates.

## Projects V2 mutation evidence

Do not report a GitHub Project item, status, field, or iteration update as complete without authoritative Projects V2 evidence. At the time of the native-runner delivery on August 7, 2026, the available GitHub App surface could publish repository content, branches, pull requests, issues, and workflow evidence, but did not expose Projects V2 item/field mutation; the execution shell also had no usable `gh` binary. Issue #15 must be added and its fields synchronized by a Projects-capable runner or connector, then the resulting Project URL/item evidence must be recorded in GitHub and Linear.

## Change and merge policy

Documentation branches must be reviewed through pull requests and merged after checks pass. Concurrent edits are reconciled semantically against the latest default branch: this managed routing block is regenerated while all unrelated prose outside the block is preserved. Do not resolve conflicts by blindly choosing one side.
<!-- org-project-routing:end -->
