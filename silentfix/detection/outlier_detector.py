from __future__ import annotations
import typing as t
import inspect
import random
from collections import Counter
from silentfix.core.types import PropertySet, FailureSet
from silentfix.config import get_config


def detect_outliers(func: t.Callable, props: PropertySet) -> FailureSet:
    results = FailureSet()
    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError):
        return results

    param_names = list(sig.parameters.keys())
    if not param_names:
        return results

    cfg = get_config()
    n_samples = 300
    outputs: list[t.Any] = []
    inputs: list[tuple] = []

    for _ in range(n_samples):
        inp = _quick_random_input(sig)
        try:
            out = func(*inp)
            inputs.append(inp)
            outputs.append(out)
        except Exception:
            continue

    if len(outputs) < 10:
        return results

    numeric_outputs = [(i, o) for i, o in zip(inputs, outputs) if isinstance(o, (int, float))]
    if len(numeric_outputs) < 10:
        return results

    vals = [o for _, o in numeric_outputs]
    mean = sum(vals) / len(vals)
    variance = sum((v - mean) ** 2 for v in vals) / len(vals)
    std = variance ** 0.5 if variance > 0 else 1.0

    outlier_count = 0
    for inp, val in numeric_outputs:
        z_score = abs(val - mean) / std if std > 0 else 0
        if z_score > 3.0:
            outlier_count += 1
            if outlier_count <= 5:
                results.add_failure(inp, {}, "outlier_detection")

    str_outputs = [(i, o) for i, o in zip(inputs, outputs) if isinstance(o, str)]
    if len(str_outputs) >= 10:
        lengths = [len(o) for _, o in str_outputs]
        mean_len = sum(lengths) / len(lengths)
        len_std = (sum((l - mean_len) ** 2 for l in lengths) / len(lengths)) ** 0.5 or 1.0
        for inp, val in str_outputs:
            if abs(len(val) - mean_len) > 3 * len_std:
                results.add_failure(inp, {}, "outlier_detection")

    return results


def _quick_random_input(sig: inspect.Signature) -> tuple:
    args = []
    for name, param in sig.parameters.items():
        hint = param.annotation
        hint_str = str(hint) if hint is not inspect.Parameter.empty else ""
        if "int" in hint_str:
            args.append(random.randint(-1000, 1000))
        elif "float" in hint_str:
            args.append(random.uniform(-1000, 1000))
        elif "list" in hint_str or "List" in hint_str:
            args.append([random.randint(-50, 50) for _ in range(random.randint(0, 15))])
        elif "str" in hint_str:
            import string
            args.append("".join(random.choices(string.ascii_letters, k=random.randint(0, 20))))
        elif "bool" in hint_str:
            args.append(random.choice([True, False]))
        else:
            args.append(0)
    return tuple(args)
