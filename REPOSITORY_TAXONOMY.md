# Repository taxonomy and trust boundaries

This org-level registry is in [repository-taxonomy.json](./repository-taxonomy.json), validated against [repository-taxonomy.schema.json](./repository-taxonomy.schema.json). It lists **public repositories only** as of 2026-10-15. A public `.github` must never publish private repository names or inventory counts.

Every listed repository declares `category`, `trust_domain`, `source_authority`, `release_unit`, `deployment_targets`, `database_scope`, and `lifecycle`. Classifications derived from names are **provisional**, indicated by `inferred-needs-review`. `unverified` means unknown, not `none` or permission granted. An empty deployment-target array records **zero approved targets in this manifest**, not proof a workload has none. Artifact identifiers, VPC IDs, and cloud identities require an approved owner-supplied source of truth.

## Mandatory isolation

- Admin web, admin API, and admin MCP are independently deployed and independently authorized, with separate VPC/service boundaries as required by the security architecture, even when source shares a workspace.
- The admin database and application database have distinct credentials, network access and least-privilege roles. App workloads cannot infer permission to reach the admin database from a repository name or shared library.
- VPN/SSH administrative access is separately restricted; private workload links require explicit allowlists and authenticated service identities. A GitHub source repository is not a VPC boundary.
- No CI or deployment system may treat an inferred or unverified classification as authorization. Review trust domain, data access, production environments, VPCs, cloud identity, release unit, and lifecycle against actual deployment/IaC evidence before promotion.
- Keep privileged deployment metadata and private repository inventories in access-restricted systems, not this public registry. Preserve existing organization repository and infrastructure policies; this manifest does not override them.

## Registry maintenance

Keep all public repositories listed in public registries; if the `.github` repository itself is private, reconcile the full authorized organization inventory. A repository rename, new service, privileged capability, deploy target, or DB scope change requires a reviewed update. Ensure no duplicate repository keys, check schema validation, and do not convert `unverified` to `reviewed` without supporting evidence.
