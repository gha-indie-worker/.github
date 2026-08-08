# Native runner implementation status

Last synchronized: 2026-08-08

This document is the evidence index for the native Windows and macOS runner program. It complements [NATIVE_RUNNER_FLEET.md](../NATIVE_RUNNER_FLEET.md), which remains the organization-wide architecture and operating contract.

## Draft implementation stack

| Layer | Pull request | Exact head | Exact validation |
|---|---|---|---|
| Secure workflow admission and canonical target bridge | [`gha-indie-worker.rs#16`](https://github.com/gha-indie-worker/gha-indie-worker.rs/pull/16) | `55708aaced966dde9c889853ffe95efd358e0b56` | [run 31239888226](https://github.com/gha-indie-worker/gha-indie-worker.rs/actions/runs/31239888226) |
| Typed runner target and dispatch-v2 profile binding | [`gha-indie-worker.rs#14`](https://github.com/gha-indie-worker/gha-indie-worker.rs/pull/14) | `adc97f4a549e70041837b0cb91077e896ff7a1e7` | [run 31211742210](https://github.com/gha-indie-worker/gha-indie-worker.rs/actions/runs/31211742210) |
| Enrollment, capability attestation, exact scheduling, leases, replay, and host-state simulator | [`gha-indie-worker.rs#21`](https://github.com/gha-indie-worker/gha-indie-worker.rs/pull/21) | `8e6be9ce13d07caf189bd4cdd57cb39a019d7b31` | [run 31239307740](https://github.com/gha-indie-worker/gha-indie-worker.rs/actions/runs/31239307740) |
| Apple Silicon macOS hardening profile | [`gha-indie-worker.rs#17`](https://github.com/gha-indie-worker/gha-indie-worker.rs/pull/17) | `43f109279dbbf2d9a5831b152e2649b73e081b02` | [run 31239541140](https://github.com/gha-indie-worker/gha-indie-worker.rs/actions/runs/31239541140) |
| Windows x64 hardening profile | [`gha-indie-worker.rs#18`](https://github.com/gha-indie-worker/gha-indie-worker.rs/pull/18) | `50d3cfcb16a34305e6ecddd3e9d9792f443d0395` | [run 31239553124](https://github.com/gha-indie-worker/gha-indie-worker.rs/actions/runs/31239553124) |
| Authoritative mixed-OS fleet inventory contract | [`gha-indie-worker.rs#19`](https://github.com/gha-indie-worker/gha-indie-worker.rs/pull/19) | `301b292192989221fce270590fcaa55a5e912f2e` | [run 31240238100](https://github.com/gha-indie-worker/gha-indie-worker.rs/actions/runs/31240238100) |
| Organization fleet and project-routing documentation | [`.github#18`](https://github.com/gha-indie-worker/.github/pull/18) | this branch | organization governance and baseline-policy checks |

All implementation pull requests remain drafts pending independent review. Their target integration branch is `dev`; workflows validate `dev` and `main` where the corresponding contract is integrated.

## Canonical vocabulary

The stack agrees on these values:

- platforms: `linux`, `macos`, `windows`;
- architectures: `x64`, `arm64`;
- trust tiers: `public-untrusted`, `public-trusted`, `private-build`, `release-signing`;
- host states: `enrolling`, `healthy`, `busy`, `draining`, `maintenance`, `quarantined`, `offline`, `revoked`;
- fixed profile name plus immutable `sha256:` digest;
- sorted unique capability sets, with `native` mandatory for Windows and macOS;
- no silent cross-platform, cross-architecture, cross-trust-tier, cross-profile-generation, or undeclared-capability fallback.

Aliases including `x86_64`, `amd64`, `aarch64`, `darwin`, and `win32` fail closed rather than being silently normalized.

## Verified protocol-laboratory behavior

The common three-operating-system corpus proves portable protocol behavior for:

- one-use host-bound enrollment and short-lived identity rotation/revocation;
- signed capability envelopes and rejection of stale, tampered, secret-bearing, or enrollment-mismatched claims;
- exact platform, architecture, trust-tier, profile-digest, and capability matching;
- per-host no-match reasons, fairness, and declared-concurrency enforcement;
- exclusive leases, rotating renewal nonces, cancellation, duplicate-delivery idempotency, and terminal receipts;
- drain, maintenance, quarantine, explicit recovery, heartbeat loss, expiry, revocation, host loss, and capability drift.

The same nine protocol and fault tests passed on `ubuntu-24.04`, `windows-2025`, and `macos-15`. The profile and inventory validators have separate exact-head runs listed above.

## Deliberate readiness boundary

The evidence above is contract, simulator, and GitHub-hosted reference evidence. It is not proof of a production independent native fleet.

Production readiness still requires:

- real Apple Silicon and Windows execution capacity, with at least two independent slots before production promotion;
- platform-bound asymmetric device identity and authenticated production transport;
- durable inventory, lease, terminal-receipt, and heartbeat storage and APIs;
- enforced macOS and Windows isolation boundaries;
- pinned operating-system images, Xcode/Visual Studio/SDK/Rust/Flutter/Node toolchains, patch rings, and rollback;
- certified Keychain, simulator, registry, service, process-tree, cache, workspace, and credential cleanup or complete reimage;
- native exact-SHA checkout, submodule, shell, path, filesystem, toolchain, log, artifact, cache, and check-lifecycle fixtures;
- reboot, partition, disk-pressure, antivirus, locked-file, crash, cancellation, expiry, and cleanup-failure exercises;
- two-host failover, queue recovery, rolling upgrades, spares, dashboards, alerts, cost controls, incident procedures, and recovery drills.

GitHub-hosted Windows and macOS jobs must never be represented as independent fleet capacity.

## Review and integration order

1. Independently review secure admission in #16 and typed dispatch/profile binding in #14.
2. Integrate those contracts into `dev` without weakening branch protection.
3. Retarget or rebase #21 onto the integrated `dev` head and rerun its exact three-OS matrix.
4. Independently review and integrate the macOS, Windows, and inventory contracts in #17, #18, and #19.
5. Connect real native agents only after production identity, transport, persistence, isolation, cleanup, and operations gates exist.

No self-approval, routine administrator bypass, or branch-protection weakening is part of this plan.

## Planning surfaces

- Linear project: https://linear.app/denman/project/githubcomgha-indie-worker-941d4102f7dc
- Parent program: https://linear.app/denman/issue/DEN-2582/gha-indie-worker-native-windows-and-macos-runner-program
- GitHub execution tracker: https://github.com/gha-indie-worker/gha-indie-worker.rs/issues/15
- GitHub Project: https://github.com/orgs/gha-indie-worker/projects/1

The connected automation currently has no authoritative GitHub Projects V2 item/field write operation. Issue #15 is therefore the board-ready execution mirror; a direct board update must not be claimed without successful Projects V2 evidence.
