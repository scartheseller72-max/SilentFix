from __future__ import annotations
import typing as t
import inspect
from silentfix.core.types import Property, PropertyKind, PropertySet


def extract_type_properties(func: t.Callable) -> PropertySet:
    props = PropertySet()
    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError):
        return props

    ret = sig.return_annotation
    if ret is inspect.Parameter.empty:
        return props

    ret_str = str(ret)
    ret_origin = getattr(ret, '__origin__', None)
    is_generic = ret_origin is not None and ret_origin is not ret

    if is_generic:
        if ret_origin in (list, tuple, set, frozenset):
            props.postconditions.append(Property(
                kind=PropertyKind.POSTCONDITION,
                predicate_py=lambda inp, out: hasattr(out, '__iter__'),
                predicate_z3=None,
                description="Return type is iterable",
                confidence=0.7,
                source="type_inference",
            ))
        return props

    if ret_str in ("list", "tuple", "List", "Tuple", "Sequence", "set", "dict"):
        for name, param in sig.parameters.items():
            param_str = str(param.annotation)
            param_origin = getattr(param.annotation, '__origin__', None)
            param_is_generic = param_origin is not None and param_origin is not param.annotation
            if not param_is_generic and ("list" in param_str or "List" in param_str or "Sequence" in param_str):
                props.postconditions.append(Property(
                    kind=PropertyKind.POSTCONDITION,
                    predicate_py=lambda inp, out, _n=name: (
                        not hasattr(out, '__len__') or
                        not hasattr(inp.get(_n) if isinstance(inp, dict) else _n, '__len__') or
                        len(out) <= len(inp.get(_n) if isinstance(inp, dict) else _n) * 2
                    ),
                    predicate_z3=None,
                    description=f"Output length bounded by 2x input length ({name})",
                    confidence=0.4,
                    source="type_inference",
                ))

        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: not hasattr(out, '__len__') or len(out) >= 0,
            predicate_z3=None,
            description="Output length is non-negative",
            confidence=0.5,
            source="type_inference",
        ))

    if ret_str == "bool":
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: isinstance(out, bool),
            predicate_z3=None,
            description="Return type is bool",
            confidence=0.8,
            source="type_inference",
        ))

    if ret_str == "int":
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: isinstance(out, int),
            predicate_z3=None,
            description="Return type is int",
            confidence=0.8,
            source="type_inference",
        ))

    if ret_str == "float":
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: isinstance(out, (int, float)),
            predicate_z3=None,
            description="Return type is float",
            confidence=0.8,
            source="type_inference",
        ))

    if "Optional" in ret_str or "None" in ret_str:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: out is None or True,
            predicate_z3=None,
            description="Return may be None",
            confidence=0.5,
            source="type_inference",
        ))

    return props
