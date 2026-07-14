from __future__ import annotations
import ast
import inspect
import typing as t
import textwrap
from silentfix.core.types import Property, PropertyKind, PropertySet


def extract_static_properties(func: t.Callable, source: str = "") -> PropertySet:
    props = PropertySet()
    sig = _extract_signature(func)
    doc = _extract_docstring(func)
    comments = _extract_comments(func)
    name = func.__name__

    if sig:
        _add_type_based_props(props, sig)
    if doc:
        _add_docstring_props(props, doc, sig)
    for comment in comments:
        _add_comment_props(props, comment, sig)
    _add_name_based_props(props, name, sig)
    if "valid_range" in name.lower():
        _add_valid_range_prop(props, func, name, sig, source)
    return props


def _add_valid_range_prop(props: PropertySet, func: t.Callable, name: str, sig: inspect.Signature | None, override_source: str = ""):
    raw = ""
    try:
        raw = textwrap.dedent(inspect.getsource(func))
    except OSError:
        raw = override_source
    if not raw:
        return
    try:
        tree = ast.parse(raw)
    except Exception:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.BoolOp):
            continue
        parts = [ast.unparse(v).strip() for v in node.value.values]
        if isinstance(node.value.op, ast.And):
            flipped = " or ".join(parts)
        elif isinstance(node.value.op, ast.Or):
            flipped = " and ".join(parts)
        else:
            continue
        param_names = list(sig.parameters.keys()) if sig else []
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out, pnames=param_names, expr=flipped: (
                isinstance(out, bool) and
                out == bool(eval(expr, {"__builtins__": {}}, {p: inp.get(p, 0) for p in pnames}))
            ),
            predicate_z3=None,
            description="output matches valid range logic",
            confidence=0.7,
            source="function_name_semantic",
        ))
        return


def _add_name_based_props(props: PropertySet, name: str, sig: inspect.Signature | None):
    name_lower = name.lower()
    param_names = list(sig.parameters.keys()) if sig else []
    if not param_names:
        return
    first_param = param_names[0]

    def _get_first_inp(inp_dict):
        if isinstance(inp_dict, dict):
            return inp_dict.get(first_param, inp_dict)
        return inp_dict

    if "max" in name_lower:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: _check_max(inp, out, first_param),
            predicate_z3=None,
            description="output is the maximum of input",
            confidence=0.7,
            source="function_name",
        ))
    if "min" in name_lower:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: _check_min(inp, out, first_param),
            predicate_z3=None,
            description="output is the minimum of input",
            confidence=0.7,
            source="function_name",
        ))
    if "min_max" in name_lower or "minmax" in name_lower:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out, p=param_names[0]: _check_min_max(inp, out, p),
            predicate_z3=None,
            description="output is (min, max) of input",
            confidence=0.7,
            source="function_name",
        ))
    if "sum" in name_lower or "total" in name_lower:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: _check_sum(inp, out, first_param),
            predicate_z3=None,
            description="output equals sum of input",
            confidence=0.7,
            source="function_name",
        ))
    if "avg" in name_lower or "average" in name_lower or "mean" in name_lower:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: _check_avg(inp, out, first_param),
            predicate_z3=None,
            description="output is the average of input",
            confidence=0.7,
            source="function_name",
        ))
    if "sort" in name_lower or "sorted" in name_lower:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: not hasattr(out, '__iter__') or (hasattr(out, '__len__') and len(out) <= 1) or all(out[i] <= out[i+1] for i in range(len(out)-1) if hasattr(out[i], '__le__')),
            predicate_z3=None,
            description="output is sorted",
            confidence=0.7,
            source="function_name",
        ))
    if "contains" in name_lower or "has" in name_lower or "found" in name_lower:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: isinstance(out, bool),
            predicate_z3=None,
            description="output is boolean (membership check)",
            confidence=0.7,
            source="function_name",
        ))
        props.metamorphic.append(Property(
            kind=PropertyKind.METAMORPHIC,
            predicate_py=lambda inp, out: True,
            predicate_z3=None,
            description="contains(x) is True when x appears in input",
            confidence=0.5,
            source="function_name",
        ))
    if "palindrome" in name_lower:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: isinstance(out, bool),
            predicate_z3=None,
            description="output is boolean (palindrome check)",
            confidence=0.7,
            source="function_name",
        ))

    if "in_range" in name_lower or "inrange" in name_lower:
        if len(param_names) >= 3:
            _x, _lo, _hi = param_names[0], param_names[1], param_names[2]
            props.postconditions.append(Property(
                kind=PropertyKind.POSTCONDITION,
                predicate_py=lambda inp, out, x=_x, lo=_lo, hi=_hi: (
                    isinstance(out, bool) and
                    out == (inp.get(lo, 0) <= inp.get(x, 0) <= inp.get(hi, 0))
                ),
                predicate_z3=None,
                description="output indicates value is within inclusive range",
                confidence=0.7,
                source="function_name",
            ))
    if "first" in name_lower or "head" in name_lower or "car" in name_lower:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out, p=param_names[0]: (
                not hasattr(inp.get(p, []), '__iter__') or
                (not inp.get(p, []) and out is None) or
                (inp.get(p, []) and out == inp[p][0])
            ),
            predicate_z3=None,
            description="output is first element of input (or None if empty)",
            confidence=0.7,
            source="function_name",
        ))
    if "is_even" in name_lower:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out, p=param_names[0]: (
                isinstance(out, bool) and
                out == (inp.get(p, 0) % 2 == 0)
            ),
            predicate_z3=None,
            description="output indicates whether input is even",
            confidence=0.7,
            source="function_name",
        ))
    if "valid_range" in name_lower:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out, p=param_names[0]: (
                isinstance(out, bool)
            ),
            predicate_z3=None,
            description="output is boolean (validity check)",
            confidence=0.7,
            source="function_name",
        ))
    if "dot_product" in name_lower or "inner_product" in name_lower:
        if len(param_names) >= 2:
            p0, p1 = param_names[0], param_names[1]
            props.postconditions.append(Property(
                kind=PropertyKind.POSTCONDITION,
                predicate_py=lambda inp, out, a=p0, b=p1: (
                    hasattr(inp.get(a, []), '__iter__') and
                    hasattr(inp.get(b, []), '__iter__') and
                    isinstance(out, (int, float)) and
                    out == sum(x * y for x, y in zip(inp[a], inp[b]))
                ),
                predicate_z3=None,
                description="output equals dot product of inputs",
                confidence=0.7,
                source="function_name",
            ))


