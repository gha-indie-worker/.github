# Codespaces edge hosting

Issue: #36

## Scope

This is a development/preview hosting tier that uses a GitHub Codespace as an ephemeral origin behind Cloudflare. It is not a production availability tier.

Current GHA Indie Worker origin:

- reported Codespace: `supreme-orbit-g4qw69qgj5wcr7v`
- reported repository: `gha-indie-worker/gha-infra`
- current canonical accessible infra repository: `gha-indie-worker/gha-indie-worker-infra`
- canonical local ingress port: `8080`

The connected GitHub installation cannot resolve `gha-indie-worker/gha-infra`; implementation work therefore targets `gha-indie-worker/gha-indie-worker-infra`. Confirm whether the existing Codespace predates a repository rename before recreating it. New automation should use the canonical current repository identity.

## Request path

```text
browser
  -> Cloudflare DNS / TLS / optional Access
  -> remotely managed named Cloudflare Tunnel
  -> cloudflared inside the Codespace
  -> http://127.0.0.1:8080
  -> repository-owned local application origin
```

GitHub port forwarding remains private. Cloudflare must not use a `*.app.github.dev` forwarded-port URL as the origin. The canonical infra devcontainer marks 8080 with `onAutoForward: ignore`.

## Implemented connector lifecycle

The shared Rust implementation is pinned to reviewed private `ORESoftware/ores-cli` revision `c854130ee147e9793a3af8736e90241630a5c934`.

```text
oresc codespace edge up
oresc codespace edge status
oresc codespace edge down
```

The infra repository exposes thin wrappers:

```text
just codespace-edge-check
just codespace-edge-up
just codespace-edge-status
just codespace-edge-down
```

The current contract is connector-only: the repository/local orchestrator must first own a real application origin that answers `/readyz` on `127.0.0.1:8080`; only then does `oresc codespace edge up` start the detached `cloudflared` connector. `down` stops only proven-owned connector processes and leaves the local origin untouched. Do not add a synthetic status server to satisfy ingress.

## Infrastructure integration

`gha-indie-worker/gha-indie-worker-infra` owns the local development graph and remains the reference for:

- reusable `modules/<provider>/...` child modules;
- state-owning `environments/<environment>/<state-root>/...` roots;
- provider-native Supabase/Neon/Cloudflare trees where appropriate;
- `_apps/gha-monorepo` as an exact-revision, non-authoritative application submodule;
- `dist/` as generated/local output;
- `.ores-compose.yaml`, `.ores-infra.toml`, `.zpkg.toml`, and related ORES contracts.

The current application doctor intentionally fails closed because the pinned API/web revisions are still print-and-exit stubs. Do not bypass this with sleeps, fake readiness, or moving branch references. Once those real server listeners are promoted, `ores-compose` owns the 8080 origin and `oresc` may attach the Cloudflare connector.

## Cross-owner bootstrap and secrets

`ORESoftware/ores-cli` is private and cross-owner. Configure these GitHub Codespaces secrets for the canonical infra Codespace:

- `ORES_CLI_READ_TOKEN` — fine-grained GitHub token limited to read-only Contents access on `ORESoftware/ores-cli`, used only to install the exact `oresc` revision;
- `TUNNEL_TOKEN` — connector token for the pre-provisioned remotely managed Cloudflare Tunnel.

The bootstrap token is passed through the environment, with Git CLI credential handling and Cargo's Git CLI fetch path. Never embed it in a Git URL or argv. `TUNNEL_TOKEN` is canonical; `CF_TUNNEL_TOKEN` is compatibility input only and must not be authored into devcontainer configuration.

For longer-lived application configuration, retain the fleet SOPS + age model: encrypted values under approved `env/enc/**` paths and no committed decrypted `.env` or tunnel credentials.

## Validation

Merged infra #27 added the initial devcontainer prerequisites. Merged #28 hardened the cross-owner bootstrap and added a Rust static validator. Current infra PR #29 promotes the connector-only `oresc` revision, updates that validator, documents the external-origin ownership boundary, and adds a dedicated Codespaces edge contract workflow.

The validator/CI contract checks exact revisions, pinned devcontainer features, secret names, Git CLI fetch mode, 8080 auto-forward suppression, wrapper presence, credential-shaped configuration, stale legacy ingress, and merge-conflict markers.

## Codespace activation

Repository readiness does not imply a live tunnel. After real API/web listeners are promoted, the activation order is:

1. initialize the exact application source;
2. pass `scripts/dev/doctor`;
3. start the foreground `ores-compose` origin and wait for `http://127.0.0.1:8080/readyz`;
4. run `just codespace-edge-check`;
5. run `just codespace-edge-up`;
6. inspect `just codespace-edge-status`.

Use `just codespace-edge-down` for connector shutdown; stop the foreground origin through its own supervisor boundary.

Devcontainer permission/configuration changes apply to newly created Codespaces as documented by GitHub; an existing Codespace may require explicit repository-authorization repair rather than assuming a rebuild changed its token scope.

## GitHub Project contract

Track the fleet in a Project named `Codespaces Edge Hosting` with fields: Status, Origin org, Origin repo, Codespace name, Public hostname, Tunnel health, Codespace state, Last verified, and Risk. Recommended views are `By org`, `Tunnel health`, `Blocked`, and `Recently verified`.

The current connector does not expose GitHub Project mutation APIs, so this document defines the tracking contract without claiming that the Project has been created.

## Exit path

Codespaces are ephemeral. Workloads requiring durable availability must graduate to Cloudflare-native hosting or the normal multi-cloud deployment path while keeping their public hostname and health contract stable where practical.
