# Codespaces edge hosting

Issue: #36

## Scope

This is a development/preview hosting tier that uses a GitHub Codespace as an ephemeral origin behind Cloudflare. It is not a production availability tier.

Current GHA Indie Worker origin identity:

- reported Codespace: `supreme-orbit-g4qw69qgj5wcr7v`;
- historical/reported repository: `gha-indie-worker/gha-infra`;
- canonical accessible infra repository: `gha-indie-worker/gha-indie-worker-infra`;
- canonical shared edge ingress: `127.0.0.1:8080`.

New automation should use the canonical current repository identity. If the existing Codespace still reports the historical repository name, treat that as a possible pre-rename artifact rather than creating a second infra authority.

## Implemented request path

```text
browser / API client
  -> Cloudflare DNS / TLS / Access/WAF as configured
  -> remotely managed named Cloudflare Tunnel
  -> cloudflared inside the Codespace
  -> 127.0.0.1:8080
  -> ORESoftware/codespaces-cluster Rust edge
       /api/* -> 127.0.0.1:18090
       /*     -> 127.0.0.1:18091
  -> gha-indie-worker API / web services
```

GitHub port forwarding remains private. Cloudflare must not use a `*.app.github.dev` forwarded-port URL as the origin. The infra devcontainer marks 8080 with `onAutoForward: ignore`.

## Reviewed immutable toolchain

The implemented Codespace stack is pinned to reviewed commits:

- `ORESoftware/ores-cli@d37aa4c1a0b79a292a31e2f16db8622144b0831f`;
- `ORESoftware/ores-compose@8a01df4227a44b0b25741b7ef4a910ec4a4dc75f`;
- `ORESoftware/codespaces-cluster@8c494f4b038a766be06ff29df5a067b6d78c9134`.

The canonical infra repository records those authorities under `config/*.rev` and cross-checks them against devcontainer installation commands and Rust contract tests. A reviewed pin must move consistently across the authority file, installation surface, test expectation, and documentation rather than being edited in only one place.

The public operator surface is:

```text
just codespace-edge-check
just codespace-edge-up
just codespace-edge-status
just codespace-edge-down
```

`just codespace-edge-up` materializes the exact reviewed shared-cluster commit only when necessary, checks it out detached, verifies `HEAD` equals the pin, starts the application compose supervisor, starts the Rust edge on 8080, waits for edge readiness, and only then starts `cloudflared` through `oresc`.

`status` and `down` deliberately do not fetch, fast-forward, or switch the shared checkout while it may own running processes. `down` stops the connector/shared edge before the application compose supervisor and attempts both layers even if one shutdown reports an error.

## Application origin and readiness

The application compose contract no longer uses print-and-exit stubs. Current local application services are long-lived loopback servers:

- API: `127.0.0.1:18090`, with `/healthz` and `/readyz`;
- web: `127.0.0.1:18091`, with `/healthz` and `/readyz`;
- web reaches API through `GHA_INDIE_WORKER_API_HTTP_BASE=http://127.0.0.1:18090`.

Port 8080 belongs only to the shared Rust edge. The edge route contract sends `/api/*` to the API backend and all other application paths to web. Its own `/healthz`, `/readyz`, and `/routes` endpoints remain control-plane endpoints.

The canonical smoke/readiness path for application traffic through the edge is `http://127.0.0.1:8080/api/readyz`; the application `.ores-compose.yaml` itself does not claim port 8080.

## Ownership boundaries

- `gha-indie-worker/gha-indie-worker-infra` owns the local composition, exact application source pin, route table, Codespaces devcontainer, runtime wrappers, and development ingress desired state.
- `ORESoftware/ores-compose` owns exact source materialization, dependency-wave startup/readiness, child supervision, reverse dependency-safe shutdown, and partial-start cleanup.
- `ORESoftware/codespaces-cluster` owns the shared Rust edge and the application compose controller boundary.
- `ORESoftware/ores-cli` owns only the detached Cloudflare connector lifecycle and proves the external loopback origin ready before connector startup.
- the application monorepo remains source aggregation, not a second infra/configuration authority.

