# Credential egress guard

The credential egress guard blocks high-confidence secret material before it enters Git history, pull-request patches, workflow logs, caches, distributions, browser traces, screenshots, or uploaded evidence. Its output contains only a detector ID, path, line, source digest, and one-way finding fingerprint. It never prints the matched value.

This control implements DEN-3429. It complements provider-side revocation, a runtime secret manager, GitHub secret scanning, and the canonical `ORESoftware/ores-sops` encrypted-environment workflow; it does not replace any of them.

## Safe repository boundary

Only these dotenv payloads may be tracked:

- `env/enc/dev.env.enc`
- `env/enc/prod.env.enc`

They must be SOPS ciphertext created from new, authorized credentials. Plaintext belongs only under ignored `env/dec/`, and a root `.env` may be an ignored local symlink managed by a guarded Just recipe. Age identities, decrypted files, provider credentials, recovery material, and production secret-manager exports must never be committed.

Credentials already disclosed in chat, Git, logs, issues, screenshots, or artifacts are compromised. Do not encrypt and reuse them. An authorized human must revoke or rotate them at the provider, review access/audit history, and provision least-privilege replacements through the approved private runtime boundary.

Repositories adopting encrypted dotenv files should use the pinned Nix shell and Just lifecycle from `ORESoftware/ores-sops`. The guard enforces the Git boundary without decrypting ciphertext and requires no live credential or age identity.

## Deterministic scan scopes

Run from the repository root:

```sh
python3 scripts/credential_egress_guard.py --scope tracked
python3 scripts/credential_egress_guard.py --scope staged
python3 scripts/credential_egress_guard.py --scope introduced --base-ref <immutable-base-sha>
python3 scripts/credential_egress_guard.py --scope paths --path artifacts --path test-results
```

The scopes have distinct purposes:

- `tracked` scans the current tracked worktree.
- `staged` reads index blobs, so an unstaged clean replacement cannot conceal a staged finding.
- `introduced` reads every changed blob from every commit after an immutable base. A finding added in one pull-request commit and deleted in a later commit remains blocked and reports the introducing commit SHA.
- `paths` scans post-test logs, distributions, traces, screenshots, and artifact directories before upload or caching.
- `history` is incident-only and requires an explicit bounded depth, for example `--scope history --history-depth 50`. It never rewrites or force-pushes history.

Inputs larger than the configured scan limit fail closed. Symlinks also fail closed so a scan cannot be redirected to a different file after review.

## Detector policy

`credential-egress-policy.json` is versioned with the repository. The built-in detectors cover:

- GitHub, Linear, AWS, SendGrid, Slack, and live Stripe credential shapes;
- PEM/OpenSSH/PGP private-key material;
- authenticated connection strings;
- signed URLs;
- authorization headers and session cookies;
- high-entropy assignments to built-in or repository-specific secret names;
- plaintext dotenv paths and noncanonical encrypted-environment paths.

Repository additions go in `repository_secret_names` as environment-style identifiers. Tests must construct synthetic, invalid examples; never copy a real credential into a fixture, snapshot, issue, pull request, or report.

Suppressions are intentionally expensive and exact. Every suppression must contain:

```json
{
  "detector_id": "credential.example",
  "path": "fixtures/synthetic.txt",
  "fingerprint": "sha256:<one-way-fingerprint>",
  "owner": "security-owner@example.invalid",
  "rationale": "Synthetic invalid compatibility fixture",
  "expires": "2099-01-01"
}
```

The detector ID, normalized path, and fingerprint must all match. A changed value produces a different fingerprint and remains blocked. Missing ownership, rationale, exact scope, or expiry fails policy loading; expired suppressions fail closed.

## Pre-commit and CI adoption

The repository publishes `.pre-commit-hooks.yaml`. Consumers must pin `rev` to a reviewed immutable commit and keep `pass_filenames: false`, because the hook scans the Git index as a coherent boundary:

```yaml
repos:
  - repo: https://github.com/gha-indie-worker/.github
    rev: <reviewed-40-character-commit>
    hooks:
      - id: credential-egress-guard
```

The composite action at `credential-egress/action.yml` provides the same detector to CI. Pin the action to a reviewed immutable commit, check out full history without persisted credentials, and pass the pull request's immutable base commit:

```yaml
- uses: actions/checkout@<reviewed-40-character-commit>
  with:
    fetch-depth: 0
    persist-credentials: false
- uses: gha-indie-worker/.github/credential-egress@<reviewed-40-character-commit>
  with:
    scope: introduced
    base-ref: ${{ github.event.pull_request.base.sha }}
```

After tests, invoke the action again with `scope: paths` and a newline-delimited `paths` list before any upload, cache save, Pages publish, or external evidence transfer.

## Incident runbook

1. Stop using the credential and prevent further publication. Do not paste it into tickets, comments, commands, screenshots, or replacement fixtures.
2. Preserve only redacted evidence: detector ID, path, line, source commit/digest, one-way fingerprint, provider/repository, and timestamps.
3. Have an authorized owner revoke or rotate the credential at the provider, review audit history and active sessions, and issue a least-privilege replacement through the approved private secret manager.
4. Remove the current-tree source and every workflow, artifact, cache, log, Pages output, release asset, and secret-store reference that reused it. Publish a focused remediation pull request.
5. Run the tracked, staged, introduced, and relevant artifact/log scopes. Use bounded history mode only to establish incident reach.
6. Treat history rewriting, force-pushing, cache purging, release deletion, and provider garbage collection as separately reviewed destructive operations. Coordinate repository owners and downstream clones before proceeding.
7. Record exact clean revisions, CI run IDs, revocation evidence location, rollout state, and remaining blockers in the private incident record and the redacted Linear update.

The absence of a detector finding is evidence for the scanned revision and inputs only. It is not proof that a provider credential was revoked, that historical objects were garbage-collected, or that deployed runtime secrets were replaced.
