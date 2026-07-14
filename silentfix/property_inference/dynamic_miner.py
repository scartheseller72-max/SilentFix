from __future__ import annotations
import typing as t
import inspect
import random
import string
from collections import Counter
from silentfix.core.types import Property, PropertyKind, PropertySet
from silentfix.config import get_config


def mine_dynamic_properties(func: t.Callable) -> PropertySet:
    props = PropertySet()
    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError):
        return props

    param_names = list(sig.parameters.keys())
    if not param_names:
        return props

    cfg = get_config()
    samples = cfg.dynamic_miner_samples
    results: list[tuple[t.Any, t.Any]] = []

    for _ in range(samples):
        inp = _generate_random_input(sig)
        try:
            out = func(*inp)
            results.append((inp, out))
        except Exception:
            continue

    if not results:
        return props

    _mine_numeric_properties(props, results, param_names, func)
    _mine_collection_properties(props, results, param_names, func)
    _mine_idempotence(props, results, func)

    return props


def _generate_random_input(sig: inspect.Signature) -> tuple:
    args = []
    for name, param in sig.parameters.items():
        hint = param.annotation
        hint_str = str(hint) if hint is not inspect.Parameter.empty else ""
        default = param.default

        if "int" in hint_str:
            val = random.randint(-100, 100)
        elif "float" in hint_str:
            val = random.uniform(-100, 100)
        elif "str" in hint_str:
            length = random.randint(0, 20)
            val = "".join(random.choices(string.ascii_letters, k=length))
        elif "list" in hint_str or "List" in hint_str or "Sequence" in hint_str:
            length = random.randint(0, 10)
            if "int" in hint_str:
                val = [random.randint(-50, 50) for _ in range(length)]
            elif "float" in hint_str:
                val = [random.uniform(-50, 50) for _ in range(length)]
            elif "str" in hint_str:
                val = ["".join(random.choices(string.ascii_letters, k=5)) for _ in range(length)]
            else:
                val = list(range(length))
        elif "bool" in hint_str:
            val = random.choice([True, False])
        elif "dict" in hint_str or "Dict" in hint_str or "Mapping" in hint_str:
            n = random.randint(0, 5)
            val = {f"k{i}": random.randint(-10, 10) for i in range(n)}
        elif "tuple" in hint_str or "Tuple" in hint_str:
            length = random.randint(0, 5)
            val = tuple(range(length))
        else:
            if default is not inspect.Parameter.empty:
                val = default
            elif "int" in hint_str or "float" in hint_str:
                val = 0
            else:
                val = None
        args.append(val)
    return tuple(args)


def _mine_numeric_properties(
    props: PropertySet, results: list[tuple],
    param_names: list[str], func: t.Callable,
):
    if not results:
        return
    first_param = param_names[0] if param_names else "inp"
    outputs = [r[1] for r in results]

    numeric_outputs = [o for o in outputs if isinstance(o, (int, float))]
    if not numeric_outputs:
        return

    min_o, max_o = min(numeric_outputs), max(numeric_outputs)
    all_nonneg = all(o >= 0 for o in numeric_outputs)
    all_nonpos = all(o <= 0 for o in numeric_outputs)
    all_in_range = all(-1000 <= o <= 1000 for o in numeric_outputs)
    zero_count = sum(1 for o in numeric_outputs if o == 0)

    _mine_max_relationship(props, results, param_names)
    _mine_min_relationship(props, results, param_names)
    _mine_sum_relationship(props, results, param_names)

    if all_nonneg:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: not isinstance(out, (int, float)) or out >= 0,
            predicate_z3=None,
            description="output is non-negative",
            confidence=min(0.9, zero_count / len(numeric_outputs) + 0.3),
            source="dynamic_mining",
        ))

    if all_nonpos and len(numeric_outputs) >= 5:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: not isinstance(out, (int, float)) or out <= 0,
            predicate_z3=None,
            description="output is non-positive",
            confidence=0.5,
            source="dynamic_mining",
        ))

    if all_in_range and len(numeric_outputs) >= 10:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: not isinstance(out, (int, float)) or -1000 <= out <= 1000,
            predicate_z3=None,
            description="output is bounded in [-1000, 1000]",
            confidence=0.4,
            source="dynamic_mining",
        ))

    if len(numeric_outputs) >= 5:
        for inp, out in results[:10]:
            first_input = inp[0] if inp else None
            if isinstance(first_input, (int, float)) and isinstance(out, (int, float)):
                if out == first_input:
                    props.postconditions.append(Property(
                        kind=PropertyKind.POSTCONDITION,
                        predicate_py=lambda inp, out, _i=0: (
                            not isinstance(inp, (int, float, list, tuple)) or
                            not isinstance(out, (int, float)) or
                            out == (inp if isinstance(inp, (int, float)) else inp[0] if inp else None)
                        ),
                        predicate_z3=None,
                        description="output equals input",
                        confidence=0.3,
                        source="dynamic_mining",
                    ))
                    break


