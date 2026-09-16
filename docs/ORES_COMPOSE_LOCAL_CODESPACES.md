# ores-compose local and Codespaces runtime

Status: **planned integration contract**. This document defines the organization-level target for running `gha-indie-worker` locally on a developer laptop or in GitHub Codespaces through `ORESoftware/ores-compose` and Cloudflare Tunnel. It does not claim that every implementation item below is merged today.

## Purpose

A developer should be able to start the same reviewed `gha-indie-worker` composition on either a laptop or a Codespace, expose it through an authenticated Cloudflare Tunnel, and reach web/API services through stable `indiebuild.dev` development URLs without giving Cloudflare direct access to arbitrary local processes, Docker ports, or private networks.

The design has one composition authority and one ingress trust boundary:

```text
browser / API client
        |
        v
Cloudflare Access
        |
        v
named Cloudflare Tunnel
        |
        v
cloudflared on laptop OR Codespace
        |
        v
loopback / UDS ores-compose machine gateway
        |
        v
catalog admission + exact-revision activation
        |
        v
ores-compose session load balancer
        |
        +--> healthy web replica(s)
        +--> healthy API replica(s)
        +--> other explicitly declared local services
```

Cloudflare Tunnel must never be configured to proxy directly to an arbitrary application container or process. The public tunnel origin is the local `ores-compose` gateway only.

## Source and configuration authority

`gha-indie-worker/gha-indie-worker-infra` is the single authority for the local composition contract. It will own the canonical `.ores-compose.yaml` and the Cloudflare development-ingress desired state.

The compose source block points to `https://github.com/gha-indie-worker/gha-indie-worker-monorepo.git` at an **exact 40-hex commit SHA**. The monorepo already aggregates the API server, web server, libraries, clients, sync, E2E, Flutter, desktop, sidecar, and infra repositories as submodules. `ores-compose` materializes only the reviewed exact commit and must not resolve a branch, tag, or other moving ref at execution time.

The monorepo is source aggregation, not a second composition authority. It must not grow a competing `.ores-compose.yaml`.

The infra manifest declares the locally runnable services, their dependencies, health/readiness checks, runtime choice, resource limits, and load-balancer policy. Managed dependencies such as hosted databases or shared authentication are represented through approved environment-backed endpoints or explicit optional local profiles; credentials never belong in the manifest.

## Execution modes

The same infra-owned manifest supports two execution locations.

### Developer laptop

The developer clones the infra repository, obtains approved runtime credentials from the local secret mechanism, and runs the `ores-compose` supervisor locally. Host processes and OCI containers may be mixed according to the manifest. The supervisor owns session state, exact source materialization, build/start ordering, health, readiness, logs, and safe local cleanup.

A named `cloudflared` tunnel runs on the same machine and forwards only to the loopback/UDS machine gateway published by `ores-compose`.

### GitHub Codespaces

The infra repository is the Codespaces entry repository. A checked-in `.devcontainer/` definition installs or verifies the pinned Rust/tooling prerequisites, `zed-pkg`, `ores-compose`, `cloudflared`, Git/submodule support, and the required OCI runtime. It does **not** duplicate the service graph.

Codespaces secrets provide only runtime secret material. The devcontainer must not contain a tunnel token, database credential, or other live secret. After creation, the same `.ores-compose.yaml` materializes the exact monorepo revision and starts the same logical service graph as the laptop path.

## Hostnames and routing

Use first-level development hostnames because they are straightforward to protect with Cloudflare Access and are covered by normal TLS handling. The initial target is:

- `local.indiebuild.dev` — laptop-backed tunnel;
- `codespace.indiebuild.dev` — Codespaces-backed tunnel.

Inside each hostname, route by path rather than by unbounded dynamic subdomains:

```text
/p/gha-indie-worker/<session>/<service>/...
```

Deep names such as `api.project.session.local.indiebuild.dev` are not part of the contract.

Laptop and Codespaces must use separate named tunnels when both can be active. Do not attach two independent developer machines as interchangeable connectors behind one hostname: Cloudflare may distribute requests between connectors, which would mix unrelated local session state. A future explicit multi-machine scheduler may change this, but ordinary developer tunnels are one hostname -> one execution machine.

## Cloudflare Access and tunnel credentials

Every development hostname is deny-by-default behind Cloudflare Access. Browser use gets an interactive operator policy. Non-browser automation, if required, gets a separately reviewed service-auth policy rather than weakening the human policy.

Tunnel credentials are runtime secrets:

- never commit tunnel credentials or tokens;
- never put a tunnel token in `.ores-compose.yaml`;
- never pass a long-lived tunnel token as a command-line argument where it can appear in process listings;
- prefer a named tunnel with a runtime-only credential file or equivalent secret-mounted credential;
- on a laptop, materialize credentials from the approved local secret store into an ignored, permission-restricted runtime path;
- in Codespaces, materialize from an authorized Codespaces secret into a runtime-only path after container creation;
- logs and diagnostics may identify the tunnel/hostname but must not print credential contents.

