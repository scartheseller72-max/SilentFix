from __future__ import annotations
import typing as t
import ast
import z3
from silentfix.core.types import SuspiciousLocation, ExecutionTrace, Patch


def synthesize_from_constraints(
    source: str,
    suspicious: list[SuspiciousLocation],
    pass_traces: list[ExecutionTrace],
    fail_traces: list[ExecutionTrace],
) -> list[Patch]:
    patches: list[Patch] = []

    for loc in suspicious:
        pass_snapshots = _collect_values_at_line(pass_traces, loc.line_no)
        fail_snapshots = _collect_values_at_line(fail_traces, loc.line_no)

        if not fail_snapshots:
            continue

        expr = _synthesize_expression(pass_snapshots, fail_snapshots)
        if expr and expr != "out":
            lines = source.split("\n")
            if loc.line_no <= len(lines):
                old_line = lines[loc.line_no - 1]
                indent = old_line[:len(old_line) - len(old_line.lstrip())]
                new_line = _replace_in_line(old_line, expr)
                if new_line and new_line != old_line:
                    lines[loc.line_no - 1] = indent + new_line
                    patched = "\n".join(lines)
                    patches.append(Patch(
                        diff=patched,
                        patched_source=patched,
                        tier=2,
                        score=0.7,
                        description=f"Constraint-based fix at line {loc.line_no}: '{expr}'",
                    ))

    return patches


def _collect_values_at_line(traces: list[ExecutionTrace], line_no: int) -> list[dict[str, t.Any]]:
    snapshots = []
    for trace in traces:
        for event in trace.events:
            if event.line_no == line_no:
                snapshots.append({v.name: v.value for v in event.variables})
    return snapshots


def _synthesize_expression(
    pass_snapshots: list[dict[str, t.Any]],
    fail_snapshots: list[dict[str, t.Any]],
) -> str | None:
    all_vars = set()
    for snap in pass_snapshots + fail_snapshots:
        all_vars.update(k for k, v in snap.items() if isinstance(v, (int, float, bool)))
    all_vars.discard("out")
    all_vars = list(all_vars)

    if not all_vars:
        return None

    candidates = _enumerate_candidates(all_vars)
    for expr in candidates:
        if _check_expr(expr, all_vars, pass_snapshots, fail_snapshots):
            return expr

    return _solve_with_z3(all_vars, pass_snapshots, fail_snapshots)


def _enumerate_candidates(vars: list[str]) -> list[str]:
    candidates = []
    for v in vars:
        candidates.append(v)
        candidates.append(f"{v} + 1")
        candidates.append(f"{v} - 1")
        candidates.append(f"len({v})" if v != "len" else f"{v}")
    for v1 in vars:
        for v2 in vars:
            if v1 < v2:
                candidates.append(f"min({v1}, {v2})")
                candidates.append(f"max({v1}, {v2})")
    for v in vars:
        candidates.append(f"not {v}" if v != "not" else v)
        candidates.append(f"abs({v})" if v != "abs" else v)
    candidates.append("0")
    candidates.append("1")
    candidates.append("True")
    candidates.append("False")
    return list(dict.fromkeys(candidates))


def _check_expr(
    expr: str, vars: list[str],
    pass_snapshots: list[dict],
    fail_snapshots: list[dict],
) -> bool:
    for snap in pass_snapshots:
        if "out" in snap:
            try:
                ns = {v: snap.get(v, 0) for v in vars}
                ns["out"] = snap["out"]
                val = eval(expr, {"__builtins__": {}}, ns)
                if abs(val - snap["out"]) > 1e-9:
                    return False
            except Exception:
                return False

    for snap in fail_snapshots:
        if "out" in snap:
            try:
                ns = {v: snap.get(v, 0) for v in vars}
                ns["out"] = snap["out"]
                result = eval(expr, {"__builtins__": {}}, ns)
                if isinstance(result, bool) or abs(result - snap["out"]) <= 1e-9:
                    return False
            except Exception:
                return False

    return True


def _solve_with_z3(
    vars: list[str],
    pass_snapshots: list[dict],
    fail_snapshots: list[dict],
) -> str | None:
    solver = z3.Solver()
    solver.set("timeout", 5000)

    z3_vars = {v: z3.Int(v) for v in vars}
    z3_c = z3.Int("c")

    template_expressions = [
        lambda c, vs: vs[vars[0]] + c,
        lambda c, vs: vs[vars[0]] - c,
        lambda c, vs: c - vs[vars[0]],
        lambda c, vs: vs[vars[0]] * c,
        lambda c, vs: vs[vars[0]] // c if len(vars) >= 1 else c,
    ]
    if len(vars) >= 2:
        template_expressions.append(lambda c, vs: vs[vars[0]] + vs[vars[1]])
        template_expressions.append(lambda c, vs: vs[vars[0]] - vs[vars[1]])
        template_expressions.append(lambda c, vs: z3.If(vs[vars[0]] > vs[vars[1]], vs[vars[0]], vs[vars[1]]))
        template_expressions.append(lambda c, vs: z3.If(vs[vars[0]] < vs[vars[1]], vs[vars[0]], vs[vars[1]]))

    for template_fn in template_expressions:
        solver.push()
        solver.add(z3_c >= -100, z3_c <= 100)
        constraints_ok = True

        for snap in pass_snapshots:
            if "out" not in snap or not isinstance(snap["out"], (int, float)):
                continue
            try:
                z3_val = template_fn(z3_c, z3_vars)
                concrete_ns = {v: snap.get(v, 0) for v in vars}
                out_val = snap["out"]
                solver.add(z3_val == out_val)
            except Exception:
                constraints_ok = False
                break

        if not constraints_ok:
            solver.pop()
            continue

        for snap in fail_snapshots:
            if "out" not in snap or not isinstance(snap["out"], (int, float)):
                continue
            try:
                z3_val = template_fn(z3_c, z3_vars)
                out_val = snap["out"]
                solver.add(z3_val != out_val)
            except Exception:
                pass

        try:
            if solver.check() == z3.sat:
                model = solver.model()
                c_val = model[z3_c].as_long()
                first = vars[0]
                return f"{first} + {c_val}" if c_val >= 0 else f"{first} - {abs(c_val)}"
        except Exception:
            pass

        solver.pop()

    return None


def _replace_in_line(line: str, new_expr: str) -> str | None:
    stripped = line.strip()
    if "=" in stripped:
        parts = stripped.split("=", 1)
        lhs = parts[0].strip()
        rhs = parts[1].strip()
        if "out" in new_expr:
            new_expr = new_expr.replace("out", rhs)
        return f"{lhs} = {new_expr}"
    if "return" in stripped:
        return stripped.replace(stripped.split("return", 1)[1].strip(), new_expr)
    return None
