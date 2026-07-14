from __future__ import annotations
import ast
import sys
import types
import typing as t
import textwrap


def get_function_source(func: t.Callable) -> str:
    try:
        source = inspect.getsource(func)
        return textwrap.dedent(source)
    except (OSError, TypeError):
        return ""


def get_module_source(func: t.Callable) -> str:
    try:
        mod = inspect.getmodule(func)
        if mod:
            source = inspect.getsource(mod)
            return textwrap.dedent(source)
    except (OSError, TypeError):
        pass
    return ""


def parse_function_ast(func: t.Callable) -> ast.FunctionDef | None:
    try:
        source = get_function_source(func)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                return node
    except SyntaxError:
        return None
    return None


def make_predicate(expr_str: str, param_names: list[str]) -> t.Callable | None:
    ns = {"__builtins__": __builtins__}
    try:
        exec(f"def _predicate({', '.join(param_names)}): return {expr_str}", ns)
        return ns["_predicate"]
    except Exception:
        return None


def safe_eval(expr: str, context: dict) -> t.Any:
    allowed_names = {
        "abs", "all", "any", "bool", "dict", "enumerate", "float",
        "int", "isinstance", "len", "list", "max", "min", "range",
        "reversed", "set", "sorted", "str", "sum", "tuple", "type", "zip",
        "True", "False", "None",
    }
    safe_context = {k: v for k, v in context.items() if not k.startswith("_")}
    safe_context.update({k: __builtins__[k] for k in allowed_names & set(__builtins__.keys())})
    try:
        return eval(expr, {"__builtins__": {}}, safe_context)
    except Exception:
        return None


def compare_asts(a1: str, a2: str) -> float:
    try:
        t1 = ast.dump(ast.parse(a1), indent=0)
        t2 = ast.dump(ast.parse(a2), indent=0)
    except SyntaxError:
        return 0.0
    from difflib import SequenceMatcher
    return SequenceMatcher(None, t1, t2).ratio()


def clone_function(func: t.Callable, new_code: str, mod_name: str = "__silentfix__") -> t.Callable:
    ns: dict = {}
    exec(compile(ast.parse(new_code), "<silentfix>", "exec"), ns)
    for name in ns:
        if callable(ns[name]) or isinstance(ns[name], type):
            return ns[name]
    return func


import inspect
