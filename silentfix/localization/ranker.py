from __future__ import annotations
import typing as t
import ast
import inspect
from silentfix.core.types import ExecutionTrace, SuspiciousLocation
from silentfix.localization.sbfl import compute_sbfl, set_all_lines
from silentfix.localization.divergence import compute_divergence
from silentfix.config import get_config


def rank_suspicious_locations(
    func: t.Callable,
    pass_traces: list[ExecutionTrace],
    fail_traces: list[ExecutionTrace],
    source_override: str = "",
) -> list[SuspiciousLocation]:
    cfg = get_config()

    try:
        source = source_override or inspect.getsource(func)
        tree = ast.parse(source)
        func_ast = tree.body[0] if tree.body else None
        all_lines = set()
        if func_ast:
            for node in ast.walk(func_ast):
                if hasattr(node, 'lineno'):
                    all_lines.add(node.lineno)
        set_all_lines(all_lines)
    except Exception:
        pass

    sbfl_scores = compute_sbfl(pass_traces, fail_traces)
    divergence_scores = compute_divergence(pass_traces, fail_traces)

    all_line_nos = set(sbfl_scores.keys()) | set(divergence_scores.keys())

    suspicious: list[SuspiciousLocation] = []
    for line_no in all_line_nos:
        sbfl = sbfl_scores.get(line_no, {}).get("combined", 0)
        divergence = divergence_scores.get(line_no, 0)

        total = (
            cfg.sbfl_weight * sbfl +
            cfg.divergence_weight * divergence
        )

        suspicious.append(SuspiciousLocation(
            line_no=line_no,
            node_type="",
            sbfl_score=sbfl,
            divergence_score=divergence,
            total_score=total,
            context="",
        ))

    if not suspicious and pass_traces and fail_traces:
        for loc in fail_traces[0].events:
            line_no = loc.line_no
            if line_no not in {l.line_no for l in suspicious}:
                suspicious.append(SuspiciousLocation(
                    line_no=line_no, node_type="", total_score=0.5,
                ))
                if len(suspicious) >= cfg.top_k_suspicious:
                    break

    if not suspicious:
        try:
            source = source_override or inspect.getsource(func)
            for i, line in enumerate(source.split("\n"), 1):
                stripped = line.strip()
                if stripped and not stripped.startswith("def ") and not stripped.startswith("#") and not stripped.startswith("@"):
                    suspicious.append(SuspiciousLocation(
                        line_no=i, node_type="line", total_score=0.5 - (i * 0.01),
                    ))
                    if len(suspicious) >= cfg.top_k_suspicious:
                        break
        except Exception:
            pass

    suspicious.sort(key=lambda x: x.total_score, reverse=True)
    return suspicious[:cfg.top_k_suspicious]