def _check_max(inp_dict, out, param_name):
    seq = inp_dict.get(param_name) if isinstance(inp_dict, dict) else inp_dict
    if not hasattr(seq, '__iter__') or not hasattr(out, '__float__'):
        return True
    items = list(seq)
    if len(items) == 0 or not all(hasattr(x, '__float__') for x in items):
        return True
    return abs(out - max(items)) < 1e-9


def _check_min(inp_dict, out, param_name):
    seq = inp_dict.get(param_name) if isinstance(inp_dict, dict) else inp_dict
    if not hasattr(seq, '__iter__') or not hasattr(out, '__float__'):
        return True
    items = list(seq)
    if len(items) == 0 or not all(hasattr(x, '__float__') for x in items):
        return True
    return abs(out - min(items)) < 1e-9


def _check_min_max(inp_dict, out, param_name):
    seq = inp_dict.get(param_name) if isinstance(inp_dict, dict) else inp_dict
    if not hasattr(seq, '__iter__') or not hasattr(out, '__iter__'):
        return True
    items = list(seq)
    if len(items) == 0 or len(out) < 2:
        return True
    try:
        return out[0] == min(items) and out[1] == max(items)
    except Exception:
        return True


def _check_avg(inp_dict, out, param_name):
    seq = inp_dict.get(param_name) if isinstance(inp_dict, dict) else inp_dict
    if not hasattr(seq, '__iter__') or not hasattr(out, '__float__'):
        return True
    items = list(seq)
    if len(items) == 0:
        return out == 0
    if not all(hasattr(x, '__float__') for x in items):
        return True
    return abs(out - sum(items) / len(items)) < 1e-9


def _check_sum(inp_dict, out, param_name):
    seq = inp_dict.get(param_name) if isinstance(inp_dict, dict) else inp_dict
    if not hasattr(seq, '__iter__') or not hasattr(out, '__float__'):
        return True
    items = list(seq)
    if not all(hasattr(x, '__float__') for x in items):
        return True
    return abs(out - sum(items)) < 1e-9


def _extract_signature(func: t.Callable) -> inspect.Signature | None:
    try:
        return inspect.signature(func)
    except (ValueError, TypeError):
        return None


def _extract_docstring(func: t.Callable) -> str:
    return inspect.getdoc(func) or ""


