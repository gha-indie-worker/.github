# Build-log cross-runtime contract and process-boundary conformance

Tracking: Linear DEN-1862, DEN-1863, DEN-2586.

This document records the organization-level release contract for IndieBuild/GitHub Actions build-log fan-out. Independently green producer and consumer unit suites are not sufficient evidence that inherited-descriptor semantics work across a real process boundary.

## Authority model

The portable build-log contract has exactly two independent human-authored authorities:

1. TypeSpec; and
2. JSON Schema Draft 2020-12.

`ORESoftware/typespec-json-schema-validator` (TJSV) is the fail-closed admission and comparison gate across language/runtime boundaries. Generated Schema B, Contract IR, SARIF, receipts, Rust/TypeScript/Dart bindings, and other generated artifacts are evidence or projections; they are not a third authored authority and must never overwrite either peer authority.

Current certified evidence snapshot from the DEN-1862 hardening line:

- interface authority: `gha-indie-worker/gha-indie-worker-interfaces@7165a361462e624195e91cf88ec472b7d6e9c1da`;
- TJSV verifier: `ORESoftware/typespec-json-schema-validator@a4b731fbf82c4d162abd74fd03758fa32bb76176`;
- reference receiver: `gha-indie-worker/gha-indie-worker-sidecar.rs@d702555675e5d3f3875388b4fe09bbfd026eafbc`.

Pins above are evidence identities, not floating dependency policy. New candidates must state and verify their own exact immutable revisions.

## Unix transport contract

The DEN-1862 receiver protocol is `gha-indie-worker.build-log-metadata/v1`.

- FD 3 carries bounded newline-delimited metadata JSON.
- FD 4 carries exact raw data bytes.
- FD 3 and FD 4 must be distinct inherited descriptors.
- Chunk payloads are binary-safe and must not be decoded or normalized as UTF-8.
- Metadata and lifecycle records must validate against the independent TypeSpec/JSON Schema authorities before runtime promotion evidence is accepted.
- Optional fields are absent when unset; schema-invalid JSON `null` is not substituted for absence.
- Unknown fields, including credential-shaped fields, fail closed at the receiver boundary.
- The receiver is an optional sink: saturation, EOF, crash, malformed input, or write timeout must not change the canonical build output or build result.
- The worker must not expose ambient GitHub, cloud, database, auth, or unrelated service credentials to the receiver. Receiver environment is empty except for the explicit allowlist and protocol variables.
- Queueing, writes, drain, close, receiver exit, and forced termination share one hard total shutdown ceiling of eight seconds; phase-by-phase budgets must not multiply that ceiling.

The already-merged DEN-1863 framed stdin/FD3 receiver protocol remains an additive compatibility surface where required. Reconciliation must be semantic: do not choose one Git side wholesale when both lifecycle models carry compatible intent.

## Mandatory real-process gate

Promotion evidence must include a real worker producer process boundary against an exact merged/certified reference sidecar revision. Unit tests on each repository are necessary but insufficient.

The exact candidate gate must:

1. verify the worker candidate, interface authority, TJSV verifier, and reference receiver SHAs before executing tests;
2. run TJSV peer-authority parity/admission and current-input Contract IR verification;
3. start the real worker receiver supervisor and the real reference receiver executable;
4. send normal stdout plus non-UTF8 stderr through the actual inherited metadata/data transport;
5. byte-compare receiver stdout/stderr output without text normalization;
6. cover receiver crash/EOF, a receiver that does not consume, queue saturation/drop accounting, metadata/data ordering, lifecycle close records, and the hard total shutdown bound;
7. fail if the runtime transport uses an IPC primitive the receiver cannot consume through its documented descriptor contract;
8. retain deterministic evidence from the exact candidate head.

A workflow that skips the real process step, exits before test steps, substitutes mocks on either side, or passes because a dependency was not executed is not promotion evidence.

## Integration defect discovered 2026-09-09

The first real worker-to-reference-sidecar test exposed a defect that repository-local tests did not detect: the worker producer used Unix-domain socketpairs for the two inherited lanes, while the reference receiver intentionally opens `/dev/fd/3` and `/dev/fd/4` as ordinary file descriptors. Socket descriptors cannot be reopened through that receiver path, so the receiver exited before receiving build bytes even though both unit suites and TJSV contract admission were green.

The invariant is stronger than “FD numbers match”: the producer must supply an IPC primitive compatible with the receiver's actual documented open/read semantics. For the Unix dual-descriptor implementation, use true inherited pipes (or an explicitly versioned alternative transport) with nonblocking/cancellable parent writers and blocking child read ends. Preserve close-on-exec correctness when relocating/installing FD3/FD4.

This finding makes the process-boundary gate permanent rather than a one-off regression test.

## Cross-platform follow-up

DEN-2586/native-runner work must explicitly validate transport semantics per operating system rather than assuming Unix descriptor behavior is portable.

- Linux: anonymous pipes, FD relocation, CLOEXEC/`dup2`, `/dev/fd`, EOF, slow-reader pressure, and child cleanup.
- macOS: the same inherited-descriptor invariants plus platform-specific `/dev/fd` behavior and native-runner cleanup/quarantine evidence.
- Windows: define an explicit named-pipe/inherited-handle protocol or another versioned transport; non-Unix builds must fail closed until that contract is implemented and independently tested.

Cross-platform transport changes must keep the same TypeSpec/JSON Schema semantic contract where the wire vocabulary is shared, and must use TJSV to prove language/runtime boundary agreement.

## Promotion and governance

`gha-indie-worker.rs` protected promotion remains subject to required `rust`, `provenance`, and `gitleaks` contexts and independent approval. Technical confidence never bypasses branch protection or review requirements.

The current DEN-1862 producer work is stacked behind parity/conformance PR #36. PR #36 may auto-merge only after its independent write-access approval is supplied. After that legitimate merge, producer PR #40 must be semantically reconciled/retargeted, rerun on its new exact head, and only then evaluated for promotion.

## Roll-forward / rollback

This contract adds validation and evidence requirements; it does not activate a deployment or mutate infrastructure. If an implementation fails the process-boundary gate, preserve the candidate branch and repair forward. Do not weaken TJSV, skip process tests, bypass protected review, rewrite history, or remove evidence merely to obtain a green result.
