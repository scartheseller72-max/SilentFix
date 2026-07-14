from __future__ import annotations
import typing as t
import ast
import inspect
import z3
from silentfix.core.types import PropertySet, FailureSet
from silentfix.config import get_config


def symbolic_detection(func: t.Callable, props: PropertySet) -> FailureSet:
    results = FailureSet()
    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError):
        return results

    param_names = list(sig.parameters.keys())
    if not param_names:
        return results

    only_numeric = all(
        str(p.annotation) in ("int", "float", "<class 'int'>", "<class 'float'>", "int | float")
        or p.annotation is inspect.Parameter.empty
        for p in sig.parameters.values()
    )
    if not only_numeric:
        return results

    cfg = get_config()
    solver = z3.Solver()
    solver.set("timeout", cfg.symbolic_timeout_s * 1000)

    z3_vars = {name: z3.Int(name) for name in param_names}

    for post in props.postconditions:
        if post.predicate_z3 is None:
            continue
        solver.push()
        solver.add(post.predicate_z3(z3_vars))
        if solver.check() == z3.sat:
            model = solver.model()
            concrete_args = tuple(model[v].as_long() for v in z3_vars.values())
            try:
                out = func(*concrete_args)
                inp_dict = {p: a for p, a in zip(param_names, concrete_args)}
                if post.predicate_py and not post.predicate_py(inp_dict, out):
                    results.add_failure(concrete_args, {}, post.description)
            except Exception:
                pass
        solver.pop()

    return results
