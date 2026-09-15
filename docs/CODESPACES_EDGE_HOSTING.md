# Codespaces edge hosting

Issue: #36

## Scope

This is a development/preview hosting tier that uses a GitHub Codespace as an ephemeral origin behind Cloudflare. It is not a production availability tier.

Current GHA Indie Worker origin:

- reported Codespace: `supreme-orbit-g4qw69qgj5wcr7v`
- reported repository: `gha-indie-worker/gha-infra`
- current canonical accessible infra repository: `gha-indie-worker/gha-indie-worker-infra`
- canonical local port: `8080`

The connected GitHub installation cannot resolve `gha-indie-worker/gha-infra`; current implementation work therefore targets `gha-indie-worker/gha-indie-worker-infra`. Before recreating the existing Codespace, confirm whether it predates a repository rename. New automation should use the canonical current repository identity.

## Request path

```text
browser
  -> Cloudflare DNS / TLS / optional Access
  -> remotely managed named Cloudflare Tunnel
  -> cloudflared inside the Codespace
  -> http://127.0.0.1:8080
  -> preview/status server
```

The GitHub forwarded port remains private. Cloudflare must not use the `*.app.github.dev` forwarded-port URL as the origin. The canonical infra devcontainer marks port 8080 with `onAutoForward: ignore`.

## Implemented lifecycle

The shared Rust implementation is pinned from private `ORESoftware/ores-cli` commit `620cbbc3a5595cfa90b242011b5c1a859928c297`.

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

`codespace-edge-check` is read-only and accepts exit 2 when the edge runtime is installed but stopped. Lifecycle behavior remains owned by `oresc`, not duplicated in shell.

## Origin contract

The shared preview/status origin exposes `/`, `/healthz`, `/readyz`, and `/version`, is stateless, and binds to `127.0.0.1:8080` by default. Responses must not contain credentials.

## Infrastructure integration

Extend the existing fleet infra conventions rather than adding an unrelated Terraform root. `gha-indie-worker/gha-indie-worker-infra` remains the reference for:

- reusable `modules/<provider>/...` child modules;
- state-owning `environments/<environment>/<state-root>/...` roots;
- provider-native Supabase/Neon/Cloudflare trees where appropriate;
- `_apps/gha-monorepo` as an exact-revision, non-authoritative application submodule;
- `dist/` as generated/local output;
- `.ores-infra.toml`, `.zpkg.toml`, and related ORES contracts.

## Cross-owner bootstrap and secrets

`ORESoftware/ores-cli` is private and belongs to a different GitHub owner. A Codespace sourced from `gha-indie-worker` cannot assume its source-repository token can clone that private repository.

Configure these GitHub Codespaces secrets before creating or rebuilding the canonical infra Codespace:

- `ORES_CLI_READ_TOKEN` — a fine-grained GitHub token limited to read-only Contents access on `ORESoftware/ores-cli`, used only to install the pinned `oresc` source revision;
- `TUNNEL_TOKEN` — the remotely managed Cloudflare Tunnel connector token consumed by `oresc codespace edge up`.

The devcontainer records only secret names/descriptions. During installation it passes `ORES_CLI_READ_TOKEN` through the environment, configures the Git CLI credential helper with `gh auth setup-git`, and enables Cargo's Git CLI fetch path. Never embed the token in a Git URL or argv.

For longer-lived application configuration, retain the fleet SOPS + age model: encrypted values under approved `env/enc/**` paths and no committed decrypted `.env` or tunnel credentials.

`CF_TUNNEL_TOKEN` remains a compatibility runtime input, but `TUNNEL_TOKEN` is canonical.

## Implemented validation

`gha-indie-worker/gha-indie-worker-infra#27` added the devcontainer edge prerequisites. Follow-up #28 hardened the cross-owner private bootstrap and added a Rust static validator for the devcontainer contract.

The validator checks the exact `oresc` revision, pinned devcontainer features, required secret names, Git CLI fetch mode, port 8080 auto-forward suppression, and rejects credential-shaped values embedded in the devcontainer configuration.

Both the local-runtime static contract and infra-isolation workflows executed real runner steps and passed on the #28 head before merge.

## Codespace activation

Devcontainer changes apply to a new or rebuilt Codespace, not retroactively to a currently running container. After configuring the secrets and rebuilding:

```text
just codespace-edge-check
just codespace-edge-up
just codespace-edge-status
```

Use `just codespace-edge-down` for an owned local shutdown. No live Cloudflare tunnel/DNS state is implied by repository readiness alone.

## GitHub Project contract

Track the fleet in a Project named `Codespaces Edge Hosting` with fields: Status, Origin org, Origin repo, Codespace name, Public hostname, Tunnel health, Codespace state, Last verified, and Risk. Recommended views are `By org`, `Tunnel health`, `Blocked`, and `Recently verified`.

The current connector does not expose GitHub Project mutation APIs, so this document defines the tracking contract but does not claim that the Project has been created.

## Exit path

Codespaces are ephemeral and the tunnel disappears when the Codespace stops. Workloads requiring durable availability must graduate to Cloudflare-native hosting or the normal multi-cloud deployment path without changing their public hostname or health contract.
