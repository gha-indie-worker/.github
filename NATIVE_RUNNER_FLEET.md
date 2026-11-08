# Native Windows and macOS runner fleet

## Purpose

`gha-indie-worker` must be able to validate software on real Windows and macOS operating systems without turning the worker into an unrestricted self-hosted shell service. This document defines the organization-wide delivery contract for native hosts and connects the implementation, operations, and conformance work tracked in Linear and GitHub.

Canonical planning:

- [DEN-2582 — Native Windows and macOS runner program](https://linear.app/denman/issue/DEN-2582/gha-indie-worker-native-windows-and-macos-runner-program)
- [DEN-2583 — Capability, enrollment, scheduling, and lease protocol](https://linear.app/denman/issue/DEN-2583/gha-indie-worker-define-native-host-capability-enrollment-scheduling)
- [DEN-2584 — Apple Silicon macOS runner pool](https://linear.app/denman/issue/DEN-2584/gha-indie-worker-provision-and-harden-an-apple-silicon-macos-runner)
- [DEN-2585 — Windows x64 runner pool](https://linear.app/denman/issue/DEN-2585/gha-indie-worker-provision-and-harden-a-windows-x64-runner-pool)
- [DEN-2586 — Linux/macOS/Windows conformance and fault-injection gates](https://linear.app/denman/issue/DEN-2586/gha-indie-worker-build-linuxmacoswindows-conformance-and-fault)
- [DEN-2588 — Mixed-OS fleet operations](https://linear.app/denman/issue/DEN-2588/gha-indie-worker-operate-the-mixed-os-fleet-inventory-capacity)
- [DEN-2589 — Native OS profile catalog and repository routing](https://linear.app/denman/issue/DEN-2589/gha-indie-worker-define-the-native-os-profile-catalog-and-repository)
- [Implementation PR #14](https://github.com/gha-indie-worker/gha-indie-worker.rs/pull/14)

## Non-goals

Native support does not mean accepting arbitrary GitHub Actions execution on an unmanaged laptop or desktop. The program must not:

- expose inbound SSH, RDP, WinRM, Screen Sharing, or a generic remote shell to workflow authors;
- allow workflow YAML to select a concrete host, image, hypervisor, command implementation, credential, network segment, signing identity, simulator device, or privileged capability;
- route untrusted fork pull requests to privileged native machines;
- reuse a dirty workspace, user profile, keychain, registry hive, simulator state, package cache, or credential store across trust boundaries;
- silently approximate unsupported GitHub Actions behavior;
- claim Windows or macOS compatibility from Linux cross-compilation alone.

The existing fixed-profile execution model remains authoritative. Native hosts add an executor class; they do not relax admission or execution policy.

## Two distinct validation layers

### GitHub-hosted reference matrix

Every runner-contract change should first pass a read-only reference matrix on GitHub-hosted Linux, Windows, and macOS machines. The initial implementation uses `ubuntu-24.04`, `windows-2025`, and `macos-15` to prove that protocol code and tests are portable.

Reference jobs do not prove the security or reliability of the independent fleet. They provide a known external comparison point for language, filesystem, process, path, quoting, line-ending, and toolchain behavior.

### Independent native fleet

Production validation uses enrolled machines controlled by `gha-indie-worker`. A dispatch is eligible only when its immutable reviewed profile exactly matches the host's attested platform, architecture, profile generation, and capabilities.

Initial production baselines:

| Pool | Platform | Architecture | Required capability | Typical reviewed capabilities |
|---|---|---|---|---|
| macOS | `macos` | `arm64` | `native` | `xcode`, `ios-simulator`, `swift`, `codesign-verify` |
| Windows | `windows` | `x64` | `native` | `msvc`, `windows-sdk`, `powershell`, `hyper-v` |
| Linux | `linux` | `x64` or `arm64` | profile-specific | container/build/test capabilities already reviewed |

Intel macOS and Windows ARM64 are future explicit pools. They must never be inferred from a generic `macos` or `windows` label.

## Repository-facing routing contract

A dispatchable workflow job must declare all of:

- `self-hosted`;
- `gha-indie-worker`;
- exactly one platform: `linux`, `macos`, or `windows`;
- exactly one architecture: `x64` or `arm64`.

The operator-reviewed profile catalog supplies the exact capabilities. Workflow YAML cannot add capabilities. The binder rejects a plan when its platform or architecture differs from the selected profile.

Example labels:

```yaml
runs-on: [self-hosted, gha-indie-worker, macos, arm64]
```

Example reviewed profile metadata:

```json
{
  "name": "macos-xcode",
  "digest": "sha256:...",
  "runner": {
    "platform": "macos",
    "architecture": "arm64",
    "capabilities": ["native", "xcode", "ios-simulator"]
  }
}
```

The dispatch request carries the normalized runner target as part of its deterministic identity and digest. A downstream scheduler must match the entire target and immutable profile generation, not only a broad operating-system label.

## Host identity and enrollment

Each machine has a unique inventory identity that is distinct from its hostname and human owner. Enrollment must be deliberate, revocable, and auditable.

Required properties:

1. The agent initiates outbound connections only.
2. Bootstrap credentials are one-use and short-lived.
3. Successful bootstrap yields a machine-bound identity protected by the operating system's secure storage where available.
4. The control plane records platform, architecture, hardware identity, OS build, agent version, profile generations, patch ring, ownership, location class, and trust tier.
5. Capability claims are verified during enrollment and periodically re-attested; a host cannot self-grant an unapproved capability.
6. Rotation, revocation, decommissioning, and suspected-compromise flows are first-class operations.
7. Re-enrollment after reimage creates traceable continuity without reviving revoked credentials.

Enrollment evidence must never contain private keys, access tokens, customer data, or full secret values.

## Scheduling and leases

Scheduling is exact-match and lease-based.

A host is eligible only when it is:

- enrolled and not revoked;
- healthy, online, and within heartbeat limits;
- not draining or quarantined;
- in an allowed trust tier for the repository/event;
- running an approved agent version and OS patch level;
- advertising the exact platform, architecture, profile digest, and required capabilities;
- below configured concurrency and thermal/resource thresholds.

A lease binds one request ID, immutable repository commit, profile digest, host identity, workspace identity, attempt number, and deadline. Leases are exclusive, renewable only under bounded rules, and terminal-state idempotent. Host loss, control-plane loss, cancellation, timeout, and duplicate delivery must not produce two authoritative executions.

The scheduler must expose why no host matched rather than silently falling back to another platform, architecture, profile, or trust tier.

## Trust tiers and repository admission

At minimum, distinguish:

1. **Public-untrusted** — fork pull requests and unknown contributors. No organization secrets, signing identities, private network access, or persistent caches. Native execution is disabled until an explicitly reviewed isolated tier exists.
2. **Public-trusted** — approved branches and reviewed internal pull requests with no sensitive signing or production access.
3. **Private-build** — private repositories and bounded build/test credentials.
4. **Release-signing** — separately governed hosts and profiles with hardware-backed signing identities and additional approvals.

A broad repository membership or `write` permission must not automatically authorize release-signing or privileged native profiles. Admission policy must bind event type, repository, immutable SHA, actor/trust decision, and selected profile.

## Isolation and cleanup

### macOS

The preferred baseline is a dedicated Apple Silicon machine or a supported macOS virtualization boundary where licensing and hardware permit it. Each job receives a fresh workspace and isolated user/session context appropriate to the profile.

Cleanup must cover:

- spawned processes, launch agents/daemons, child process trees, and open file handles;
- temporary users, home-directory state, shell history, environment files, and credential helpers;
- Keychain items and unlocked keychains created for the job;
- Xcode derived data, build products, package-manager state, simulator devices, simulator keychains, and test media;
- mounted images, temporary volumes, network proxies, and firewall changes;
- signing material and provisioning profiles, even after cancellation or agent crash.

A cleanup failure quarantines the host. High-trust profiles should prefer restore/reimage from a known immutable baseline over incremental cleanup.

### Windows

The agent runs as a constrained Windows service identity. Jobs use a fresh workspace and an isolated user, VM, sandbox, or equivalent boundary selected by the reviewed profile.

Cleanup must cover:

- complete process trees, services, scheduled tasks, jobs, named pipes, and handles;
- temporary users and profiles, `%TEMP%`, credential manager entries, PowerShell history, and Git credential helpers;
- registry changes, environment variables, certificates, package-manager state, and developer tool caches;
- mounted VHD/VHDX images, Hyper-V resources, Windows Sandbox state, firewall rules, and network shares;
- code-signing material and SDK credentials.

A locked file or surviving service is a cleanup failure, not a warning. The host enters quarantine until remediation or reimage proves a clean baseline.

## Secrets and network policy

Secrets are issued per job and per profile with minimum scope and lifetime. They are not stored in profile catalogs, dispatch documents, logs, workspace snapshots, or reusable caches.

Native hosts default to restricted egress. Profiles explicitly declare approved network destinations or network classes. Production control planes, cloud metadata endpoints, local LAN services, personal user accounts, and unrelated developer machines are denied unless a separately reviewed profile requires them.

Logs, annotations, and artifacts must use bounded collection and masking. Masking is defense in depth, not permission to expose a secret to an unnecessary job.

## Lifecycle and operations

Every host supports these states:

`enrolling → ready → leased → cleaning → ready`

Operational states may interrupt the normal path:

- `draining` — accepts no new work and finishes or cancels current work according to policy;
- `quarantined` — unavailable because identity, patching, health, cleanup, or conformance is suspect;
- `reimaging` — restoring the approved baseline;
- `revoked` — identity permanently disabled;
- `offline` — heartbeat lost, with any lease treated through the ambiguity/recovery protocol.

Fleet operations must track capacity, queue delay, utilization, patch compliance, agent/profile versions, failure rate, cleanup failures, quarantines, reimage duration, thermal/resource pressure, and spare capacity. Patch rollout uses canary and staged rings with rollback to a known image/profile generation.

## Conformance and fault injection

Promotion requires both functional parity evidence and fleet-specific failure evidence.

The conformance corpus should cover:

- path separators, case sensitivity, symlinks/junctions, executable bits, long paths, file locking, Unicode, line endings, and filesystem timestamp behavior;
- `cmd`, PowerShell, POSIX shell, process exit/signal behavior, cancellation, and child-process cleanup;
- Rust, Node.js, Python, Dart/Flutter, browser automation, and repository-specific toolchains as profiles are added;
- exact detached-SHA checkout, submodules, LFS where approved, clean workspaces, and credential removal;
- bounded logs, annotations, artifacts, timeouts, retries, and terminal-state reconciliation;
- host reboot during lease, network partition, agent crash, control-plane restart, duplicate delivery, cancellation races, disk exhaustion, and cleanup failure;
- comparison with the GitHub-hosted reference matrix for supported semantics.

A passing unit test on one hosted image is not sufficient to promote a native pool.

## Rollout gates

### Gate 1 — typed protocol and reference matrix

- runner target is part of the reviewed catalog and dispatch identity;
- unsupported/missing/ambiguous labels fail closed;
- Linux, Windows, and macOS reference checks pass;
- schema migration and rollback are documented.

Tracked by PR #14, DEN-2589, and the first portion of DEN-2586.

### Gate 2 — one-machine lab per native platform

- one enrolled Apple Silicon Mac and one enrolled Windows x64 machine;
- outbound-only agent identity, heartbeat, drain, lease, cancellation, cleanup, and quarantine;
- no production secrets or untrusted workloads;
- inventory ownership and reimage procedure documented.

Tracked by DEN-2583, DEN-2584, DEN-2585, and DEN-2588.

### Gate 3 — trusted pilot

- selected internal repositories only;
- exact profile matching and immutable SHA checkout;
- conformance and fault-injection evidence published;
- capacity alerts, patch rings, spare/recovery plan, and operator runbooks active.

### Gate 4 — production expansion

- repository-by-repository admission review;
- trust-tier controls proven;
- release-signing remains separate;
- no unresolved cleanup, duplicate-execution, identity, or recovery ambiguity;
- rollback/reimage drills completed.

## Evidence and synchronization

GitHub is authoritative for code, commits, pull requests, checks, workflow runs, releases, and runtime evidence. Linear is authoritative for program scope, ownership, dependencies, milestones, and status. The organization GitHub Project mirrors execution state when Projects V2 mutation is available; the absence of a board-field update must be recorded explicitly rather than reported as complete.
