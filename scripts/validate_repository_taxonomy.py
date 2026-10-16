#!/usr/bin/env python3
"""Fail-closed organization repository taxonomy checker (Python standard library)."""
import argparse
import copy
import datetime
import json
import re
from pathlib import Path


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
    if "const" in shape and value != shape["const"]:
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


def check(registry, schema, owner, public_repo):
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
        if name in names:
            fail(f"{name}: duplicate repository")
        names.add(name)
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
        if name.endswith("-admin-mcp-server.rs"):
            expected = "admin-mcp"
        elif name.endswith("-admin-api-server.rs"):
            expected = "admin-api"
        elif name.endswith("-admin-web-server.rs"):
            expected = "admin-web"
        else:
            expected = None
        if expected and (role != expected or scope != "admin" or cat != "app"):
            fail(f"{name}: admin service must have {expected} domain and admin DB scope")
        if role in {"admin-web", "admin-api", "admin-mcp"}:
            if scope != "admin" or cat != "app":
                fail(f"{name}: invalid administrative role or database scope")
        if role == "public-app" and scope == "admin":
            fail(f"{name}: public application cannot access admin database")
        if row["source_authority"] == "pinned-integration-superproject" and cat != "integration":
            fail(f"{name}: integration source authority on non-integration repository")
        if state == "inferred-needs-review":
            if evidence is not None:
                fail(f"{name}: provisional record cannot assert review evidence")
            if targets["status"] != "unverified" or release["status"] != "unverified":
                fail(f"{name}: provisional record cannot approve a deployment or release")
        elif state == "reviewed":
            if not isinstance(evidence, dict) or not all(evidence.get(k) for k in ("url", "reviewed_by", "reviewed_at")):
                fail(f"{name}: reviewed classification requires provenance")
            if not re.fullmatch(r"https://github\.com/[^/]+/[^/]+/(?:pull/\d+|commit/[0-9a-f]{40})", evidence["url"]):
                fail(f"{name}: review evidence must reference GitHub PR or commit")
            try:
                datetime.datetime.fromisoformat(evidence["reviewed_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                fail(f"{name}: invalid review timestamp")
        if targets["status"] == "unverified" and any(targets[k] for k in ("environments", "vpcs", "cloud_identities")):
            fail(f"{name}: unverified targets must not assert deployed resources")
        if release["status"] == "unverified" and release["identifiers"]:
            fail(f"{name}: unverified release identifiers are forbidden")
        if targets["status"] == "reviewed":
            if state != "reviewed":
                fail(f"{name}: reviewed targets require reviewed classification")
            if release["kind"] in {"service", "application"} or role.startswith("admin-"):
                if any(not targets[k] for k in ("environments", "vpcs", "cloud_identities")):
                    fail(f"{name}: reviewed deployable requires environment, VPC and identity")
            if role.startswith("admin-"):
                admin_vpcs[role] = set(targets["vpcs"])
        if release["status"] == "reviewed" and state != "reviewed":
            fail(f"{name}: reviewed release requires reviewed classification")
    if owner + "/.github" not in names:
        fail("the organization .github repository is missing")
    roles = sorted(admin_vpcs)
    for i, left in enumerate(roles):
        for right in roles[i + 1:]:
            if admin_vpcs[left] & admin_vpcs[right]:
                fail(f"reviewed admin roles {left} and {right} share a VPC")
    return len(rows)


def self_test():
    owner = "test-org"
    schema = json.loads(Path("repository-taxonomy.schema.json").read_text())
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
            check(instance, schema, owner, True)
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
    expect("missing-github", lambda x: x["repositories"][0].update(repository="test-org/other"))
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
        data = json.loads(Path(args.registry).read_text(encoding="utf-8"))
        schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
        count = check(data, schema, args.org, args.public_repo)
        print(f"repository taxonomy: PASS ({count} repositories; organization {args.org})")
    except (PolicyError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"repository taxonomy: FAIL: {exc}\n")


if __name__ == "__main__":
    main()
