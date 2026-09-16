# ores-compose local and Codespaces runtime

Status: **core runtime implemented and pinned; external ingress acceptance still incomplete**. The organization now has one promoted infra-owned `ores-compose` application contract, an exact monorepo source revision, runnable API/web services, a pinned Codespaces toolchain, and independent executable evidence for the application/runtime boundary. Cloudflare Access/tunnel end-to-end acceptance, a fresh real Codespace rebuild, and a fresh laptop acceptance run remain separate evidence gates and are not claimed complete here.

## Landed evidence

The following implementation is now merged rather than merely planned:

- `gha-indie-worker-infra` owns the canonical `.ores-compose.yaml`, local/Codespaces runtime validator, devcontainer, shared-edge routing config, and exact private-tool revision files;
- application source is pinned to `gha-indie-worker-monorepo@68de4b122d06621805bfb810367488bd171272c7`;
- the API and web services are long-lived loopback listeners on `127.0.0.1:18090` and `127.0.0.1:18091`, with separate health/readiness boundaries;
- the shared edge revision is pinned by `config/codespaces-cluster.rev` at `9d1e9709fa2ba0fccdf920731cdfa5673a77e5f6` and owns loopback port `8080`;
- Codespaces bootstrap pins `ORESoftware/ores-cli@c854130ee147e9793a3af8736e90241630a5c934` and `ORESoftware/ores-compose@8a01df4227a44b0b25741b7ef4a910ec4a4dc75f` through reviewed `config/*.rev` authorities;
- `ores-compose@8a01df4227a44b0b25741b7ef4a910ec4a4dc75f` is the merged lifecycle hardening with pre-network admission, exact source materialization, checkout-path lifetime locking, dependency-safe reverse shutdown waves, and partial-start cleanup;
- infra promotion through `gha-indie-worker-infra#39` is merged at `d1ab40cf05c205496634af349a442b8955d3f109` after its Rust/local-runtime/Codespace-edge contracts executed real steps and passed;
- independent `gha-indie-worker-test` certification has executed exact-SHA API/web rustfmt, strict Clippy, tests, builds, and paired live readiness/health checks;
- the test organization now also contains a required-private-auth production-manifest lane. That lane must not be counted as live `ores-compose up` evidence unless its scoped `ORE_SOURCE_TOKEN` checkout and subsequent parser/plan/up steps actually execute.

These facts do **not** imply that the Cloudflare ingress acceptance list below has been fully exercised against both a fresh laptop and a fresh Codespace.

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
loopback shared Rust edge / ores-compose-controlled services
        |
        +--> healthy web service
        +--> healthy API service
```

Cloudflare Tunnel must never be configured to proxy directly to an arbitrary application container or request-selected process. The committed local routing boundary is loopback-only and admitted by reviewed configuration.

## Source and configuration authority

`gha-indie-worker/gha-indie-worker-infra` is the single authority for the local composition contract. It owns the canonical `.ores-compose.yaml`, local runtime validation, Codespaces entry configuration, and Cloudflare development-ingress desired state.

The compose source block points to `https://github.com/gha-indie-worker/gha-indie-worker-monorepo.git` at an **exact 40-hex commit SHA**. The promoted source is `68de4b122d06621805bfb810367488bd171272c7`. `ores-compose` materializes only the reviewed exact commit and must not resolve a branch, tag, or other moving ref at execution time.

The monorepo is source aggregation, not a second composition authority. It must not grow a competing `.ores-compose.yaml`.

The infra manifest declares the locally runnable services, dependencies, health/readiness checks, runtime choice, environment, and routing assumptions. Managed dependencies such as hosted databases or shared authentication are represented through approved runtime configuration; credentials never belong in the manifest.

## Execution modes

The same infra-owned manifest supports two execution locations.

### Developer laptop

The developer clones the infra repository, obtains approved runtime credentials from the local secret mechanism, and uses the checked-in bootstrap/doctor lifecycle. `ores-compose` owns exact source materialization, build/start ordering, health/readiness, and dependency-safe shutdown. The shared Rust edge owns loopback port `8080` and routes only to declared local API/web backends.

