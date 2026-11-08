#!/usr/bin/env python3
"""Fail-closed organization repository taxonomy checker (Python standard library)."""
import argparse
import copy
import datetime
import json
import re
from pathlib import Path

MAX_JSON_BYTES = 2_000_000

def read_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        fail(f"{path}: expected regular file, not symlink or special file")
    if path.stat().st_size > MAX_JSON_BYTES:
        fail(f"{path}: oversized registry/schema")
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                fail(f"{path}: duplicate JSON property {key!r}")
            result[key] = value
        return result
    def reject_nonfinite(value):
        fail(f"{path}: non-finite numeric literal {value}")
    return json.loads(path.read_text(encoding="utf-8"),
                      object_pairs_hook=unique_pairs,
                      parse_constant=reject_nonfinite)


class PolicyError(ValueError):
    pass


def fail(message):
    raise PolicyError(message)


def schema_check(value, shape, schema, path="$"):
    """Validate the strict subset of JSON Schema used by this repository's schema."""
    if "$ref" in shape:
        ref = shape["$ref"]
        if not ref.startswith("#/$defs/"):
            fail(f"{path}: unsupported schema reference")
        return schema_check(value, schema["$defs"][ref.split("/")[-1]], schema, path)
    typ = shape.get("type")
    types = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool}
    if typ in types and (not isinstance(value, types[typ]) or
                         (typ == "integer" and isinstance(value, bool))):
        fail(f"{path}: expected {typ}")
    if "const" in shape and (type(value) is not type(shape["const"]) or value != shape["const"]):
        fail(f"{path}: wrong constant")
    if "enum" in shape and value not in shape["enum"]:
        fail(f"{path}: value outside enum")
    if "pattern" in shape and (not isinstance(value, str) or
                               re.fullmatch(shape["pattern"], value) is None):
        fail(f"{path}: pattern mismatch")
    if typ == "object":
        for key in shape.get("required", []):
            if key not in value:
                fail(f"{path}.{key}: missing required property")
        if shape.get("additionalProperties") is False:
            for key in value:
                if key not in shape.get("properties", {}):
                    fail(f"{path}.{key}: unexpected property")
        for key, prop in shape.get("properties", {}).items():
            if key in value:
                schema_check(value[key], prop, schema, f"{path}.{key}")
    if typ == "array":
        for i, item in enumerate(value):
            schema_check(item, shape["items"], schema, f"{path}[{i}]")


