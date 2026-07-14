from __future__ import annotations
import typing as t
import json
import inspect
import textwrap
from silentfix.core.types import Property, PropertyKind, PropertySet
from silentfix.llm.client import LLMClient
from silentfix.llm.prompts import PROPERTY_EXTRACTION_SYSTEM
from silentfix.core.utils import make_predicate


def extract_llm_properties(func: t.Callable, module_code: str = "") -> PropertySet:
    props = PropertySet()
    source = _get_func_source(func)
    sig = _get_func_sig(func)
    doc = inspect.getdoc(func) or ""
    param_names = list(sig.parameters.keys()) if sig else []

    prompt = _build_extraction_prompt(func.__name__, source, sig, doc, module_code)
    client = LLMClient()
    response = client.complete(prompt, system=PROPERTY_EXTRACTION_SYSTEM, max_tokens=4096, json_mode=True)

    try:
        data = json.loads(response)
    except (json.JSONDecodeError, TypeError):
        return props

    if "postconditions" in data:
        for pc in data["postconditions"]:
            pred = make_predicate(
                pc.get("predicate_expr", "True"),
                param_names + (["out"] if "out" in pc.get("predicate_expr", "") else []),
            )
            props.postconditions.append(Property(
                kind=PropertyKind.POSTCONDITION,
                predicate_py=pred,
                predicate_z3=None,
                description=pc.get("description", "LLM-derived postcondition"),
                confidence=0.7,
                source="llm",
            ))

    if "preconditions" in data:
        for pc in data["preconditions"]:
            pred = make_predicate(pc.get("predicate_expr", "True"), param_names)
            props.preconditions.append(Property(
                kind=PropertyKind.PRECONDITION,
                predicate_py=pred,
                predicate_z3=None,
                description=pc.get("description", "LLM-derived precondition"),
                confidence=0.6,
                source="llm",
            ))

    if "examples" in data:
        for ex in data["examples"]:
            args = tuple(ex.get("args", []))
            kwargs = ex.get("kwargs", {})
            expected = ex.get("expected")
            if args or kwargs:
                props.examples.append((args, kwargs, expected))

    return props


def _get_func_source(func: t.Callable) -> str:
    try:
        return textwrap.dedent(inspect.getsource(func))
    except (OSError, TypeError):
        return "def stub(): pass"


def _get_func_sig(func: t.Callable) -> inspect.Signature | None:
    try:
        return inspect.signature(func)
    except (ValueError, TypeError):
        return None


def _build_extraction_prompt(
    name: str, source: str, sig: inspect.Signature | None,
    doc: str, module_code: str,
) -> str:
    sig_str = str(sig) if sig else "unknown"
    lines = [
        f"Function: {name}{sig_str}",
        f"Docstring: {doc}" if doc else "",
        f"Source:\n```python\n{source}\n```",
    ]
    if module_code:
        lines.append(f"Module context:\n```python\n{module_code[:2000]}\n```")
    lines.append("\nExtract all likely preconditions, postconditions, loop invariants, and example I/O pairs.")
    return "\n".join(lines)