A named `cloudflared` tunnel runs on the same machine and forwards only to the reviewed loopback ingress boundary.

### GitHub Codespaces

The infra repository is the Codespaces entry repository. Its checked-in `.devcontainer/` installs the reviewed exact private-tool revisions plus `cloudflared`, Git/submodule support, and required Rust tooling. It does **not** duplicate the service graph.

`ORES_CLI_READ_TOKEN` is the bootstrap/network credential for the three reviewed private ORE tooling repositories and is not exported into long-running application, edge, or tunnel processes. `TUNNEL_TOKEN` is separate tunnel runtime material. The devcontainer contains neither secret value.

After creation, the same `.ores-compose.yaml` materializes the exact monorepo revision and starts the same logical API/web graph used on a laptop.

## Hostnames and routing

Use first-level development hostnames because they are straightforward to protect with Cloudflare Access and normal TLS handling:

- `local.indiebuild.dev` — laptop-backed interactive surface;
- `codespace.indiebuild.dev` — Codespaces-backed interactive surface;
- `hooks.indiebuild.dev` / `ci-laptop.indiebuild.dev` — separate signed machine/webhook surfaces where interactive Access is inappropriate.

The local shared edge route table is explicit:

```text
/api/* -> API 127.0.0.1:18090, strip /api
/*      -> web 127.0.0.1:18091
```

Port `8080` belongs to the shared Rust edge only. Application services must not bind it directly.

Laptop and Codespaces must use separate named tunnels when both can be active. Do not attach two independent developer machines as interchangeable connectors behind one hostname: that could mix unrelated local session state.

## Cloudflare Access and tunnel credentials

Every interactive development hostname is deny-by-default behind Cloudflare Access. Browser use gets an interactive operator policy. Non-browser automation gets a separately reviewed signed/service-auth surface rather than weakening the human policy.

Tunnel credentials are runtime secrets:

- never commit tunnel credentials or tokens;
- never put a tunnel token in `.ores-compose.yaml`;
- never pass a long-lived tunnel credential as a request-controlled value;
- prefer a named tunnel with runtime-only secret material;
- materialize credentials into ignored, permission-restricted runtime paths where a credential file is used;
- logs and diagnostics may identify the tunnel/hostname but must not print credential contents.

Committed Cloudflare configuration may contain public tunnel/DNS identifiers, but never a credential.

## ores-compose responsibilities

The local orchestrator is deliberately stricter than a generic process launcher. It must:

1. admit only projects/services declared by trusted `.ores-compose.yaml` configuration;
2. bind activation to the exact reviewed source commit;
3. complete runtime/replica admission before source network access;
4. serialize materialization of the same checkout path and hold that lock for the supervisor lifetime;
5. expose liveness separately from traffic readiness;
6. start dependency waves in admitted order and stop them in reverse dependency order;
7. signal a shutdown wave before waiting on its members;
8. clean up already-started work after a later-wave or partial-start failure;
9. route only to healthy, locally/private resolved backends;
10. fail closed when source checkout, health, readiness, runtime planning, or lifecycle state is ambiguous.

The pinned `ores-compose@8a01df4227a44b0b25741b7ef4a910ec4a4dc75f` implements the lifecycle/source slice above. Future pin changes must advance the reviewed `config/ores-compose.rev` authority and all consuming validation together.

## Developer workflow

The implemented operator flow is now:

```text
1. clone gha-indie-worker-infra
2. obtain approved laptop/Codespaces bootstrap secret material
3. run scripts/dev/bootstrap and scripts/dev/doctor
4. ores-compose reads infra-owned .ores-compose.yaml
5. ores-compose verifies/materializes exact monorepo 68de4b12...
6. API starts on 127.0.0.1:18090
7. web starts on 127.0.0.1:18091 after its dependency boundary
8. shared Rust edge owns 127.0.0.1:8080 and routes /api vs /
9. cloudflared may start only against the reviewed local edge boundary
10. Access-protected external requests may then reach admitted routes
```