def check(registry, schema, owner, public_repo, *, _fixture_review_authorization=False):
    schema_check(registry, schema, schema)
    if registry["organization"] != owner:
        fail("organization does not match workflow repository owner")
    visibility = registry["inventory_visibility"]
    if public_repo and visibility != "public-only":
        fail("public .github must have public-only inventory")
    if not public_repo and visibility != "organization-private":
        fail("private .github requires organization-private inventory")
    rows = registry["repositories"]
    if not rows:
        fail("registry has no repositories")
    names = set()
    admin_vpcs = {}
    for row in rows:
        name = row["repository"]
        if name.casefold() == (owner + "/.github").casefold() and name != owner + "/.github":
            fail(f"{name}: governance repository name must use exact canonical spelling")
        if name.casefold() in names:
            fail(f"{name}: duplicate repository (case-insensitive)")
        names.add(name.casefold())
        if not name.startswith(owner + "/"):
            fail(f"{name}: foreign organization")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name):
            fail(f"{name}: malformed repository")
        if visibility == "public-only" and row["visibility"] != "public":
            fail(f"{name}: nonpublic entry in public registry")
        role = row["trust_domain"]
        scope = row["database_scope"]
        cat = row["category"]
        state = row["review_status"]
        release = row["release_unit"]
        targets = row["deployment_targets"]
        evidence = row.get("review_evidence")
        if name == owner + "/.github":
            if cat != "governance" or role != "shared-library" or scope != "none":
                fail(f"{name}: organization policy repository misclassified")
        if name.casefold().endswith("-admin-mcp-server.rs"):
            expected = "admin-mcp"
        elif name.casefold().endswith("-admin-api-server.rs"):
            expected = "admin-api"
        elif name.casefold().endswith("-admin-web-server.rs"):
            expected = "admin-web"
        else:
            expected = None
        if expected and (role != expected or scope != "admin" or cat != "app"):
            fail(f"{name}: admin service must have {expected} domain and admin DB scope")
        if role in {"admin-web", "admin-api", "admin-mcp"}:
            if scope != "admin" or cat != "app":
                fail(f"{name}: invalid administrative role or database scope")
        if scope == "admin" and role not in {"admin-web", "admin-api", "admin-mcp", "data-admin"}:
            fail(f"{name}: only administrative trust domains may access admin database")
        if role == "data-admin" and scope != "admin":
            fail(f"{name}: data-admin requires admin database scope")
        if role == "data-app" and scope not in {"app", "none", "unverified"}:
            fail(f"{name}: invalid data-app database scope")
        if row["source_authority"] == "pinned-integration-superproject" and cat != "integration":
            fail(f"{name}: integration source authority on non-integration repository")
        if state == "inferred-needs-review":
            if evidence is not None:
                fail(f"{name}: provisional record cannot assert review evidence")
            if targets["status"] != "unverified" or release["status"] != "unverified":
                fail(f"{name}: provisional record cannot approve a deployment or release")
        elif state == "reviewed":
            # Syntax-only JSON evidence is forgeable. Production has no authoritative
            # approved-attestation source yet, so it must reject all promotions.
            # The fixture-only override is used solely to exercise downstream VPC
            # isolation checks in the trusted verifier's own self-tests.
            if not _fixture_review_authorization:
                fail(f"{name}: reviewed claims require independently verified approval; admission unavailable")
            if not isinstance(evidence, dict) or not all(evidence.get(k) for k in ("url", "reviewed_by", "reviewed_at")):
                fail(f"{name}: reviewed classification requires provenance")
            if not re.fullmatch(r"https://github\.com/[^/]+/[^/]+/(?:pull/\d+|commit/[0-9a-f]{40})", evidence["url"]):
                fail(f"{name}: malformed GitHub review evidence")
            if not evidence["url"].startswith(f"https://github.com/{owner}/.github/pull/"):
                fail(f"{name}: reviewed classification requires organization governance PR provenance")
            try:
                reviewed_time = datetime.datetime.fromisoformat(evidence["reviewed_at"].replace("Z", "+00:00"))
                if reviewed_time.tzinfo is None or reviewed_time.utcoffset() is None:
                    fail(f"{name}: review timestamp needs timezone")
                if reviewed_time > datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5):
                    fail(f"{name}: review timestamp is in future")
            except (ValueError, AttributeError):
                fail(f"{name}: invalid review timestamp")
        if targets["status"] == "unverified" and any(targets[k] for k in ("environments", "vpcs", "cloud_identities")):
            fail(f"{name}: unverified targets must not assert deployed resources")
        if release["status"] == "unverified" and release["identifiers"]:
            fail(f"{name}: unverified release identifiers are forbidden")
        if targets["status"] == "reviewed":
            for field in ("environments", "vpcs", "cloud_identities"):
                values = targets[field]
                if any(not value.strip() or value != value.strip() for value in values):
                    fail(f"{name}: invalid reviewed {field} value")
                if len(values) != len(set(values)):
                    fail(f"{name}: duplicated reviewed {field} value")
            if state != "reviewed":
                fail(f"{name}: reviewed targets require reviewed classification")
            if release["kind"] in {"service", "application"} or role.startswith("admin-"):
                if any(not targets[k] for k in ("environments", "vpcs", "cloud_identities")):
                    fail(f"{name}: reviewed deployable requires environment, VPC and identity")
            if role.startswith("admin-"):
                admin_vpcs.setdefault(role, set()).update(targets["vpcs"])
        if release["status"] == "reviewed":
            if state != "reviewed":
                fail(f"{name}: reviewed release requires reviewed classification")
            if release["kind"] not in {"none", "integration"} and not release["identifiers"]:
                fail(f"{name}: reviewed release requires artifact identifiers")
            if any(not value.strip() or value != value.strip() for value in release["identifiers"]):
                fail(f"{name}: reviewed release identifiers cannot be blank or padded")
            if len(release["identifiers"]) != len(set(release["identifiers"])):
                fail(f"{name}: duplicated reviewed release identifier")
    if (owner + "/.github").casefold() not in names:
        fail("the organization .github repository is missing")
    roles = sorted(admin_vpcs)
    for i, left in enumerate(roles):
        for right in roles[i + 1:]:
            if admin_vpcs[left] & admin_vpcs[right]:
                fail(f"reviewed admin roles {left} and {right} share a VPC")
    return len(rows)


