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

    if "list" in ret_str or "List" in ret_str or "Sequence" in ret_str or "tuple" in ret_str or "Tuple" in ret_str:
        for name, param in sig.parameters.items():
            param_str = str(param.annotation)
            if "list" in param_str or "List" in param_str or "Sequence" in param_str:
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

    if "dict" in ret_str or "Dict" in ret_str or "Mapping" in ret_str:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: isinstance(out, dict),
            predicate_z3=None,
            description="Return type is dict",
            confidence=0.6,
            source="type_inference",
        ))

    if "bool" in ret_str:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: isinstance(out, bool),
            predicate_z3=None,
            description="Return type is bool",
            confidence=0.8,
            source="type_inference",
        ))

    if "int" in ret_str:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: isinstance(out, int),
            predicate_z3=None,
            description="Return type is int",
            confidence=0.8,
            source="type_inference",
        ))

    if "float" in ret_str:
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
