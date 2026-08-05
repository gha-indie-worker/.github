<!-- ore-org-baseline:begin -->
# Repository relationships for `gha-indie-worker`

This file is rendered from `repository-relationships.json`. The JSON registry is authoritative.

- Audience: `public`
- Repositories represented: **3**
- Relationships represented: **2**
- Inventory digest: `sha256:15cf0a90ab9736cc87728d6419d1965185f6d3b7570d9abdf0ec77b06017bec6`

## Immutable routing identity

| Field | Value |
|---|---|
| Mapping ID | `context:gha-indie-worker` |
| GitHub owner ID | `312674563` |
| Linear project ID | `69d23e78-b898-49bf-bc84-d319bdaa2059` |
| Linear team ID | `eb8ab169-5afe-4b6f-9cab-3f2aa3e887dc` |

## Repositories

| Repository | Visibility | Roles | Archived |
|---|---|---|---|
| `gha-indie-worker/.github` | `public` | `community-health`, `governance`, `relationship-registry` | no |
| `gha-indie-worker/gha-clone-server.rs` | `public` | `repository` | no |
| `gha-indie-worker/gha-indie-worker.rs` | `public` | `repository` | no |

## Relationships

| From | Type | To | Status | Required |
|---|---|---|---|---|
| `gha-indie-worker/.github` | `governs` | `gha-indie-worker/gha-clone-server.rs` | `declared` | yes |
| `gha-indie-worker/.github` | `governs` | `gha-indie-worker/gha-indie-worker.rs` | `declared` | yes |

## Editing relationships

Put reviewed public declarations in `repository-relationships.manual.json`; do not edit the generated registry directly.
Private repository names and private-only relationships belong in the private `approved-private-registry` mirror.
Inferred edges are advisory and must remain visibly labeled until reviewed.
<!-- ore-org-baseline:end -->