The wrappers orchestrate reviewed tools and secret boundaries; they are not a second configuration language.

## Ownership

- `gha-indie-worker-infra`: `.ores-compose.yaml`, reviewed tool revisions, local defaults, Cloudflare development desired state, devcontainer, bootstrap/doctor/tunnel scripts, and shared-edge route table.
- `gha-indie-worker-monorepo`: exact source aggregation/submodule graph only.
- individual service repositories: source code, service-local tests/build definitions, generated runtime contracts, and documented local health behavior.
- `ORESoftware/ores-compose`: generic orchestration, exact source materialization, admission, health/readiness, lifecycle ordering/cleanup, runtime adapters, and load-balancing primitives.
- `gha-indie-worker-docs`: detailed operator runbook and acceptance evidence.
- `gha-indie-worker-test`: independent exact-SHA executable conformance.
- Linear `github.com/gha-indie-worker`: priority, milestones, dependencies, and implementation status.

## Acceptance gate

The integration is considered fully accepted only when all of the following have executable evidence:

- [x] one canonical infra-owned manifest pins an exact monorepo commit;
- [x] API and web revisions remain live together behind separate loopback readiness/health boundaries;
- [x] source/gitlink/tool revisions are immutable and cross-checked by infra contracts;
- [x] dependency ordering is independently certified for the API/web graph;
- [x] Codespaces bootstrap credentials are constrained to the private-tool network/bootstrap boundary by static contracts;
- [ ] a fresh real laptop clone completes bootstrap/doctor/start/stop with approved secret material;
- [ ] a fresh real Codespace rebuild completes bootstrap/doctor/start/stop with authorized Codespaces secrets;
- [ ] the private-source production-manifest certification executes `ores-compose check`, `plan`, and live `up` against promoted infra using the scoped `ORE_SOURCE_TOKEN`;
- [ ] an anonymous external request is rejected by Cloudflare Access;
- [ ] an admitted external request traverses Access -> tunnel -> local edge -> healthy declared service;
- [ ] an unknown project/service route fails closed and does not launch arbitrary work;
- [ ] the tunnel origin cannot be changed by request data into an RFC1918, metadata, public-Internet, or arbitrary local target;
- [ ] tunnel/database/auth credentials do not appear in Git, process arguments, or logs;
- [ ] stopping/unhealthing a backend removes it from routing and recovery is deterministic through the external edge;
- [ ] laptop and Codespaces can run concurrently without requests crossing between their sessions;
- [ ] local startup is demonstrated not to mutate production DNS, production Cloud Run/Kubernetes state, or persistent provider state.

Unchecked items are evidence gaps, not implied failures.

## Delivery state

1. **Done:** promote exact-source/lifecycle `ores-compose` and pin it through reviewed infra revision authority.
2. **Done:** add infra-owned `.ores-compose.yaml` with exact monorepo source and runnable API/web graph.
3. **Done at repository-contract level:** add bootstrap/doctor and local tunnel/edge lifecycle boundaries.
4. **Done at repository-contract level:** add infra Codespaces devcontainer with scoped private-tool bootstrap credentials and no duplicate compose graph.
5. **Partially done:** Cloudflare infra has separate interactive vs signed-machine surface concepts; full live Access/tunnel acceptance remains to be demonstrated.
6. **In progress:** independent test org contains source/lifecycle and runnable API/web conformance; the credential-backed promoted-manifest live lane must execute after `ORE_SOURCE_TOKEN` is available.
7. **Deferred:** expand additional local services only after the remaining API/web external-ingress acceptance cases are green.

## GitHub Actions budget note

GitHub Actions runs that end as `startup_failure` with **zero jobs/zero executed steps** are runner-admission/budget infrastructure non-evidence, not source success or source failure. Do not weaken tests merely to make those runs green. A zero-step run can be ignored for merge readiness only when the change has sufficient semantic review/evidence and no independent approval/protection requirement remains. Any job that executes steps and fails remains real evidence that must be diagnosed.
