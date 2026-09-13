# Local development and PR verification

The canonical local-development topology for this GitHub organization lives in:

`gha-indie-worker/gha-indie-worker-infra/.ores-compose.yaml`

Do not copy independent `.ores-compose.yaml` files into every application repository. The `*-infra` repository owns the org-level process/container graph, local service discovery, private session networking, load-balancer defaults, external-service fallbacks, Cloudflare Tunnel sidecars, and cross-repository startup order.

Application repositories own their implementation-specific launch surfaces. `ores-compose discover` may inspect checked-out repositories for conventional `Dockerfile*` and `entrypoint.sh` files and use those as launch hints when the infra topology does not explicitly provide a command/image.

## PR verification

`gha-indie-worker` is the external CI coordinator when GitHub-hosted Actions minutes are unavailable. For a pull-request webhook it should:

1. bind work to the exact PR head SHA;
2. resolve this org's `gha-indie-worker-infra/.ores-compose.yaml`;
3. create an isolated `pr-<number>-<sha>` ores-compose session;
4. start the org topology (or lazily start services through the ores-compose Rust load balancer);
5. read the PR revision's `.github/workflows/*.yml` files and execute the supported workflow subset against that session;
6. fail closed on unsupported workflow constructs rather than silently skipping them;
7. publish pending/success/failure back to the exact GitHub commit via the GitHub API;
8. tear down or retain the session according to the CI retention policy.

The ores-compose load balancer is part of the local topology. Port-bearing server services default to at least two instances behind the Rust LB, while infrastructure/one-shot services are not automatically replicated.

Cloudflare Tunnel exposure is an ingress adapter, not the service network itself. The local control plane remains session-scoped and should prefer Unix-domain sockets on Unix hosts.
