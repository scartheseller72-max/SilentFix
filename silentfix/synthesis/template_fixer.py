from __future__ import annotations
import ast
import typing as t
import inspect
import textwrap
from silentfix.core.types import SuspiciousLocation, Patch


def apply_template_fixes(
    source: str,
    suspicious: list[SuspiciousLocation],
) -> list[Patch]:
    patches: list[Patch] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return patches

    func_node = _find_function_def(tree)

    for loc in suspicious:
        line_patches = _try_line_templates(source, loc.line_no)
        patches.extend(line_patches)

        context_patches = _try_context_templates(source, tree, loc.line_no, func_node)
        patches.extend(context_patches)

    return patches


def _find_function_def(tree: ast.AST) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            return node
    return None


def _try_line_templates(source: str, line_no: int) -> list[Patch]:
    patches: list[Patch] = []
    lines = source.split("\n")
    if line_no < 1 or line_no > len(lines):
        return patches

    line = lines[line_no - 1]
    stripped = line.strip()

    templates = [
        ("off_by_one_range", _fix_off_by_one),
        ("off_by_one_range_start", _fix_off_by_one_range_start),
        ("operator_swap", _fix_operator_swap),
        ("comparison_swap", _fix_comparison_direction),
        ("missing_increment", _fix_missing_increment),
        ("comparison_order", _fix_comparison_order),
        ("premature_return", _fix_premature_return),
        ("bad_initializer", _fix_bad_initializer),
        ("sort_mutation", _fix_sort_mutation),
        ("swapped_min_max", _fix_swapped_min_max),
        ("first_element_guard", _fix_first_element_guard),
        ("wrong_return_branch", _fix_wrong_return_branch),
        ("comparison_boundary", _fix_comparison_boundary),
        ("boolean_and_or", _fix_boolean_and_or),
    ]

    for name, fix_fn in templates:
        patched_lines = lines[:]
        new_line = fix_fn(stripped)
        if new_line and new_line != stripped:
            indent = line[:len(line) - len(line.lstrip())]
            patched_lines[line_no - 1] = indent + new_line
            diff = "\n".join(patched_lines)
            patches.append(Patch(
                diff=diff,
                patched_source=diff,
                tier=1,
                score=0.6,
                description=f"Template fix '{name}' at line {line_no}: {stripped.strip()} -> {new_line.strip()}",
            ))

    return patches


def _try_context_templates(
    source: str, tree: ast.AST, line_no: int, func_node: ast.FunctionDef | None,
) -> list[Patch]:
    patches: list[Patch] = []
    lines = source.split("\n")

    if func_node is None:
        return patches

    if _has_missing_return(func_node):
        last_stmt = func_node.body[-1] if func_node.body else None
        if last_stmt and hasattr(last_stmt, 'lineno'):
            indent = "    " * (len(func_node.body) if func_node.body else 1)
            ret_line = f"{indent}return None"
            patched = lines[:]
            patched.insert(last_stmt.lineno, ret_line)
            patches.append(Patch(
                diff="\n".join(patched),
                patched_source="\n".join(patched),
                tier=1,
                score=0.5,
                description=f"Template fix 'missing_return' in function at line {func_node.lineno}",
            ))

    loop_var = _get_loop_var_for_line(func_node, line_no)

    if line_no <= len(lines):
        line = lines[line_no - 1]
        stripped = line.strip()
        indent = line[:len(line) - len(line.lstrip())]

        if loop_var:
            patch = _fix_accumulator_pattern(stripped, loop_var, line_no, indent, lines)
            if patch:
                patches.append(patch)

        patch = _fix_missing_guard(stripped, func_node, line_no, indent, lines)
        if patch:
            patches.append(patch)

        patch = _fix_string_join_sep(stripped, func_node, line_no, indent, lines)
        if patch:
            patches.append(patch)

    return patches


import re


def _fix_off_by_one(line: str) -> str | None:
    m = re.search(r'range\((\w+)\s*\)', line)
    if m:
        var = m.group(1)
        return line.replace(m.group(0), f"range({var} - 1)")
    m = re.search(r'range\((\w+)\s*\)', line)
    if m:
        var = m.group(1)
        return line.replace(m.group(0), f"range(len({var}))")
    m = re.search(r'for\s+(\w+)\s+in\s+range\(len\((\w+)\)\s*\)', line)
    if m:
        idx, var = m.group(1), m.group(2)
        return line.replace(m.group(0), f"for {idx} in range(len({var}) - 1)")
    return None


def _fix_operator_swap(line: str) -> str | None:
    if "<=" in line and "if" in line:
        return line.replace("<=", "<")
    if ">=" in line and "if" in line:
        return line.replace(">=", ">")
    if "==" in line and "if" in line:
        return line.replace("==", "!=")
    return None