## Cross-owner bootstrap and secret boundary

All three ORE tooling repositories are private and cross-owner from `gha-indie-worker`. Configure:

- `ORES_CLI_READ_TOKEN` — a fine-grained GitHub token with read-only Contents access limited to `ORESoftware/ores-cli`, `ORESoftware/ores-compose`, and `ORESoftware/codespaces-cluster`, used only for bootstrap/network operations;
- `TUNNEL_TOKEN` — the connector token for the pre-provisioned remotely managed named Cloudflare Tunnel.

The devcontainer performs a read-only shared-cluster access preflight so insufficient token scope fails during rebuild rather than first activation. Runtime wrappers inject the GitHub token as `GH_TOKEN` only around a required private clone/fetch/bootstrap operation; they do not export it into the long-running process tree.

`oresc@d37aa4c1...` removes `ORES_CLI_READ_TOKEN`, `GH_TOKEN`, `GITHUB_TOKEN`, `TUNNEL_TOKEN`, and `CF_TUNNEL_TOKEN` from generic child command environments before its cloudflared version preflight, detached supervisor, and connector spawn. It selectively restores only canonical `TUNNEL_TOKEN` and the ownership marker where required.

`codespaces-cluster@8c494f4b...` independently strips the same control-plane/tunnel credentials before `ores-compose --help` and `ores-compose up`, preventing those credentials from reaching the application process tree. Its fallback private tooling is pinned rather than pulled from moving Git heads.

For longer-lived application secrets, retain the fleet SOPS + age model: encrypted values under approved `env/enc/**` paths and no committed decrypted `.env`, tunnel token, or credential JSON.

## Validation status

The current infra promotion was semantically reconciled against concurrent lifecycle work rather than selecting one side of overlapping changes wholesale. `gha-indie-worker/gha-indie-worker-infra#40` preserved the newer `ores-compose@8a01df...` authority while promoting `oresc@d37aa4c1...` and `codespaces-cluster@8c494f4b...`.

On the exact reconciled #40 head, all three relevant workflows passed on real GitHub-hosted runners:

- Codespace edge contract;
- local runtime static contract;
- infra isolation contracts.

The Rust contract suite verifies immutable revision files, devcontainer/tool pin parity, scoped cross-owner bootstrap auth, immutable shared-cluster checkout, forbidden credential/legacy-ingress material, and documentation parity.

A GitHub Actions result with zero/null executed steps is capacity/admission non-evidence, not a successful test and not by itself a source failure. Low-risk reviewed changes may use the repository's documented zero-runner exception, but the current GHA edge toolchain promotion has real runner-backed evidence.

## Codespace activation

Repository readiness does not imply the named tunnel is currently live. The activation order in a suitably authorized/rebuilt Codespace is:

1. ensure the exact application source is initialized and the repository doctor/contract checks pass;
2. configure the approved `ORES_CLI_READ_TOKEN` and `TUNNEL_TOKEN` secret inputs;
3. run `just codespace-edge-check`;
4. run `just codespace-edge-up`;
5. verify `just codespace-edge-status` and application readiness through `/api/readyz`;
6. use `just codespace-edge-down` for ordered connector/edge/application shutdown.

The available GitHub connector does not provide a shell inside the running Codespace and does not provide Cloudflare account mutation, so repository readiness must not be described as proof that the public tunnel is active.

## GitHub Project contract

Track the fleet in a Project named `Codespaces Edge Hosting` with fields: Status, Origin org, Origin repo, Codespace name, Public hostname, Tunnel health, Codespace state, Last verified, and Risk. Recommended views are `By org`, `Tunnel health`, `Blocked`, and `Recently verified`.

The current connector does not expose GitHub Project mutation APIs, so this document defines the tracking contract without claiming that the Project exists.

## Exit path

Codespaces are ephemeral. Workloads requiring durable availability must graduate to Cloudflare-native hosting or the normal multi-cloud deployment path while keeping their public hostname and health contract stable where practical.
