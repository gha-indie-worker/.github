# Workflow governance linter

Tracking: [DEN-3426](https://linear.app/denman/issue/DEN-3426/cross-org-ci-build-a-reusable-workflow-governance-linter-and-exact)

`workflow_policy_linter.py` is a dependency-free, non-executing analyzer for GitHub Actions workflow files. It converts organization policy into deterministic JSON, text, and SARIF findings tied to the exact policy, exception set, workflow bytes, repository, and source SHA.

## Security boundary

The linter reads workflow text. It does not evaluate expressions, import actions, restore caches, download artifacts, invoke containers, execute workflow commands, contact GitHub, or resolve mutable action tags. Unsupported or ambiguous YAML constructs fail closed as `GHW000` rather than being approximated as safe.

The conservative parser supports the GitHub Actions subset used by the canary repositories: mapping-style triggers, explicit permissions, workflow concurrency, jobs, runner labels, timeouts, steps, `uses`, `run`, `with`, environments, and reusable-workflow secrets. YAML anchors, aliases, tags, merge keys, and tabs require explicit review.

## Enforced rules

| Rule | Contract |
|---|---|
| `GHW001` | Declare top-level workflow permissions, including `{}` when the workflow starts with no token permissions. |
| `GHW002` | Never use `write-all` at workflow or job scope. |
| `GHW003` | Give every executable non-reusable job a bounded `timeout-minutes`. |
| `GHW004` | Pin external actions and reusable workflows to a full 40-character commit SHA. |
| `GHW005` | Pin `docker://` actions to a 64-character `sha256` digest. |
| `GHW006`–`GHW008` | Event-driven workflows declare a complete, static concurrency policy that does not use secrets or attacker-controlled event fields. |
| `GHW009` | `pull_request_target` is denied unless a narrowly scoped, expiring exception receives independent review. |
| `GHW010`–`GHW011` | Pull-request paths cannot reach self-hosted runners, write permissions, protected environments, or inherited secrets. |
| `GHW012` | Do not interpolate pull-request, issue, review, or comment text directly into shell commands. |
| `GHW013` | Enumerate reusable-workflow secrets; `secrets: inherit` is forbidden. |
| `GHW014` | Scheduled workflows declare `SCHEDULE_TIMEZONE`, `RUN_EVIDENCE_SCHEMA`, and `MISSED_RUN_POLICY`. |
| `GHW015` | Every `actions/checkout` step sets `persist-credentials: false`. |
| `GHW016` | `pull_request_target` cannot download artifacts without an exact reviewed exception. |

## Run locally

```bash
python -m py_compile \
  scripts/workflow_policy_linter.py \
  scripts/workflow_policy/*.py \
  scripts/tests/test_workflow_policy_*.py
python -m unittest discover -s scripts/tests -p 'test_workflow_policy_*.py' -v

python scripts/workflow_policy_linter.py \
  --policy workflow-policy.json \
  --exceptions workflow-policy-exceptions.json \
  --repository owner/repository \
  --source-sha "$(git rev-parse HEAD)" \
  --format json \
  --output artifacts/workflow-policy-report.json
```

When no workflow paths are supplied, the CLI examines `.github/workflows/*.yml` and `.yaml`. `--mode enforce` returns nonzero for any unsuppressed error. `--mode audit` returns zero while retaining `valid: false`; it inventories legacy violations but does not create a baseline or silently grandfather new findings.

## Read-only fleet audit

`scripts/fleet_workflow_audit.py` enumerates every repository visible to the authenticated GitHub CLI, resolves each default branch to a 40-character commit, and then fetches workflow blobs by that immutable commit in bounded GraphQL batches. It runs the same parser and policy without cloning or executing target repositories:

```bash
python scripts/fleet_workflow_audit.py \
  --gh "$(command -v gh)" \
  --scanner-source-sha "$(git rev-parse HEAD)" \
  --include-archived \
  --format json \
  --output /tmp/workflow-fleet-report.json
```

The report binds the scanner commit as well as every repository commit and workflow blob identity, content digest, finding, fetch error, and observed API rate-limit state. A repository that GitHub proves is empty is recorded explicitly with `empty_repository: true` and `source_sha: null`; the scanner never invents a commit identity for it. A changed default branch, inaccessible blob, binary or oversized workflow, partial GraphQL response, disabled repository, or missing repository result is never silently called clean. Fetch errors make the run incomplete and nonzero unless a human deliberately selects `--allow-partial`; the report remains `complete=false` either way.

The fleet driver uses only authenticated GitHub metadata/content reads. It does not dispatch, rerun, approve, enable, or execute Actions; billing-aware test dispatch remains a separate reviewed operation after the static report identifies a safe canary.

## Exact-head evidence

The JSON report contains:

* policy version and SHA-256 digest;
* exception-set SHA-256 digest;
* repository and source SHA supplied by the caller;
* SHA-256 digest for every workflow input;
* deterministic, sorted findings with rule, path, line, job, severity, and suppression metadata;
* counts for files, findings, suppressions, unsuppressed errors, and final validity.

The SARIF rendering carries the same policy and exception digests and exact-head automation ID. No wall-clock timestamp is included, so identical inputs and arguments produce byte-stable output.

## Exceptions

Exceptions use `workflow-policy-exceptions.json` and the committed schema. Each item must identify one exact workflow path, one suppressible rule, an owner, a substantive rationale, an ISO expiration date, and optionally one exact job. Wildcards, unknown rules, expired entries, short rationales, and attempts to suppress policy/exception validation are rejected as `GHW901`.

An exception suppresses only matching findings. It does not alter the policy, hide the underlying result, authorize workflow execution, or bypass branch protection and independent review.

## Canary rollout

The initial enforcement workflow validates this linter plus three existing organization-policy workflows. The next rollout stage is audit-only evidence in at least four unrelated `*-test` organizations; enforcement follows only after each violation is remediated or represented by a narrow expiring exception. Production organizations remain out of scope until exact-head canaries pass independently of GitHub-hosted Actions as well as on the hosted reference lane.
