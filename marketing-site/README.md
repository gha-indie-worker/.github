# GHA Indie Worker marketing site

This directory is the complete Astro source staged for the future public repository `gha-indie-worker/gha-indie-worker.github.io` and URL `https://gha-indie-worker.github.io/`.

## Canonical planning

- Linear project: [github.com/gha-indie-worker](https://linear.app/denman/project/githubcomgha-indie-worker-941d4102f7dc)
- GitHub Project: [gha-indie-worker-project #1](https://github.com/orgs/gha-indie-worker/projects/1)
- Organization: [gha-indie-worker](https://github.com/gha-indie-worker)
- Publication issue: [gha-indie-worker/.github#8](https://github.com/gha-indie-worker/.github/issues/8)

## Product sources

- `gha-indie-worker.rs`: authenticated Rust build/deploy control surface
- `gha-clone-server.rs`: bounded GitHub Actions-compatible planning and execution research

The page presents the real `build-server.v1` request contract, fixed-profile execution, NATS lifecycle subjects, Postgres durability, Fiducia coordination, and the explicit prohibition on caller-supplied shell commands. It labels the examples as API/event contracts because there is not yet a dedicated polyglot `gha-indie-worker-clients` repository.

## Local validation

```bash
npm install --ignore-scripts --no-audit --no-fund
npm run validate
npm run build
npm run test:browser
```

The staging workflow runs the same static validator and Chromium suite, then publishes the built `dist/` directory as a GitHub Actions artifact. The final Pages repository should commit its own lockfile before release publication.

## Publish

1. Create the public repository `gha-indie-worker/gha-indie-worker.github.io`.
2. Copy this directory to the new repository root while preserving file modes.
3. Commit an npm lockfile produced from the exact dependency versions.
4. Run the validator, build, and Chromium tests.
5. Add the standard Astro GitHub Pages workflow and select **GitHub Actions** as the Pages source.
6. Verify the canonical HTTPS URL and update issue #8, GitHub Project #1, and the Linear project.

The staging repository and artifact are evidence that the source builds. They are not a claim that the Pages repository or public site already exists.
