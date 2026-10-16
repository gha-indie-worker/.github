# Repository taxonomy: administrator activation checklist

The taxonomy policy does not become mandatory until GitHub independently enforces it. GitHub Actions passing on a pull request is not proof of protected admission.

## Controls to configure after reviewing the pilot

1. Protect the default branch against direct pushes and require an approved pull request. Require an independent reviewer with governance authority; a PR author cannot approve their own change.
2. Require the **taxonomy-admission** check from the **GitHub Actions** app. The producing workflow is **repository-taxonomy-policy**. Confirm the exact context in the GitHub branch rules interface. Avoid ambiguous checks called `validate`.
3. Select and verify a real authorized user/team, then protect these paths with CODEOWNERS review: `/.github/workflows/repository-taxonomy.yml`, `/scripts/validate_repository_taxonomy.py`, `/repository-taxonomy.schema.json`, `/repository-taxonomy.json`, and `/.github/CODEOWNERS`. Do not add a fictional team or an unverified owner.
4. Do not allow changes to the verifier source commit, expected Git blob digests, or workflow definition without that approval. An immutable fetched verifier protects code integrity but does not prevent a PR from deleting the workflow; only independently enforced GitHub rules can enforce that.
5. Keep the pinned validator reachable through a reviewed, retained verifier revision. Never assume a commit on an unmerged branch is a permanent release. Promote to a protected, retained reference only with governance approval.
6. The validator rejects production `reviewed` classifications until an external approval authority is implemented. Repository-provided `review_evidence` is not sufficient to authorize a new VPC, cloud identity, or database scope.
7. Public inventories contain public repositories only. A private org inventory is limited to repositories visible to the authorized GitHub installation; completeness must be checked separately. This metadata does not prove actual production network or database isolation.

## Acceptance evidence

For every pilot repository, record the applicable ruleset or branch-protection settings, the reviewer identity, the latest PR head and successful **taxonomy-admission** check, and merge approval. On private repositories confirm the current GitHub plan supports the required restrictions; if it does not, do not claim that merge enforcement is active.

## CI runner exhaustion

Prefer the source repository's own Actions runners. If its minutes are exhausted, an authorized private carrier in a different organization can test an explicitly approved temporary copy. Do not use a carrier's token to access private source across organization boundaries; and do not copy private code into a public or unauthorized destination. Confirm destination access policy before mirroring, use least privileges, and clean up temporary branches afterwards.
