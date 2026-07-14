from __future__ import annotations
import typing as t
from collections import defaultdict
from silentfix.core.types import ExecutionTrace, SuspiciousLocation


def compute_sbfl(
    pass_traces: list[ExecutionTrace],
    fail_traces: list[ExecutionTrace],
) -> dict[int, dict[str, float]]:
    line_stats: dict[int, dict] = defaultdict(lambda: {"ef": 0, "ep": 0, "nf": 0, "np": 0})

    for trace in fail_traces:
        covered = set(e.line_no for e in trace.events)
        for line in covered:
            line_stats[line]["ef"] += 1
        uncovered_lines = _all_lines - covered if _all_lines else set()
        for line in uncovered_lines:
            if line in line_stats:
                line_stats[line]["nf"] += 1

    for trace in pass_traces:
        covered = set(e.line_no for e in trace.events)
        for line in covered:
            line_stats[line]["ep"] += 1
        uncovered_lines = _all_lines - covered if _all_lines else set()
        for line in uncovered_lines:
            if line in line_stats:
                line_stats[line]["np"] += 1

    scores: dict[int, dict[str, float]] = {}
    n_fail = len(fail_traces)
    n_pass = len(pass_traces)

    for line, stats in line_stats.items():
        ef, ep, nf, np = stats["ef"], stats["ep"], stats["nf"], stats["np"]

        tarantula = _safe_tarantula(ef, ep, nf, np)
        ochiai = _safe_ochiai(ef, ep, nf, np)
        dstar = _safe_dstar(ef, ep, nf, np, n_fail, n_pass)

        scores[line] = {
            "tarantula": tarantula,
            "ochiai": ochiai,
            "dstar": dstar,
            "combined": (tarantula + ochiai + dstar) / 3.0,
        }

    all_combined = [s["combined"] for s in scores.values()]
    max_c = max(all_combined) if all_combined else 1.0
    if max_c > 0:
        for line in scores:
            scores[line]["combined"] /= max_c

    return scores


_all_lines: set[int] = set()

def set_all_lines(lines: set[int]):
    global _all_lines
    _all_lines = lines


def _safe_tarantula(ef: int, ep: int, nf: int, np: int) -> float:
    passed = ep + np
    failed = ef + nf
    if failed == 0 and passed == 0:
        return 0.0
    failed_ratio = ef / failed if failed > 0 else 0
    passed_ratio = ep / passed if passed > 0 else 0
    total = failed_ratio + passed_ratio
    return failed_ratio / total if total > 0 else 0.0


def _safe_ochiai(ef: int, ep: int, nf: int, np: int) -> float:
    denom = ((ef + ep) * (ef + nf)) ** 0.5
    return ef / denom if denom > 0 else 0.0


def _safe_dstar(ef: int, ep: int, nf: int, np: int, n_fail: int, n_pass: int) -> float:
    if n_fail == 0:
        return 0.0
    denom = ep + nf
    if denom == 0:
        return 1.0 if ef > 0 else 0.0
    raw = (ef ** 2) / denom
    max_raw = (n_fail ** 2) / 1.0 if n_pass == 0 and n_fail > 0 else (n_fail ** 2) / max(1, n_fail)
    return min(1.0, raw / max_raw) if max_raw > 0 else 0.0