def self_test():
    owner = "test-org"
    schema = read_json("repository-taxonomy.schema.json")
    schema["properties"]["organization"] = {"const": owner}
    row = {
        "repository": "test-org/.github", "visibility": "public",
        "category": "governance", "trust_domain": "shared-library",
        "source_authority": "canonical",
        "release_unit": {"kind": "none", "identifiers": [], "status": "unverified"},
        "deployment_targets": {"environments": [], "vpcs": [], "cloud_identities": [], "status": "unverified"},
        "database_scope": "none", "lifecycle": "unverified",
        "review_status": "inferred-needs-review"
    }
    doc = {
        "version": 1, "organization": owner, "inventory_visibility": "public-only",
        "governance": {"approval_required": True, "unverified_fields_grant_no_access": True,
                       "separate_admin_deployments": True, "public_registry_excludes_private_repositories": True},
        "repositories": [row]
    }
    scenarios = []
    def expect(label, mutate, rejected=True):
        instance = copy.deepcopy(doc)
        mutate(instance)
        caught = False
        try:
            check(instance, schema, owner, True, _fixture_review_authorization=True)
        except (PolicyError, KeyError, TypeError, ValueError):
            caught = True
        if caught != rejected:
            fail(f"self-test {label}: {'unexpected rejection' if caught else 'unexpected acceptance'}")
        scenarios.append(label)
    expect("base-pass", lambda x: None, False)
    expect("missing-category", lambda x: x["repositories"][0].pop("category"))
    expect("duplicate-repo", lambda x: x["repositories"].append(copy.deepcopy(row)))
    expect("foreign-owner", lambda x: x["repositories"][0].update(repository="other/.github"))
    expect("public-private-leak", lambda x: x["repositories"][0].update(visibility="private"))
    expect("admin-role-mismatch", lambda x: x["repositories"][0].update(repository="test-org/demo-admin-mcp-server.rs"))
    expect("public-to-admin-db", lambda x: x["repositories"][0].update(trust_domain="public-app", database_scope="admin"))
    expect("unreviewed-vpc", lambda x: x["repositories"][0]["deployment_targets"].update(vpcs=["vpc-unknown"]))
    expect("unreviewed-release", lambda x: x["repositories"][0]["release_unit"].update(identifiers=["image:latest"]))
    expect("self-attested-reviewed", lambda x: x["repositories"][0].update(review_status="reviewed"))
    expect("bad-authority", lambda x: x["repositories"][0].update(source_authority="pinned-integration-superproject"))
    expect("unknown-category", lambda x: x["repositories"][0].update(category="typo"))
    expect("bad-schema", lambda x: x.update(version=2))
    expect("boolean-version-is-not-integer-one", lambda x: x.update(version=True))
    expect("numeric-governance-bool-must-not-pass", lambda x: x["governance"].update(approval_required=1))
    expect("numeric-privacy-bool-must-not-pass", lambda x: x["governance"].update(public_registry_excludes_private_repositories=1))
    expect("governance-repository-case-alias", lambda x: x["repositories"][0].update(repository="test-org/.GITHUB"))
    expect("governance-repository-owner-case-alias", lambda x: x["repositories"][0].update(repository="TEST-ORG/.github"))
    expect("governance-repository-extra-trailing-dot", lambda x: x["repositories"][0].update(repository="test-org/.github."))
    expect("version-as-string", lambda x: x.update(version="1"))
    expect("governance-false", lambda x: x["governance"].update(approval_required=False))
    expect("missing-github", lambda x: x["repositories"][0].update(repository="test-org/other"))

    expect("case-folded-duplicate", lambda x: x["repositories"].append(
        dict(copy.deepcopy(row), repository="TEST-ORG/.GITHUB")))
    expect("shared-library-admin-db", lambda x: x["repositories"][0].update(database_scope="admin"))
    expect("data-admin-needs-admin-db", lambda x: x["repositories"][0].update(
        trust_domain="data-admin", database_scope="none"))
    expect("data-app-cannot-use-admin-db", lambda x: x["repositories"][0].update(
        trust_domain="data-app", database_scope="admin"))

    def approved(repo_name, role, vpc):
        entry = copy.deepcopy(row)
        entry.update(repository=repo_name, category="app", trust_domain=role,
                     database_scope="admin", review_status="reviewed",
                     review_evidence={"url": "https://github.com/test-org/.github/pull/123",
                                      "reviewed_by": "test-reviewer",
                                      "reviewed_at": "2026-01-01T00:00:00Z"})
        entry["release_unit"].update(kind="service", status="reviewed",
                                     identifiers=["sha256:" + "a" * 64])
        entry["deployment_targets"].update(
            status="reviewed", environments=["production"], vpcs=[vpc],
            cloud_identities=["synthetic-role"])
        return entry

    def attach(x, entries):
        x["repositories"].extend(entries)

    expect("reviewed-admin-distinct-vpcs", lambda x: attach(x, [
        approved("test-org/a-admin-api-server.rs", "admin-api", "vpc-a"),
        approved("test-org/a-admin-mcp-server.rs", "admin-mcp", "vpc-b"),
    ]), False)
    expect("reviewed-admin-vpc-overlap", lambda x: attach(x, [
        approved("test-org/a-admin-api-server.rs", "admin-api", "vpc-same"),
        approved("test-org/a-admin-mcp-server.rs", "admin-mcp", "vpc-same"),
    ]))
    expect("multiple-same-role-vpc-overwrite", lambda x: attach(x, [
        approved("test-org/a-admin-api-server.rs", "admin-api", "vpc-shared"),
        approved("test-org/b-admin-api-server.rs", "admin-api", "vpc-second"),
        approved("test-org/a-admin-mcp-server.rs", "admin-mcp", "vpc-shared"),
    ]))
    expect("reviewed-release-empty-identifier", lambda x: (
        attach(x, [approved("test-org/a-admin-api-server.rs", "admin-api", "vpc-a")]),
        x["repositories"][-1]["release_unit"].update(identifiers=[])))
    expect("review-with-foreign-org-pr", lambda x: (
        attach(x, [approved("test-org/a-admin-api-server.rs", "admin-api", "vpc-a")]),
        x["repositories"][-1]["review_evidence"].update(
            url="https://github.com/other/.github/pull/1")))
    expect("review-with-naive-timestamp", lambda x: (
        attach(x, [approved("test-org/a-admin-api-server.rs", "admin-api", "vpc-a")]),
        x["repositories"][-1]["review_evidence"].update(
            reviewed_at="2026-01-01T00:00:00")))
    expect("review-with-future-timestamp", lambda x: (
        attach(x, [approved("test-org/a-admin-api-server.rs", "admin-api", "vpc-a")]),
        x["repositories"][-1]["review_evidence"].update(
            reviewed_at="2999-01-01T00:00:00Z")))
    expect("admin-missing-reviewed-vpc", lambda x: (
        attach(x, [approved("test-org/a-admin-api-server.rs", "admin-api", "vpc-a")]),
        x["repositories"][-1]["deployment_targets"].update(vpcs=[])))

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "registry.json"
        for content, error_text, label in [
            ('{"a":1,"a":2}', "duplicate JSON property", "duplicate-json-properties"),
            ('{"a":NaN}', "non-finite", "non-finite-json"),
        ]:
            p.write_text(content, encoding="utf-8")
            try:
                read_json(p)
            except PolicyError as error:
                if error_text not in str(error):
                    raise
            else:
                fail(f"self-test {label}: unexpectedly accepted")
            scenarios.append(label)

    expect("mixed-case-admin-mcp-name", lambda x: x["repositories"].append(
        dict(copy.deepcopy(row), repository="test-org/A-ADMIN-MCP-SERVER.RS")))
    expect("blank-reviewed-vpc", lambda x: (
        attach(x, [approved("test-org/a-admin-api-server.rs", "admin-api", "vpc-a")]),
        x["repositories"][-1]["deployment_targets"].update(vpcs=["  "])))
    expect("duplicate-reviewed-vpc", lambda x: (
        attach(x, [approved("test-org/a-admin-api-server.rs", "admin-api", "vpc-a")]),
        x["repositories"][-1]["deployment_targets"].update(vpcs=["vpc-a", "vpc-a"])))
    expect("blank-reviewed-cloud-identity", lambda x: (
        attach(x, [approved("test-org/a-admin-api-server.rs", "admin-api", "vpc-a")]),
        x["repositories"][-1]["deployment_targets"].update(cloud_identities=[""])))
    expect("blank-reviewed-release-identifier", lambda x: (
        attach(x, [approved("test-org/a-admin-api-server.rs", "admin-api", "vpc-a")]),
        x["repositories"][-1]["release_unit"].update(identifiers=[" "])))

    forged = copy.deepcopy(doc)
    attach(forged, [approved("test-org/a-admin-api-server.rs", "admin-api", "vpc-a")])
    try:
        check(forged, schema, owner, True)  # production mode, NOT fixture mode
    except PolicyError as error:
        if "independently verified approval" not in str(error):
            raise
    else:
        fail("self-test: production accepted self-attested reviewed record")
    scenarios.append("production-denies-spoofed-review")
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "actual.json"
        target.write_text('{"a": 1}', encoding="utf-8")
        link = Path(tmp) / "link.json"
        link.symlink_to(target)
        try:
            read_json(link)
        except PolicyError as error:
            if "regular file" not in str(error):
                raise
        else:
            fail("self-test: symlinked JSON was accepted")
        scenarios.append("rejects-symlinked-registry")
        too_large = Path(tmp) / "oversized.json"
        too_large.write_bytes(b" " * (MAX_JSON_BYTES + 1))
        try:
            read_json(too_large)
        except PolicyError as error:
            if "oversized" not in str(error):
                raise
        else:
            fail("self-test: oversized JSON was accepted")
        scenarios.append("rejects-oversized-registry")
    print(f"self-tests passed: {len(scenarios)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--org")
    parser.add_argument("--registry", default="repository-taxonomy.json")
    parser.add_argument("--schema", default="repository-taxonomy.schema.json")
    parser.add_argument("--public-repo", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            return
        if not args.org:
            parser.error("--org is required")
        data = read_json(args.registry)
        schema = read_json(args.schema)
        count = check(data, schema, args.org, args.public_repo)
        print(f"repository taxonomy: PASS ({count} repositories; organization {args.org})")
    except (PolicyError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"repository taxonomy: FAIL: {exc}\n")


if __name__ == "__main__":
    main()
