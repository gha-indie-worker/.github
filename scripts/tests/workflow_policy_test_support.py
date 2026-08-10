from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from workflow_policy import Finding, lint_model, load_policy, parse_workflow  # noqa: E402

CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
UPLOAD_SHA = "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"


def safe_workflow() -> str:
    return f"""name: Safe policy fixture

on:
  pull_request:
  push:

permissions:
  contents: read

concurrency:
  group: safe-${{{{ github.workflow }}}}-${{{{ github.ref }}}}
  cancel-in-progress: true

jobs:
  verify:
    permissions:
      contents: read
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    steps:
      - name: Checkout
        uses: actions/checkout@{CHECKOUT_SHA}
        with:
          persist-credentials: false
      - name: Run tests
        run: echo safe
      - name: Upload evidence
        uses: actions/upload-artifact@{UPLOAD_SHA}
        with:
          name: policy-evidence
          path: report.json
"""


class WorkflowPolicyTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_policy(ROOT / "workflow-policy.json")

    def lint(self, text: str, path: str = ".github/workflows/test.yml") -> list[Finding]:
        return lint_model(parse_workflow(text, path), self.policy)

    @staticmethod
    def rule_ids(findings: list[Finding]) -> set[str]:
        return {finding.rule_id for finding in findings}
