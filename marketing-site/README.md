# GHA Indie Worker marketing site

This directory is the complete Astro source staged for the future public repository `gha-indie-worker/gha-indie-worker.github.io` and URL `https://gha-indie-worker.github.io/`.

## Canonical planning

- Linear project: [github.com/gha-indie-worker](https://linear.app/denman/project/githubcomgha-indie-worker-941d4102f7dc)
- GitHub Project: [gha-indie-worker-project #1](https://github.com/orgs/gha-indie-worker/projects/1)
- Organization: [gha-indie-worker](https://github.com/gha-indie-worker)

## Product sources

- `gha-indie-worker.rs`: authenticated Rust build/deploy control surface
- `gha-clone-server.rs`: GitHub Actions-compatible execution research and supporting server work

The page presents the real `build-server.v1` request contract, fixed-profile execution, NATS lifecycle subjects, Postgres durability, Fiducia coordination, and the explicit prohibition on caller-supplied shell commands. It labels the examples as API/event contracts because there is not yet a dedicated polyglot `gha-indie-worker-clients` repository.

## Publish

1. Create the public repository `gha-indie-worker.github.io` in the `gha-indie-worker` organization.
2. Copy this directory to the new repository root.
3. Run `npm install && npm run build`.
4. Add the standard Astro GitHub Pages workflow and select **GitHub Actions** as the Pages source.
5. Verify the canonical HTTPS URL and update the linked GitHub and Linear tickets.
