# Project tracking and issue routing

The canonical GitHub planning surface for the organization is:

- https://github.com/orgs/gha-indie-worker/projects/1

The matching Linear planning surface is:

- https://linear.app/denman/project/githubcomgha-indie-worker-941d4102f7dc

## Native runner program

The native Windows and macOS runner track is represented by:

- umbrella issue: DEN-2582;
- enrollment and scheduling: DEN-2583;
- Apple Silicon macOS pilot: DEN-2584;
- Windows x64 pilot: DEN-2585;
- cross-platform conformance: DEN-2586;
- mixed-OS operations: DEN-2588;
- runner profile catalog: DEN-2589;
- executable GitHub tracker: https://github.com/gha-indie-worker/gha-indie-worker.rs/issues/15.

## Current execution mirror

The board-ready execution stack is:

- secure workflow admission and canonical target bridge: https://github.com/gha-indie-worker/gha-indie-worker.rs/pull/16;
- typed runner-target and dispatch-v2 profile binding: https://github.com/gha-indie-worker/gha-indie-worker.rs/pull/14;
- native enrollment, attestation, exact scheduling, leases, replay, and host-state simulator: https://github.com/gha-indie-worker/gha-indie-worker.rs/pull/21;
- Apple Silicon macOS hardening profile: https://github.com/gha-indie-worker/gha-indie-worker.rs/pull/17;
- Windows x64 hardening profile: https://github.com/gha-indie-worker/gha-indie-worker.rs/pull/18;
- authoritative mixed-OS inventory contract: https://github.com/gha-indie-worker/gha-indie-worker.rs/pull/19;
- organization fleet and operating contract: https://github.com/gha-indie-worker/.github/pull/18.

Exact heads, validation runs, canonical vocabulary, review order, and the production-readiness boundary are maintained in [NATIVE_RUNNER_IMPLEMENTATION_STATUS.md](NATIVE_RUNNER_IMPLEMENTATION_STATUS.md).

Use issue #15 as the authoritative execution and evidence mirror until each item is placed on the GitHub Project with the required fields. The connected automation currently exposes no authoritative Projects V2 item/field write operation, so no direct board update should be claimed without successful evidence.

## Issue fields

When adding implementation issues to the GitHub Project, set:

- `Status`: `Todo`, `In progress`, or the closest configured field value;
- `Priority`: `High` for identity, scheduling, isolation, cleanup, or fleet-readiness work;
- `Linear`: the relevant `DEN-*` identifier;
- `Platform`: `Control plane`, `macOS`, `Windows`, `Cross-platform`, or `Operations`;
- `Readiness`: `Contract`, `Lab`, `Pilot`, or `Production gate`.

## Promotion rules

Do not move a native-runner issue to `Done` merely because a hosted reference job passes. Completion requires the acceptance criteria in Linear and the organization fleet contract, including physical or independent host evidence where the issue requires it.

All implementation pull requests remain drafts until independently reviewed. Do not self-approve, weaken branch protection, or use routine administrator bypass to advance this stack.