The committed Cloudflare configuration may contain public tunnel/DNS identifiers and a placeholder credential-file path, but never the credential itself.

## ores-compose responsibilities

The local gateway is deliberately stricter than a generic reverse proxy. It must:

1. admit only projects/services declared by trusted `.ores-compose.yaml` configuration;
2. bind activation to the exact reviewed source commit;
3. serialize/fence activation so stale supervisors cannot republish ingress;
4. retain incoming requests only within bounded budgets while cold-start work runs;
5. expose liveness separately from traffic readiness;
6. route only to healthy, locally/private resolved backends;
7. keep container/private addresses below the supervisor trust boundary;
8. reject arbitrary external TCP targets and filesystem sockets outside its runtime root;
9. provide attach/ps/logs/exec/restart/doctor-style operator surfaces without exposing secrets;
10. fail closed when source checkout, health, readiness, lease/fencing, or durable state is ambiguous.

The current active `ores-compose` development stack already models these boundaries, but promotion/release of that stack is a dependency of this plan. Until the needed stack is merged/released and pinned, the integration status remains **Planned**, not **Have**.

## Developer workflow

The intended operator flow is:

```text
1. clone gha-indie-worker-infra
2. obtain approved laptop/Codespaces secret material
3. run the local doctor/bootstrap command
4. ores-compose reads infra-owned .ores-compose.yaml
5. ores-compose fetches/verifies the exact monorepo commit
6. ores-compose builds/starts the declared services
7. /healthz proves supervisor/process liveness
8. /readyz proves a routable local system exists
9. cloudflared starts against only the local gateway
10. Access-protected external requests reach the declared service route
```

The implementation should provide boring wrappers such as `scripts/dev/bootstrap`, `scripts/dev/doctor`, and `scripts/dev/tunnel`; these wrappers orchestrate approved tools and secret-file paths but do not become a second configuration language.

## Ownership

- `gha-indie-worker-infra`: `.ores-compose.yaml`, local environment defaults, Cloudflare development DNS/Access/tunnel desired state, Codespaces entry configuration, and bootstrap/doctor/tunnel scripts.
- `gha-indie-worker-monorepo`: exact source aggregation/submodule graph only.
- individual service repositories: source code, service-local tests/build definitions, and documented local command/health behavior.
- `ORESoftware/ores-compose`: generic orchestration, source materialization, machine/session gateway, health/readiness, runtime adapters, fencing, and load balancing.
- `gha-indie-worker-docs`: detailed operator runbook and acceptance evidence.
- Linear `github.com/gha-indie-worker`: priority, milestones, dependencies, acceptance criteria, and implementation status.

## Acceptance gate

The integration is considered working only when all of the following have executable evidence:

- one canonical infra-owned manifest runs on both a fresh laptop clone and a fresh Codespace;
- the manifest pins and verifies an exact monorepo commit;
- web and API do not become externally routable before readiness succeeds;
- an anonymous request is rejected by Cloudflare Access;
- an admitted request traverses Access -> tunnel -> local gateway -> healthy declared service;
- an unknown project/service route fails closed and does not launch arbitrary work;
- the tunnel origin cannot be changed by request data into an RFC1918, metadata, public Internet, or arbitrary local target;
- tunnel/database/auth credentials do not appear in Git, process arguments, or logs;
- stopping/unhealthing a backend removes it from routing and recovery is deterministic;
- laptop and Codespaces can run concurrently without requests crossing between their sessions;
- rebuilding a Codespace with only repository contents plus authorized Codespaces secrets reproduces the environment;
- a fresh laptop bootstrap with only repository contents plus the approved secret store reproduces the environment;
- local startup never mutates production DNS, production Cloud Run/Kubernetes state, or persistent provider state.

## Delivery sequence

1. Promote a reviewed `ores-compose` stack that contains the trusted config/source, machine gateway, health/readiness, fencing, and configured load-balancer behavior; publish/pin it through the normal package path.
2. Add the infra-owned `.ores-compose.yaml` using the exact monorepo source contract and a minimal API/web service graph first.
3. Add laptop `bootstrap`, `doctor`, and secure named-tunnel startup using a credential file rather than a CLI token.
4. Add the infra Codespaces devcontainer and secret-materialization/bootstrap path; keep the compose graph out of devcontainer JSON.
5. Extend Cloudflare infra from the existing `local` ingress concept to explicit laptop and Codespaces first-level hostnames/Access applications/tunnel bindings.
6. Add end-to-end tests for anonymous denial, exact-source activation, readiness gating, API/web routing, backend failure, and laptop/Codespace isolation.
7. Expand the manifest to additional local services only after the API/web path is green and reproducible.

## GitHub Actions budget note

For this organization, GitHub Actions runs that end as `startup_failure` with **zero jobs/zero executed steps** are caused by the GitHub Actions budget/minutes being exhausted. Treat those runs as infrastructure non-evidence, not as source or workflow-definition failures. Do not weaken tests or rewrite workflows merely to make zero-job runs green; use real stepful evidence, local execution, or the independent `*-test` organization where appropriate.
