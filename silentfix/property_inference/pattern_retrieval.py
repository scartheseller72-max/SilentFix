from __future__ import annotations
import typing as t
from silentfix.core.types import Property, PropertyKind, PropertySet

COMMON_PATTERNS: dict[str, list[dict]] = {
    "sort": [
        {"kind": "post", "desc": "result is sorted ascending", "expr": "sorted(out) == list(out)"},
        {"kind": "post", "desc": "result has same length as input", "expr": "len(out) == len(inp)"},
        {"kind": "post", "desc": "result contains same elements", "expr": "sorted(out) == sorted(inp)"},
    ],
    "max": [
        {"kind": "post", "desc": "result is the maximum of input", "expr": "out == max(inp)"},
    ],
    "min": [
        {"kind": "post", "desc": "result is the minimum of input", "expr": "out == min(inp)"},
    ],
    "sum": [
        {"kind": "post", "desc": "result equals sum of input", "expr": "out == sum(inp)"},
    ],
    "average": [
        {"kind": "post", "desc": "result equals average of input", "expr": "len(inp) == 0 or abs(out - sum(inp)/len(inp)) < 1e-9"},
    ],
    "reverse": [
        {"kind": "post", "desc": "result is reversed input", "expr": "out == list(reversed(inp))"},
    ],
    "unique": [
        {"kind": "post", "desc": "result has no duplicates", "expr": "len(set(out)) == len(out)"},
    ],
    "filter": [
        {"kind": "post", "desc": "result preserves original order", "expr": "all(out[i] <= out[i+1] for i in range(len(out)-1)) if sorted out else True"},
    ],
}


def retrieve_pattern_properties(name: str, source: str) -> PropertySet:
    props = PropertySet()
    name_lower = name.lower()
    source_lower = source.lower()

    for pattern_name, pattern_props in COMMON_PATTERNS.items():
        if pattern_name in name_lower or pattern_name in source_lower:
            for p in pattern_props:
                pred = _make_simple_pred(p["expr"])
                prop = Property(
                    kind=PropertyKind.POSTCONDITION,
                    predicate_py=pred,
                    predicate_z3=None,
                    description=p["desc"],
                    confidence=0.5,
                    source=f"pattern_{pattern_name}",
                )
                props.postconditions.append(prop)

    return props


def _make_simple_pred(expr: str) -> t.Callable:
    import textwrap
    ns = {"__builtins__": __builtins__}
    exec(f"def _pred(inp, out): return {expr}", ns)
    return ns["_pred"]
