"""Closed-set domain values are compared through their StrEnum, never as bare string literals."""

import ast
from enum import StrEnum
from pathlib import Path

from interns.domain.labels import EstimationOutcome, RefinementOutcome, TypeLabel
from interns.domain.verdict import ReviewState
from interns.steps.flag_failure import Noun
from interns.steps.run_summary import Phase, Round

ROOT = Path(__file__).resolve().parents[2]
SOURCES = [*sorted((ROOT / "interns/src/interns").rglob("*.py")), ROOT / "gh_issues_mcp/server.py"]
ENUMS: list[type[StrEnum]] = [ReviewState, RefinementOutcome, EstimationOutcome, TypeLabel, Phase, Round, Noun]
VALUES = {member.value for enum in ENUMS for member in enum}


def literal_comparisons(source: str) -> list[str]:
    hits = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            operands += [e for o in operands if isinstance(o, ast.Tuple | ast.List | ast.Set) for e in o.elts]
            hits += [o.value for o in operands if isinstance(o, ast.Constant) and o.value in VALUES]
        elif isinstance(node, ast.MatchValue) and isinstance(node.value, ast.Constant) and node.value.value in VALUES:
            hits.append(node.value.value)
    return hits


def test_detects_a_compared_literal():
    assert literal_comparisons('x = r.state == "CHANGES_REQUESTED"') == ["CHANGES_REQUESTED"]
    assert literal_comparisons('match s:\n    case "APPROVED":\n        pass') == ["APPROVED"]
    assert literal_comparisons("x = r.state == ReviewState.APPROVED") == []


def test_no_closed_set_value_is_compared_as_a_bare_literal():
    offenders = {
        str(path.relative_to(ROOT)): hits for path in SOURCES if (hits := literal_comparisons(path.read_text()))
    }
    assert not offenders, f"compare through the StrEnum member instead: {offenders}"
