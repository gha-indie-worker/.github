# gha-indie-worker bounded CI project delivery — August 5, 2026

## Project routing

- GitHub organization: [`gha-indie-worker`](https://github.com/gha-indie-worker)
- GitHub Project: [`gha-indie-worker-project` #1](https://github.com/orgs/gha-indie-worker/projects/1)
- Standalone repository: [`gha-indie-worker/gha-clone-server.rs`](https://github.com/gha-indie-worker/gha-clone-server.rs)
- Linear project: [`github.com/gha-indie-worker`](https://linear.app/denman/project/githubcomgha-indie-worker-941d4102f7dc)
- Linear evidence: [gha-indie-worker bounded CI continuity delivery — August 5, 2026](https://linear.app/denman/document/gha-indie-worker-bounded-ci-continuity-delivery-august-5-2026-e75b56c2fd58)
- Primary Linear issue: DEN-1606

Standalone clone-server source, repository-local CI, platform-boundary contracts, and extraction provenance belong on this organization’s Project. Shared Kubernetes, ARC, multi-provider routing, and fixed-profile execution substrate belong on the ORESoftware board. Durable distributed assignment and fencing belong on the Fiducia board.

## Source authority

The reviewed source authority for the current extraction is:

```text
ORESoftware/k8s-cluster@e75a654bfd527500a3a2ef4ceb1836e78e14a7a6
remote/deployments/gha-clone-server-rs
```

The standalone repository is a reviewed extraction, not an independently drifting fork. A future synchronization must use a normal pull request, record the full immutable source commit, preserve hidden files, modes, and `Cargo.lock`, compare the complete target tree, and reconcile independent changes semantically. Do not force-push over reviewed standalone history.

## Platform-boundary pull request

[`gha-indie-worker/gha-clone-server.rs#2`](https://github.com/gha-indie-worker/gha-clone-server.rs/pull/2) is exact-head green at:

```text
5d8f4c00ea359c495b4bc997b29ce22cfc9c9c4f
```

The PR is non-draft, mergeable, contains six permanent files, and has no unresolved review threads. Squash auto-merge is enabled. Branch protection requires one independent write-access approval; the author cannot self-approve, and that requirement is not bypassed.

Permanent product scope:

- `.github/workflows/ci.yml`
- `.github/workflows/gha-clone-server-meta.yml`
- `docs/platform-boundary.json`
- `docs/platform-boundary.md`
- `tests/architecture_contract.rs`
- `tests/meta_self_test.rs`

Exact-head validation passed Rust formatting, warnings-denied all-target/all-feature Clippy, all locked tests including the repository-local meta self-test, a locked release build, standalone CI, and secret scanning.

## Bounded architecture contract

This service does not clone GitHub’s proprietary Actions control plane and does not claim full parity.

It accepts only allowlisted repositories, immutable 40-hex revisions, direct reviewed workflow paths, bounded request bodies, and the deliberately supported YAML subset. It emits fixed `dd-build-server` profiles rather than caller-selected shell, image, working directory, service, OIDC, environment, deployment, or marketplace-action behavior.

The wider system keeps separate authorities:

1. GitHub-hosted runners and official ARC for native GitHub Actions semantics.
2. Capacity/billing policy in `gha-capacity-broker-rs`.
3. Bounded planning and run coordination in `gha-clone-server-rs`.
4. Pre-submit provider selection in `gha-executor-router`.
5. Fixed-profile execution, logs, and artifacts in `dd-build-server`.
6. Distributed durability and fencing in Fiducia.

Provider choice occurs before submission. Once an executor is contacted, ambiguous acceptance must not cause cross-provider replay. Accepted build identity remains pinned through polling.

Webhook delivery claims and run records are process-local. Keep one active replica until durable identity, assignment, and Fiducia fencing are authoritative.

## Remaining project gates

1. Obtain one independent write-access approval for PR #2; squash auto-merge is already armed.
2. Protect `main` with repository-local CI and secret scanning after merge.
3. Publish immutable source provenance for every future extraction update.
4. Keep the supported YAML surface fail-closed and add behavior only with fixtures, architecture tests, and real-process tests.
5. Do not scale beyond one active replica until Fiducia-backed durable claims and fencing are implemented and tested.