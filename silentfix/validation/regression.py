from __future__ import annotations
import typing as t
import textwrap
from silentfix.core.types import Patch, PropertySet
from silentfix.detection.hypothesis_tester import run_property_tests


def validate_patch(
    func: t.Callable,
    patched_source: str,
    props: PropertySet,
    failing_inputs: list[tuple],
    passing_inputs: list[tuple],
) -> dict:
    result = {
        "passed": False,
        "regressions": [],
        "remaining_failures": [],
        "new_failures": [],
        "verified": False,
        "score": 0.0,
    }

    ns: dict = {}
    try:
        clean_source = textwrap.dedent(patched_source)
        exec(compile(clean_source, "<validate>", "exec"), ns)
        patched_func = None
        for n, v in ns.items():
            if callable(v) and not n.startswith("_"):
                patched_func = v
                break
    except Exception as e:
        result["error"] = f"Failed to compile: {e}"
        return result

    if patched_func is None:
        result["error"] = "No callable found in patched source"
        return result

    regressions = 0
    for args, kwargs in passing_inputs:
        try:
            orig_out = func(*args, **kwargs)
            new_out = patched_func(*args, **kwargs)
            if str(type(orig_out)) != str(type(new_out)):
                regressions += 1
                result["regressions"].append({"args": args, "reason": "type_mismatch"})
            elif isinstance(orig_out, (int, float)) and isinstance(new_out, (int, float)):
                if abs(orig_out - new_out) > 1e-9:
                    regressions += 1
                    result["regressions"].append({"args": args, "original": orig_out, "new": new_out})
            elif str(orig_out) != str(new_out):
                regressions += 1
                result["regressions"].append({"args": args, "original": str(orig_out), "new": str(new_out)})
        except Exception as e:
            regressions += 1
            result["regressions"].append({"args": args, "error": str(e)})

    fixes_original = 0
    for args, kwargs in failing_inputs:
        try:
            new_out = patched_func(*args, **kwargs)

            inp_dict = {}
            import inspect
            try:
                sig = inspect.signature(func)
                param_names = list(sig.parameters.keys())
                inp_dict = {p: a for p, a in zip(param_names, args)}
            except Exception:
                inp_dict = {"a": args}

            all_violated = all(
                post.predicate_py and post.predicate_py(inp_dict, new_out)
                for post in props.postconditions if post.predicate_py
            )
            if all_violated:
                fixes_original += 1
            else:
                if len(result["new_failures"]) < 5:
                    result["new_failures"].append((args, str(new_out)))
        except Exception:
            if len(result["new_failures"]) < 5:
                result["new_failures"].append((args, "exception"))

    remaining_count = len(failing_inputs) - fixes_original

    result["remaining_failures_count"] = remaining_count
    result["regression_count"] = regressions
    result["fixes_count"] = fixes_original

    score = 1.0
    if regressions > 0:
        score -= 0.3 * min(1.0, regressions / max(len(passing_inputs), 1))
    if remaining_count > 0:
        score -= 0.5 * min(1.0, remaining_count / max(len(failing_inputs), 1))

    score = max(0.0, score)
    result["score"] = score
    result["passed"] = score >= 0.3 and regressions == 0 and fixes_original > 0

    return result