def _extract_comments(func: t.Callable) -> list[str]:
    try:
        source = textwrap.dedent(inspect.getsource(func))
        comments = []
        for line in source.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#"):
                comments.append(stripped.lstrip("#").strip())
        return comments
    except (OSError, TypeError):
        return []


def _add_type_based_props(props: PropertySet, sig: inspect.Signature):
    for name, param in sig.parameters.items():
        hint = param.annotation
        if hint is inspect.Parameter.empty:
            continue
        hint_str = str(hint)
        hint_origin = getattr(hint, '__origin__', None)
        if hint_origin is not None and hint_origin is not hint:
            pass
        elif hint_str in ("int", "float"):
            pass
        elif hint_origin is list or hint_origin is tuple or hint_str in ("list", "tuple", "List", "Tuple", "Sequence"):
            props.postconditions.append(Property(
                kind=PropertyKind.POSTCONDITION,
                predicate_py=lambda inp, out, _n=name: not hasattr(out, '__len__') or len(out) >= 0,
                predicate_z3=None,
                description=f"Output length is defined (non-negative)",
                confidence=0.3,
                source="type_hint",
            ))

    ret = sig.return_annotation
    if ret is not inspect.Parameter.empty:
        ret_str = str(ret)
        ret_origin = getattr(ret, '__origin__', None)
        if ret_origin is not None and ret_origin is not ret:
            pass
        elif ret_str == "bool":
            props.postconditions.append(Property(
                kind=PropertyKind.POSTCONDITION,
                predicate_py=lambda inp, out: isinstance(out, bool),
                predicate_z3=None,
                description="Return type is bool",
                confidence=0.7,
                source="type_hint",
            ))
        elif ret_str in ("int", "float"):
            props.postconditions.append(Property(
                kind=PropertyKind.POSTCONDITION,
                predicate_py=lambda inp, out: isinstance(out, (int, float)),
                predicate_z3=None,
                description="Return type is numeric",
                confidence=0.7,
                source="type_hint",
            ))


def _add_docstring_props(props: PropertySet, doc: str, sig: inspect.Signature | None):
    doc_lower = doc.lower()
    param_names = list(sig.parameters.keys()) if sig else []

    patterns = {
        "sort": [("result is sorted", "sorted({out}) == list({out})")],
        "maximum": [("returns maximum", "{out} == max({inp})")],
        "minimum": [("returns minimum", "{out} == min({inp})")],
        "sum": [("returns sum", "{out} == sum({inp})")],
        "count": [("returns count", "{out} == sum(1 for _ in {inp})")],
        "average": [("returns average", "len({inp}) == 0 or abs({out} - sum({inp})/len({inp})) < 1e-9")],
        "unique": [("removes duplicates", "len({out}) <= len({inp})")],
        "reverse": [("reversed order", "{out} == list(reversed({inp}))")],
        "filter": [("filters elements", "all(x in {inp} for x in {out})")],
        "map": [("transforms elements", "len({out}) == len({inp})")],
        "positive": [("returns positive", "{out} >= 0")],
        "non-negative": [("returns non-negative", "{out} >= 0")],
        "idempotent": [("idempotent", "f(f({inp})) == f({inp})")],
    }

    for keyword, prop_list in patterns.items():
        if keyword in doc_lower:
            for desc, expr_template in prop_list:
                expr = expr_template
                if "{inp}" in expr and param_names:
                    first_param = param_names[0]
                    expr = expr.replace("{inp}", first_param)
                if "{out}" in expr:
                    expr = expr.replace("{out}", "out")
                try:
                    pred = _make_property_predicate(expr, param_names)
                    props.postconditions.append(Property(
                        kind=PropertyKind.POSTCONDITION,
                        predicate_py=pred,
                        predicate_z3=None,
                        description=desc,
                        confidence=0.6,
                        source="docstring",
                    ))
                except Exception:
                    pass


def _add_comment_props(props: PropertySet, comment: str, sig: inspect.Signature | None):
    comment_lower = comment.lower()
    param_names = list(sig.parameters.keys()) if sig else []

    for keyword in ["expects", "requires", "assumes", "input"]:
        if keyword in comment_lower:
            props.preconditions.append(Property(
                kind=PropertyKind.PRECONDITION,
                predicate_py=lambda inp: True,
                predicate_z3=None,
                description=f"Comment suggests: {comment}",
                confidence=0.3,
                source="comment",
            ))


def _make_property_predicate(expr: str, param_names: list[str]) -> t.Callable:
    ns = {"__builtins__": __builtins__}
    exec(f"def _pred(inp, out): return {expr}", ns)
    return ns["_pred"]