def _fix_comparison_direction(line: str) -> str | None:
    if "if" in line and " > " in line:
        m = re.search(r'if\s+(\w+)\s*>\s*(\w+)', line)
        if m and m.group(1) != m.group(2):
            return line.replace(f"{m.group(1)} > {m.group(2)}", f"{m.group(1)} < {m.group(2)}")
    if "if" in line and " < " in line:
        m = re.search(r'if\s+(\w+)\s*<\s*(\w+)', line)
        if m and m.group(1) != m.group(2):
            return line.replace(f"{m.group(1)} < {m.group(2)}", f"{m.group(1)} > {m.group(2)}")
    return None


def _fix_missing_increment(line: str) -> str | None:
    if line.strip().startswith("for ") and line.strip().endswith(":"):
        return None
    stripped = line.strip()
    if stripped.startswith("result") or stripped.startswith("total") or stripped.startswith("sum"):
        if "+" in stripped or "-" in stripped:
            return None
        return None
    return None


def _fix_comparison_order(line: str) -> str | None:
    m = re.search(r'if\s+(\d+)\s*([<>=!]+)\s*(\w+)', line)
    if m:
        const, op, var = m.group(1), m.group(2), m.group(3)
        reverse_op = {"<": ">", ">": "<", "<=": ">=", ">=": "<=", "==": "==", "!=": "!="}
        if op in reverse_op:
            new_op = reverse_op[op]
            return line.replace(m.group(0), f"if {var} {new_op} {const}")
    return None


def _fix_off_by_one_range_start(line: str) -> str | None:
    m = re.search(r'for\s+(\w+)\s+in\s+range\(1\s*,\s*len\((\w+)\)\s*\)', line)
    if m:
        idx, var = m.group(1), m.group(2)
        return line.replace(m.group(0), f"for {idx} in range(len({var}))")
    return None


def _fix_premature_return(line: str) -> str | None:
    stripped = line.strip()
    if stripped.startswith("else:") and stripped == "else:":
        return None
    if "else:" in stripped and "return" in stripped:
        return f"# {stripped}"
    return None


def _fix_bad_initializer(line: str) -> str | None:
    stripped = line.strip()
    pattern_vars = r'(result|total|sum|max_val|min_val|count|best|worst|max_so_far|min_so_far)'
    m = re.match(pattern_vars + r'\s*=\s*1\s*$', stripped)
    if m:
        var = m.group(1)
        if var in ('total', 'sum', 'count'):
            return line.replace(f"{var} = 1", f"{var} = 0")
        return None
    m = re.match(pattern_vars + r'\s*=\s*0\s*$', stripped)
    if m:
        var = m.group(1)
        if var in ('result', 'max_val', 'min_val', 'best', 'worst', 'max_so_far', 'min_so_far'):
            return line.replace(f"{var} = 0", f"{var} = float('-inf')")
        return None
    m = re.match(pattern_vars + r'\s*=\s*0\.0\s*$', stripped)
    if m:
        var = m.group(1)
        if var in ('result', 'max_val', 'min_val', 'best', 'worst', 'max_so_far', 'min_so_far'):
            return line.replace(f"{var} = 0.0", f"{var} = float('-inf')")
        return None
    return None


def _fix_sort_mutation(line: str) -> str | None:
    m = re.search(r'return\s+(\w+)\.sort\(\)', line)
    if m:
        var = m.group(1)
        return line.replace(m.group(0), f"return sorted({var})")
    return None


def _fix_swapped_min_max(line: str) -> str | None:
    m = re.search(r'return\s+max\((\w+)\)\s*,\s*min\(\1\)', line)
    if m:
        var = m.group(1)
        return line.replace(m.group(0), f"return min({var}), max({var})")
    return None


def _fix_first_element_guard(line: str) -> str | None:
    m = re.search(r'return\s+(\w+)\[0\]', line)
    if m and "if" not in line:
        var = m.group(1)
        return line.replace(m.group(0), f"return {var}[0] if {var} else None")
    return None


def _fix_wrong_return_branch(line: str) -> str | None:
    if "return True" in line:
        return line.replace("return True", "return False")
    if "return False" in line:
        return line.replace("return False", "return True")
    return None


def _fix_comparison_boundary(line: str) -> str | None:
    m = re.search(r'return\s+(\w+)\s*<\s*(\w+)\s*<\s*(\w+)', line)
    if m:
        x, lo, hi = m.group(1), m.group(2), m.group(3)
        return line.replace(m.group(0), f"return {lo} <= {x} <= {hi}")
    return None


def _fix_boolean_and_or(line: str) -> str | None:
    if "return" in line and "and" in line:
        if "or" not in line:
            m = re.search(r'return\s+(.+?)\s+and\s+(.+?)\s*$', line)
            if m:
                left, right = m.group(1), m.group(2)
                return line.replace(m.group(0), f"return {left} or {right}")
    return None


