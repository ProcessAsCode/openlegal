"""Minimal DMN decision-table evaluator.

Supported hit policies: FIRST, UNIQUE, ANY.
Supported cell expressions:
  - "-"                                 wildcard
  - "<X" | "<=X" | ">X" | ">=X" | "==X" | "!=X"
  - "[A..B]" / "(A..B)" / "[A..B)" / "(A..B]"   numeric ranges
  - "A, B, C"                           membership
  - bare literal                        equality with type coercion
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DMNTable:
    id: str
    name: str
    hit_policy: str
    inputs: list[str]
    outputs: list[str]
    rules: list[list[Any]]

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "DMNTable":
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            hit_policy=data.get("hit_policy", "UNIQUE").upper(),
            inputs=data["inputs"],
            outputs=data["outputs"],
            rules=data["rules"],
        )

    @classmethod
    def from_path(cls, path: str | Path) -> "DMNTable":
        return cls.from_json(json.loads(Path(path).read_text(encoding="utf-8")))


_OP_RE = re.compile(r"^\s*(<=|>=|<|>|==|!=)\s*(.+)$")
_RANGE_RE = re.compile(r"^\s*([\[\(])\s*(.+?)\s*\.\.\s*(.+?)\s*([\]\)])\s*$")


def _coerce(v: Any) -> Any:
    if not isinstance(v, str):
        return v
    s = v.strip()
    if s.lower() in {"true", "false"}:
        return s.lower() == "true"
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return s


def _match_cell(cell: Any, value: Any) -> bool:
    if cell is None or cell == "-" or cell == "":
        return True
    if not isinstance(cell, str):
        return cell == value

    expr = cell.strip()

    m = _RANGE_RE.match(expr)
    if m:
        lo_b, lo, hi, hi_b = m.groups()
        lo_v, hi_v = _coerce(lo), _coerce(hi)
        v = _coerce(value)
        if not isinstance(v, (int, float)):
            return False
        lo_ok = (v > lo_v) if lo_b == "(" else (v >= lo_v)
        hi_ok = (v < hi_v) if hi_b == ")" else (v <= hi_v)
        return lo_ok and hi_ok

    m = _OP_RE.match(expr)
    if m:
        op, rhs = m.groups()
        v = _coerce(value)
        r = _coerce(rhs)
        try:
            if op == "<":   return v < r
            if op == "<=":  return v <= r
            if op == ">":   return v > r
            if op == ">=":  return v >= r
            if op == "==":  return v == r
            if op == "!=":  return v != r
        except TypeError:
            return False

    if "," in expr:
        options = [_coerce(p.strip()) for p in expr.split(",")]
        return _coerce(value) in options

    return _coerce(expr) == _coerce(value)


class DMNEvaluationError(ValueError):
    """Raised when a table evaluation violates its hit policy."""


@dataclass(frozen=True)
class DMNResult:
    decision_id: str
    output: dict[str, Any]
    matched_rules: list[int]
    hit_policy: str


def evaluate(table: DMNTable, inputs: dict[str, Any]) -> DMNResult:
    n_in = len(table.inputs)
    n_out = len(table.outputs)

    matches: list[tuple[int, list[Any]]] = []
    for idx, rule in enumerate(table.rules, start=1):
        if len(rule) != n_in + n_out:
            raise DMNEvaluationError(
                f"{table.id}: rule {idx} has {len(rule)} cells, expected {n_in + n_out}"
            )
        if all(
            _match_cell(rule[i], inputs.get(name))
            for i, name in enumerate(table.inputs)
        ):
            matches.append((idx, rule[n_in:]))

    if not matches:
        if table.hit_policy in {"FIRST", "ANY"}:
            return DMNResult(table.id, {}, [], table.hit_policy)
        raise DMNEvaluationError(
            f"{table.id}: no rule matched (hit_policy={table.hit_policy}); inputs={inputs}"
        )

    if table.hit_policy == "FIRST":
        idx, outputs = matches[0]
        return DMNResult(
            table.id,
            {name: outputs[i] for i, name in enumerate(table.outputs)},
            [idx], "FIRST",
        )

    if table.hit_policy == "UNIQUE":
        if len(matches) > 1:
            raise DMNEvaluationError(
                f"{table.id}: hit_policy=UNIQUE but {len(matches)} rules matched: "
                f"{[m[0] for m in matches]}"
            )
        idx, outputs = matches[0]
        return DMNResult(
            table.id,
            {name: outputs[i] for i, name in enumerate(table.outputs)},
            [idx], "UNIQUE",
        )

    if table.hit_policy == "ANY":
        first_out = matches[0][1]
        for idx, out in matches[1:]:
            if out != first_out:
                raise DMNEvaluationError(
                    f"{table.id}: hit_policy=ANY but rules disagree"
                )
        return DMNResult(
            table.id,
            {name: first_out[i] for i, name in enumerate(table.outputs)},
            [m[0] for m in matches], "ANY",
        )

    raise DMNEvaluationError(f"{table.id}: unsupported hit_policy {table.hit_policy!r}")


__all__ = ["DMNTable", "DMNResult", "DMNEvaluationError", "evaluate"]
