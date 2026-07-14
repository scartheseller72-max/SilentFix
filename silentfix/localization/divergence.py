from __future__ import annotations
import typing as t
from collections import defaultdict
import math
from silentfix.core.types import ExecutionTrace


def compute_divergence(
    pass_traces: list[ExecutionTrace],
    fail_traces: list[ExecutionTrace],
) -> dict[int, float]:
    line_var_values: dict[int, dict[str, dict[str, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: {"pass": [], "fail": []})
    )

    for trace in pass_traces:
        for event in trace.events:
            for var in event.variables:
                if isinstance(var.value, (int, float)):
                    line_var_values[event.line_no][var.name]["pass"].append(float(var.value))

    for trace in fail_traces:
        for event in trace.events:
            for var in event.variables:
                if isinstance(var.value, (int, float)):
                    line_var_values[event.line_no][var.name]["fail"].append(float(var.value))

    divergence_scores: dict[int, float] = {}
    for line_no, var_dict in line_var_values.items():
        max_div = 0.0
        for var_name, dists in var_dict.items():
            pass_vals = dists["pass"]
            fail_vals = dists["fail"]
            if len(pass_vals) < 3 or len(fail_vals) < 3:
                continue
            div = _kl_divergence(pass_vals, fail_vals)
            max_div = max(max_div, div)
        if max_div > 0:
            divergence_scores[line_no] = min(1.0, max_div)

    if divergence_scores:
        max_score = max(divergence_scores.values())
        if max_score > 0:
            for line in divergence_scores:
                divergence_scores[line] /= max_score

    return divergence_scores


def _kl_divergence(p: list[float], q: list[float]) -> float:
    bins = 10
    all_vals = p + q
    if not all_vals:
        return 0.0
    mn, mx = min(all_vals), max(all_vals)
    if mx == mn:
        return 0.0
    bin_width = (mx - mn) / bins
    if bin_width == 0:
        return 0.0

    p_hist = [0.0] * bins
    q_hist = [0.0] * bins

    for v in p:
        idx = min(int((v - mn) / bin_width), bins - 1)
        p_hist[idx] += 1.0
    for v in q:
        idx = min(int((v - mn) / bin_width), bins - 1)
        q_hist[idx] += 1.0

    p_sum = sum(p_hist)
    q_sum = sum(q_hist)
    if p_sum == 0 or q_sum == 0:
        return 0.0

    p_hist = [c / p_sum for c in p_hist]
    q_hist = [c / q_sum for c in q_hist]

    eps = 1e-10
    kl = sum(
        p * math.log((p + eps) / (q + eps))
        for p, q in zip(p_hist, q_hist)
    )
    return kl