def _get_loop_var_for_line(func_node: ast.FunctionDef, line_no: int) -> str | None:
    for node in ast.walk(func_node):
        if isinstance(node, ast.For):
            start = getattr(node, 'lineno', 0)
            end = getattr(node, 'end_lineno', start)
            if start <= line_no <= end:
                if isinstance(node.target, ast.Name):
                    return node.target.id
                if isinstance(node.target, ast.Tuple):
                    for elt in node.target.elts:
                        if isinstance(elt, ast.Name):
                            return elt.id
    return None


def _fix_accumulator_pattern(
    stripped: str, loop_var: str, line_no: int, indent: str, lines: list[str],
) -> Patch | None:
    m = re.match(r'(\w+)\s*\+=\s*1\s*$', stripped)
    if m:
        new_line = stripped.replace("+= 1", f"+= {loop_var}")
        patched = lines[:]
        patched[line_no - 1] = indent + new_line
        diff = "\n".join(patched)
        return Patch(
            diff=diff, patched_source=diff, tier=1, score=0.6,
            description=f"Template fix 'count_vs_sum' at line {line_no}",
        )

    m = re.match(r'(\w+)\s*\+=\s*len\((\w+)\)\s*$', stripped)
    if m and m.group(2) != loop_var:
        new_line = stripped.replace(m.group(0), f"{m.group(1)} += {loop_var}")
        patched = lines[:]
        patched[line_no - 1] = indent + new_line
        diff = "\n".join(patched)
        return Patch(
            diff=diff, patched_source=diff, tier=1, score=0.6,
            description=f"Template fix 'wrong_accumulator' at line {line_no}",
        )

    return None


def _fix_missing_guard(
    stripped: str, func_node: ast.FunctionDef, line_no: int, indent: str, lines: list[str],
) -> Patch | None:
    if "return" not in stripped or "/" not in stripped:
        return None
    if "if" in stripped:
        return None
    if _has_guard_before(func_node, line_no):
        return None

    m = re.search(r'return\s+(\w+)\s*/\s*(\w+)', stripped)
    if m:
        denom = m.group(2)
        guard = f"{indent}if {denom} == 0:\n{indent}    return float('inf')"
        patched = lines[:]
        patched.insert(line_no - 1, guard)
        diff = "\n".join(patched)
        return Patch(
            diff=diff, patched_source=diff, tier=1, score=0.6,
            description=f"Template fix 'missing_denominator_guard' at line {line_no}",
        )

    return None


def _fix_string_join_sep(
    stripped: str, func_node: ast.FunctionDef, line_no: int, indent: str, lines: list[str],
) -> Patch | None:
    params = [a.arg for a in func_node.args.args if isinstance(a, ast.arg)]
    if "sep" not in params:
        return None
    if "+= " in stripped and ('"' in stripped or "'" in stripped):
        m = re.search(r'\+\=\s*item\s*\+\s*["\'][^"\']*["\']', stripped)
        if m:
            new_line = stripped.replace(m.group(0), f"+= item + {params[-1]}")
            patched = lines[:]
            patched[line_no - 1] = indent + new_line
            diff = "\n".join(patched)
            return Patch(
                diff=diff, patched_source=diff, tier=1, score=0.6,
                description=f"Template fix 'string_join_sep' at line {line_no}",
            )
        m2 = re.search(r'\+\=\s*["\'][^"\']*["\']', stripped)
        if m2 and not re.search(r'\+=\s*\w+\s*\+', stripped):
            new_line = stripped.replace(m2.group(0), f"+= {params[-1]}")
            patched = lines[:]
            patched[line_no - 1] = indent + new_line
            diff = "\n".join(patched)
            return Patch(
                diff=diff, patched_source=diff, tier=1, score=0.6,
                description=f"Template fix 'string_join_sep' at line {line_no}",
            )
    return None


def _has_guard_before(func_node: ast.FunctionDef, line_no: int) -> bool:
    for node in ast.walk(func_node):
        if isinstance(node, ast.If) and hasattr(node, 'lineno'):
            if node.lineno < line_no:
                for child in ast.walk(node):
                    if isinstance(child, ast.BinOp) and isinstance(child.op, ast.Div):
                        return True
    return False


def _has_missing_return(node: ast.FunctionDef) -> bool:
    has_return = any(
        isinstance(stmt, ast.Return)
        for stmt in ast.walk(node)
    )
    if not has_return and not _returns_none(node):
        return True
    return False


def _returns_none(node: ast.FunctionDef) -> bool:
    for stmt in node.body:
        if isinstance(stmt, ast.Return) and stmt.value is None:
            return True
    return False