def _mine_collection_properties(
    props: PropertySet, results: list[tuple],
    param_names: list[str], func: t.Callable,
):
    outputs_with_len = [(r[0], r[1]) for r in results if hasattr(r[1], '__len__')]
    if not outputs_with_len or len(outputs_with_len) < 5:
        return

    lengths = [len(o) for _, o in outputs_with_len]
    if max(lengths) == 0:
        return

    non_empty_ratio = sum(1 for l in lengths if l > 0) / len(lengths)
    if non_empty_ratio > 0.9:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: hasattr(out, '__len__') and len(out) > 0,
            predicate_z3=None,
            description="output is non-empty",
            confidence=min(0.8, non_empty_ratio),
            source="dynamic_mining",
        ))

    inputs_with_len = [r[0] for r in outputs_with_len if r[0] and hasattr(r[0][0] if r[0] else None, '__len__')]
    if inputs_with_len:
        in_lens = [len(i[0]) for i in inputs_with_len]
        out_lens = [len(o) for _, o in outputs_with_len]
        matches = sum(1 for il, ol in zip(in_lens, out_lens) if il == ol)
        if matches / len(in_lens) > 0.8:
            first_param = param_names[0] if param_names else "inp"
            props.postconditions.append(Property(
                kind=PropertyKind.POSTCONDITION,
                predicate_py=lambda inp, out, _n=first_param: (
                    not hasattr(_get_input_val(inp, _n), '__len__') or
                    not hasattr(out, '__len__') or
                    len(_get_input_val(inp, _n)) == len(out)
                ),
                predicate_z3=None,
                description="output length equals input length",
                confidence=0.6,
                source="dynamic_mining",
            ))


def _mine_idempotence(
    props: PropertySet, results: list[tuple], func: t.Callable,
):
    for inp, out in results[:20]:
        try:
            out2 = func(*(inp if isinstance(inp, tuple) else (inp,)))
            if out == out2:
                props.postconditions.append(Property(
                    kind=PropertyKind.POSTCONDITION,
                    predicate_py=lambda inp, out: True,
                    predicate_z3=None,
                    description="idempotent: f(f(x)) == f(x)",
                    confidence=0.3,
                    source="dynamic_mining",
                ))
                return
        except Exception:
            continue


def _mine_max_relationship(props, results, param_names):
    if not param_names:
        return
    first_param = param_names[0]
    max_matches = 0
    total = 0
    for inp, out in results:
        if not isinstance(out, (int, float)):
            continue
        first_val = inp[0] if inp else None
        if isinstance(first_val, (list, tuple)) and len(first_val) > 0:
            total += 1
            if all(isinstance(x, (int, float)) for x in first_val):
                if abs(out - max(first_val)) < 1e-9:
                    max_matches += 1

    if total >= 5 and max_matches / total > 0.6:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: (
                not hasattr(_get_input_val(inp, first_param), '__iter__')
                or not hasattr(out, '__float__')
                or out == max(_get_input_val(inp, first_param))
            ),
            predicate_z3=None,
            description="output equals maximum of input",
            confidence=min(0.8, max_matches / total),
            source="dynamic_mining",
        ))


def _mine_min_relationship(props, results, param_names):
    if not param_names:
        return
    first_param = param_names[0]
    min_matches = 0
    total = 0
    for inp, out in results:
        if not isinstance(out, (int, float)):
            continue
        first_val = inp[0] if inp else None
        if isinstance(first_val, (list, tuple)) and len(first_val) > 0:
            total += 1
            if all(isinstance(x, (int, float)) for x in first_val):
                if abs(out - min(first_val)) < 1e-9:
                    min_matches += 1

    if total >= 5 and min_matches / total > 0.6:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: (
                not hasattr(_get_input_val(inp, first_param), '__iter__')
                or not hasattr(out, '__float__')
                or out == min(_get_input_val(inp, first_param))
            ),
            predicate_z3=None,
            description="output equals minimum of input",
            confidence=min(0.8, min_matches / total),
            source="dynamic_mining",
        ))


def _mine_sum_relationship(props, results, param_names):
    if not param_names:
        return
    first_param = param_names[0]
    sum_matches = 0
    total = 0
    for inp, out in results:
        if not isinstance(out, (int, float)):
            continue
        first_val = inp[0] if inp else None
        if isinstance(first_val, (list, tuple)):
            total += 1
            if all(isinstance(x, (int, float)) for x in first_val):
                if abs(out - sum(first_val)) < 1e-9:
                    sum_matches += 1

    if total >= 5 and sum_matches / total > 0.6:
        props.postconditions.append(Property(
            kind=PropertyKind.POSTCONDITION,
            predicate_py=lambda inp, out: (
                not hasattr(_get_input_val(inp, first_param), '__iter__')
                or not hasattr(out, '__float__')
                or abs(out - sum(_get_input_val(inp, first_param))) < 1e-9
            ),
            predicate_z3=None,
            description="output equals sum of input",
            confidence=min(0.8, sum_matches / total),
            source="dynamic_mining",
        ))


def _get_input_val(inp, name):
    if isinstance(inp, dict):
        return inp.get(name)
    if isinstance(inp, (list, tuple)) and inp:
        return inp[0]
    return inp
