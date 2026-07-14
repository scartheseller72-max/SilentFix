from __future__ import annotations
import typing as t
import inspect
import hypothesis
from hypothesis import strategies as st, assume, settings, Phase
from silentfix.core.types import PropertySet, FailureSet
from silentfix.config import get_config


def run_property_tests(func: t.Callable, props: PropertySet) -> FailureSet:
    results = FailureSet()
    sig = _get_signature(func)
    if not sig:
        return results

    param_names = list(sig.parameters.keys())
    strategy = _build_strategy(sig)
    cfg = get_config()

    for post in props.postconditions:
        if post.predicate_py is None:
            continue
        failures = _test_one_property(func, param_names, strategy, post, props, cfg)
        for args, kwargs in failures:
            results.add_failure(args, kwargs, post.description)

    for ex_args, ex_kwargs, _ in props.examples:
        try:
            out = func(*ex_args, **ex_kwargs)
            inp_dict = {p: a for p, a in zip(param_names, ex_args)}
            failed = False
            for post in props.postconditions:
                if post.predicate_py and not post.predicate_py(inp_dict, out):
                    failed = True
                    break
            if not failed:
                results.add_pass(ex_args, ex_kwargs)
        except Exception:
            pass

    return results


def _get_signature(func: t.Callable) -> inspect.Signature | None:
    try:
        return inspect.signature(func)
    except (ValueError, TypeError):
        return None


def _build_strategy(sig: inspect.Signature) -> st.SearchStrategy:
    strategies = []
    for name, param in sig.parameters.items():
        hint = param.annotation
        hint_str = str(hint) if hint is not inspect.Parameter.empty else ""
        default = param.default

        if "list" in hint_str or "List" in hint_str or "Sequence" in hint_str:
            if "int" in hint_str:
                s = st.lists(st.integers(min_value=-100, max_value=100), max_size=20)
            elif "float" in hint_str:
                s = st.lists(st.floats(min_value=-100, max_value=100, allow_nan=False), max_size=20)
            elif "str" in hint_str:
                s = st.lists(st.text(max_size=10), max_size=20)
            else:
                s = st.lists(st.integers(min_value=-100, max_value=100), max_size=20)
        elif "tuple" in hint_str or "Tuple" in hint_str:
            s = st.tuples(st.integers(min_value=-100, max_value=100))
        elif "dict" in hint_str or "Dict" in hint_str or "Mapping" in hint_str:
            s = st.dictionaries(st.text(max_size=10), st.integers(min_value=-100, max_value=100), max_size=10)
        elif "bool" in hint_str:
            s = st.booleans()
        elif "str" in hint_str:
            s = st.text(max_size=50)
        elif "int" in hint_str:
            s = st.integers(min_value=-1000, max_value=1000)
        elif "float" in hint_str:
            s = st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False)
        else:
            if default is not inspect.Parameter.empty:
                s = st.just(default)
            else:
                s = st.integers(min_value=-1000, max_value=1000)
        strategies.append(s)

    if len(strategies) == 1:
        return strategies[0]
    return st.tuples(*strategies)


def _test_one_property(
    func: t.Callable, param_names: list[str],
    strategy: st.SearchStrategy, post: "Property",
    props: PropertySet, cfg,
) -> list[tuple[tuple, dict]]:
    failures: list[tuple[tuple, dict]] = []
    n_param = len(param_names)
    seen: set[str] = set()

    for i in range(cfg.hypothesis_max_examples):
        try:
            args = strategy.example()
        except Exception:
            continue

        key = str(args)
        if key in seen:
            continue
        seen.add(key)

        if n_param == 1:
            inp_dict = {param_names[0]: args}
            call_args = (args,)
        else:
            inp_dict = {p: a for p, a in zip(param_names, args)}
            call_args = args

        skip = False
        for pre in props.preconditions:
            if pre.predicate_py and not pre.predicate_py(inp_dict):
                skip = True
                break
        if skip:
            continue

        try:
            out = func(*call_args)
            if post.predicate_py and not post.predicate_py(inp_dict, out):
                failures.append((call_args, {}))
        except Exception:
            pass

    return failures[:50]
