#!/usr/bin/env python3
"""Read-only, fail-closed *advisory* GitHub governance readiness probe.

This is NOT a substitute for GitHub-enforced rulesets or an independent
trusted required workflow. No credentials, secrets, writes, or private
repository requests are used. Intended for public .github repositories.
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


def fetch_json(url):
    request = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json",
                      "User-Agent": "ores-taxonomy-readonly-protection-audit"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def latest_review_states(reviews):
    """GitHub can return multiple reviews per account; the latest wins."""
    states = {}
    for review in sorted(reviews, key=lambda r: (r.get("submitted_at") or "", r.get("id") or 0)):
        login = (review.get("user") or {}).get("login")
        if login:
            states[login.casefold()] = review.get("state")
    return states


def assess(branch, reviews, codeowners_present, author):
    findings = []
    if branch.get("protected") is not True:
        findings.append("main is not protected")
    protection = branch.get("protection") or {}
    required = protection.get("required_status_checks") or {}
    checks = required.get("checks") or []
    contexts = required.get("contexts") or []
    names = set(contexts)
    names.update(c.get("context") for c in checks if isinstance(c, dict))
    if "taxonomy-admission" not in names:
        findings.append("taxonomy-admission is not listed as a required branch check")
    if not codeowners_present:
        findings.append("CODEOWNERS is absent from the protected base branch")
    states = latest_review_states(reviews)
    independent = [u for u, state in states.items() if
                   state == "APPROVED" and u != author.casefold()]
    if not independent:
        findings.append("no distinct-account APPROVED review is currently recorded")
    # Distinct GitHub accounts do NOT prove distinct humans.
    return findings


def self_test():
    good = {"protected": True, "protection": {
        "required_status_checks": {"checks": [{"context": "taxonomy-admission"}]}}}
    approved = [{"id": 1, "user": {"login": "governance-reviewer"},
                 "state": "APPROVED", "submitted_at": "2026-01-01T00:00:00Z"}]
    def expect(label, branch, reviews, owners, author, expected):
        got = assess(branch, reviews, owners, author)
        if len(got) != expected:
            raise AssertionError(f"{label}: expected {expected} finding(s), got {got}")
    expect("valid-evidence", good, approved, True, "pr-author", 0)
    expect("unprotected-branch", dict(good, protected=False), approved, True, "pr-author", 1)
    expect("missing-required-check",
           {"protected": True, "protection": {"required_status_checks": {"checks": []}}},
           approved, True, "pr-author", 1)
    expect("missing-base-codeowners", good, approved, False, "pr-author", 1)
    expect("unapproved", good, [], True, "pr-author", 1)
    expect("self-approval", good, approved, True, "governance-reviewer", 1)
    dismissed = approved + [{"id": 2, "user": {"login": "governance-reviewer"},
                             "state": "DISMISSED", "submitted_at": "2026-01-02T00:00:00Z"}]
    expect("superseded-approval", good, dismissed, True, "pr-author", 1)
    print("governance readiness self-tests passed: 7")


def audit(repo, base, pr_number, author):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("invalid repository name")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", base):
        raise ValueError("invalid base branch")
    root = f"https://api.github.com/repos/{repo}"
    branch = fetch_json(f"{root}/branches/{urllib.parse.quote(base)}")
    reviews = fetch_json(f"{root}/pulls/{pr_number}/reviews?per_page=100")
    # Conservative: if more review pages exist, do not claim completeness.
    if len(reviews) >= 100:
        raise ValueError("review audit requires pagination; cannot prove current approval")
    owners_url = f"{root}/contents/.github/CODEOWNERS?ref={urllib.parse.quote(base)}"
    try:
        fetch_json(owners_url)
        owners = True
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        owners = False
    findings = assess(branch, reviews, owners, author)
    if findings:
        for problem in findings:
            print(f"UNREADY: {problem}")
        print("GitHub admin must verify effective rulesets/check source and human independence.")
        return 1
    print("PRELIMINARY READINESS ONLY: independently verify effective rulesets, check app and human reviewers.")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--repo")
    parser.add_argument("--base", default="main")
    parser.add_argument("--pr", type=int)
    parser.add_argument("--author")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.repo or not args.pr or not args.author:
        parser.error("--repo, --pr and --author required")
    try:
        return audit(args.repo, args.base, args.pr, args.author)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"UNREADY: governance audit could not be completed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
