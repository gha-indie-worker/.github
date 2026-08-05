# gha-indie-worker organization handbook

> Shared operating defaults for repositories maintained under **gha-indie-worker**. Repository-local policy may strengthen these rules but should not silently weaken them.

## Mission

gha-indie-worker maintains independent and self-hosted GitHub Actions-compatible worker, runner, scheduling, and execution infrastructure. This `.github` repository is the canonical home for shared policy, reusable templates, community health files, and planning links.

## Repository contract

Each active repository must document purpose, ownership, maturity, supported platforms and workflow features, development and test commands, authoritative job and protocol formats, release and rollback procedures, compatibility policy, and GitHub Project/Linear links. Worker components should also document registration and identity, isolation, secret lifecycle, permissions, scheduling, concurrency, cancellation, timeouts, caching, artifacts, log redaction, cleanup, observability, quotas, and crash recovery.

## Change workflow

1. Anchor work in an issue, Linear item, or documented maintenance objective.
2. Keep branches and pull requests focused.
3. Explain motivation, scope, tenant and supply-chain risk, validation, compatibility, migration, and rollback.
4. Test registration, denied permissions, cancellation, timeout, concurrent jobs, cache/artifact failure, malicious workflow input, crash, restart, and cleanup paths as relevant.
5. Resolve conflicts semantically by reconstructing both sides' intent.
6. Prefer squash merges for focused work unless commit structure materially improves auditability.

## Evidence, security, and documentation

Pull requests should include reproducible commands, synthetic workflows, expected and observed job states, negative-path and load evidence, documentation updates, and CI or local-equivalent results. Never commit credentials, runner tokens, workflow secrets, signing material, or sensitive logs. Follow `SECURITY.md` for private reporting. Use least privilege and strong workload isolation; pin actions/images, verify provenance, redact logs, and record important compatibility, scheduling, and security decisions.

## Planning ownership

GitHub owns code, reviews, checks, releases, and delivery evidence. Linear owns priority, dependencies, sequencing, and cross-project planning. The organization GitHub Project is the cross-repository execution view; see `PROJECTS.md` for routing details.

## Organization health

- [ ] Profiles, descriptions, topics, and READMEs are current.
- [ ] Community health files and reusable issue/PR guidance are present.
- [ ] Identity, isolation, secrets, permissions, scheduling, cleanup, logs, artifacts, and recovery are documented.
- [ ] Required checks cover malicious workflow input, cancellation, failure, compatibility, load, and supply-chain risk.
- [ ] Stale repositories are archived or clearly marked.
- [ ] GitHub Project and Linear links resolve and reflect completed work.
