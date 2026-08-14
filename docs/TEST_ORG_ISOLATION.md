# Test-organization production isolation

Tracking: `DEN-3448`. The reusable gate is stacked on the workflow-governance
linter from `DEN-3426`; both gates are required. Workflow governance rejects
unsafe execution mechanics, while this scanner rejects production identity and
resource scope in repositories owned by organizations ending in `-test`.

## Boundary

The scanner reads bounded local text files only. It does not evaluate GitHub
expressions, execute workflow or repository code, restore caches, invoke
actions, start containers, resolve DNS, or contact a discovered endpoint.
Symlinked files and directories are not followed. SOPS ciphertext under
`env/enc` is not decrypted; plaintext `env/dec` must remain ignored and absent
from commits.

The report contains repository-relative paths, line numbers, rule IDs, input
digests, finding fingerprints, the exact source SHA, and policy/exception/report
digests. It never contains a matched credential, endpoint, account identifier,
or configuration value.

## Required manifest

Every canary has `.github/test-org-isolation.json`:

```json
{
  "schema_version": 1,
  "namespace_prefix": "sample-service-test",
  "domain_suffix": "sample-service.invalid",
  "service_account_prefix": "sample-service-test",
  "storage_prefix": "test/sample-service/",
  "outbound_send_enabled": false,
  "outbound_rate_limit_per_minute": 0,
  "production_connectivity_enabled": false
}
```

Missing or permissive manifest state fails closed. The `.invalid`, `.test`, and
`.example` suffixes are accepted synthetic destinations; loopback, private, and
link-local addresses are also non-production. Other HTTP(S) hosts in scanned
configuration are rejected without being resolved or contacted.

The static rules additionally reject production environments and infrastructure
identities, production/deploy/PAT/cross-organization-write secret names,
privileged production self-hosted runner labels, and SendGrid/Twilio scope in a
test repository. The adjacent workflow-governance linter remains responsible
for immutable action refs, exact concurrency, permissions, unsafe triggers,
attacker-controlled shell interpolation, and reusable-workflow secret flow.

## Exceptions

Exceptions are optional and default to none. Each entry must name one exact
repository, repository-relative path, suppressible rule ID, owner, detailed
rationale, GitHub review URL, and ISO expiry date. Globs, parent traversal,
unknown rules, missing review evidence, expired entries, manifest exceptions,
and unreadable-input exceptions fail closed. One exception cannot expand to a
different repository, path, or rule.

## Reusable action

Pin the action to an immutable central commit and keep checkout credentials
disabled:

```yaml
- uses: gha-indie-worker/.github/test-org-isolation@<40-character SHA>
  with:
    root: .
    repository: ${{ github.repository }}
    source-sha: ${{ github.sha }}
```

The action writes `report.json`, `report.md`, and `report.sarif` under
`.test-org-isolation/`, prints only compact digest-bound status, and fails when
any unsuppressed finding remains. Artifact upload and code-scanning publication
are left to the calling repository so its own permissions and retention policy
remain explicit.

Because the report directory is intentionally hidden, callers that publish the
evidence with `actions/upload-artifact` must set `include-hidden-files: true`:

```yaml
- if: ${{ always() }}
  uses: actions/upload-artifact@<40-character SHA>
  with:
    name: test-org-isolation-${{ github.sha }}
    path: .test-org-isolation/
    include-hidden-files: true
    if-no-files-found: error
```

## Local verification

```bash
python3 scripts/test_org_isolation.py \
  --root /path/to/checked-out-test-repo \
  --repository example-test/service \
  --source-sha 0123456789012345678901234567890123456789 \
  --policy test-org-isolation-policy.json \
  --exceptions test-org-isolation-exceptions.json \
  --format markdown

python3 -m unittest -v scripts.tests.test_test_org_isolation
```

Runtime-generated fixtures cover missing configuration, non-routable test
destinations, production-like secret and infrastructure names, privileged
runners, paid messaging providers, exact exceptions, expiry, deterministic
reports, SARIF, content-free diagnostics, and symlink refusal.
