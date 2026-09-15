# Codespaces edge hosting

Issue: #36

## Scope

This is a development/preview hosting tier that uses a GitHub Codespace as an ephemeral origin behind Cloudflare. It is not a production availability tier.

Current GHA Indie Worker origin:

- reported Codespace: `supreme-orbit-g4qw69qgj5wcr7v`
- reported repository: `gha-indie-worker/gha-infra`
- current canonical accessible infra repository: `gha-indie-worker/gha-indie-worker-infra`
- canonical local port: `8080`

Before automating future Codespaces, reconcile whether the existing Codespace was created before an infra-repository rename. New automation should use the canonical repository identity.

## Request path

```text
browser
  -> Cloudflare DNS / TLS / optional Access
  -> remotely managed named Cloudflare Tunnel
  -> cloudflared inside the Codespace
  -> http://127.0.0.1:8080
  -> preview/status server
```

The GitHub forwarded port remains private. Cloudflare must not use the `*.app.github.dev` forwarded-port URL as the origin.

## Origin contract

Expose `/`, `/healthz`, `/readyz`, and `/version`; keep the process stateless and bind to `127.0.0.1:8080` unless local tooling requires otherwise. `/version` may expose repo/version/commit metadata but never secrets.

## Infrastructure integration

Extend the existing fleet infra conventions rather than adding an unrelated Terraform root. `gha-indie-worker/gha-indie-worker-infra` is the reference for:

- reusable `modules/<provider>/...` child modules;
- state-owning `environments/<environment>/<state-root>/...` roots;
- provider-native Supabase/Neon/Cloudflare trees where appropriate;
- `_apps/gha-monorepo` as an exact-revision, non-authoritative application submodule;
- `dist/` as generated/local output;
- `.ores-infra.toml`, `.zpkg.toml`, and related ORES contracts.

## Tunnel and secrets

Use a remotely managed named tunnel per Codespace. Protect administrative/diagnostic routes with Cloudflare Access and add WAF/rate limits where appropriate.

Target the fleet SOPS + age pattern: keep only bootstrap material in GitHub Codespaces secrets; place `CF_TUNNEL_TOKEN` and environment values in encrypted `env/enc/codespaces.env.enc`; keep `env/dec/**`, plaintext `.env`, and tunnel credentials out of Git.

A direct `CF_TUNNEL_TOKEN` Codespaces secret is acceptable for the proof of concept.

## Lifecycle commands

Expose commands equivalent to:

```text
just codespace-edge-up
just codespace-edge-status
just codespace-edge-down
```

The up command starts the local server plus `cloudflared`, waits for `/readyz`, and fails closed if required bootstrap material is absent.

## GitHub Project contract

Track the fleet in a Project named `Codespaces Edge Hosting` with fields: Status, Origin org, Origin repo, Codespace name, Public hostname, Tunnel health, Codespace state, Last verified, and Risk. Recommended views are `By org`, `Tunnel health`, `Blocked`, and `Recently verified`.

## Exit path

Codespaces are ephemeral and the tunnel disappears when the Codespace stops. Workloads requiring durable availability must graduate to Cloudflare-native hosting or the normal multi-cloud deployment path without changing their public hostname or health contract.
