from __future__ import annotations
import typing as t
import importlib
import sys
import inspect
from pathlib import Path
from silentfix.core.engine import SilentFixPro
from silentfix.core.types import RepairResult, FailureSet
import textwrap


def fix_function(func: t.Callable) -> RepairResult:
    engine = SilentFixPro()
    module_code = _get_module_source(func)
    return engine.fix(func, module_code)


def fix_file(filepath: str, func_name: str | None = None) -> RepairResult:
    filepath = Path(filepath).resolve()
    sys.path.insert(0, str(filepath.parent))

    spec = importlib.util.spec_from_file_location(filepath.stem, filepath)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {filepath}")

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    if func_name:
        func = getattr(mod, func_name, None)
        if func is None:
            raise AttributeError(f"Function '{func_name}' not found in {filepath}")
    else:
        func = _find_main_function(mod)

    return fix_function(func)


def _get_module_source(func: t.Callable) -> str:
    try:
        mod = inspect.getmodule(func)
        if mod:
            import textwrap
            return textwrap.dedent(inspect.getsource(mod))
    except (OSError, TypeError):
        pass
    return ""


def _find_main_function(mod) -> t.Callable | None:
    candidates = [
        getattr(mod, name) for name in dir(mod)
        if callable(getattr(mod, name, None))
        and not name.startswith("_")
        and inspect.isfunction(getattr(mod, name))
    ]
    return candidates[0] if candidates else None


def cli():
    import click

    @click.group()
    def cli_group():
        pass

    @cli_group.command()
    @click.argument("target", required=True)
    def fix(target: str):
        if ":" in target:
            filepath, func_name = target.rsplit(":", 1)
        else:
            filepath, func_name = target, None

        result = fix_file(filepath, func_name)

        from rich.console import Console
        from rich.table import Table
        console = Console()

        if result.success:
            console.print("[bold green]Repair successful![/bold green]")
            console.print(f"Iterations: {result.iterations}")

            if result.patches:
                p = result.patches[0]
                console.print(f"\n[bold]Patch (tier {p.tier}):[/bold]")
                console.print(p.diff)
        else:
            console.print("[bold red]Repair failed[/bold red]")
            if result.error:
                console.print(f"Error: {result.error}")

        if result.suspicious_locations:
            table = Table(title="Suspicious Locations")
            table.add_column("Line", style="cyan")
            table.add_column("Score", style="yellow")
            table.add_column("SBFL", style="dim")
            table.add_column("Divergence", style="dim")

            for loc in result.suspicious_locations[:10]:
                table.add_row(
                    str(loc.line_no),
                    f"{loc.total_score:.3f}",
                    f"{loc.sbfl_score:.3f}",
                    f"{loc.divergence_score:.3f}",
                )
            console.print(table)

        if result.properties:
            props = result.properties
            console.print(f"\n[bold]Properties:[/bold]")
            console.print(f"  Preconditions: {len(props.preconditions)}")
            console.print(f"  Postconditions: {len(props.postconditions)}")
            console.print(f"  Invariants: {len(props.invariants)}")
            console.print(f"  Metamorphic: {len(props.metamorphic)}")
            console.print(f"  Examples: {len(props.examples)}")

    @cli_group.command()
    @click.argument("filepath", required=True)
    @click.argument("func_name", required=False)
    def analyze(filepath: str, func_name: str | None = None):
        from rich.console import Console
        console = Console()

        result = analyze_file(filepath, func_name)
        console.print(f"[bold]Analysis complete[/bold]")
        if result.properties:
            props = result.properties
            console.print(f"  Preconditions: {len(props.preconditions)}")
            console.print(f"  Postconditions: {len(props.postconditions)}")
            console.print(f"  Invariants: {len(props.invariants)}")
            console.print(f"  Metamorphic: {len(props.metamorphic)}")
            console.print(f"  Examples: {len(props.examples)}")
        console.print(f"  Failing inputs: {len(result.failing_inputs)}")
        console.print(f"  Suspicious locations: {len(result.suspicious_locations)}")
        if result.suspicious_locations:
            from rich.table import Table
            table = Table(title="Suspicious Locations")
            table.add_column("Line", style="cyan")
            table.add_column("Score", style="yellow")
            table.add_column("SBFL", style="dim")
            table.add_column("Divergence", style="dim")
            for loc in result.suspicious_locations[:10]:
                table.add_row(
                    str(loc.line_no),
                    f"{loc.total_score:.3f}",
                    f"{loc.sbfl_score:.3f}",
                    f"{loc.divergence_score:.3f}",
                )
            console.print(table)

    cli_group()


def analyze_file(filepath: str, func_name: str | None = None) -> RepairResult:
    filepath = Path(filepath).resolve()
    sys.path.insert(0, str(filepath.parent))

    spec = importlib.util.spec_from_file_location(filepath.stem, filepath)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {filepath}")

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    if func_name:
        func = getattr(mod, func_name, None)
        if func is None:
            raise AttributeError(f"Function '{func_name}' not found in {filepath}")
    else:
        func = _find_main_function(mod)

    from silentfix.core.types import Config
    from silentfix.property_inference.static_extractor import extract_static_properties
    from silentfix.property_inference.llm_extractor import extract_llm_properties
    from silentfix.property_inference.type_inferrer import extract_type_properties
    from silentfix.property_inference.dynamic_miner import mine_dynamic_properties
    from silentfix.property_inference.pattern_retrieval import retrieve_pattern_properties
    from silentfix.property_inference.fusion import fuse_properties
    from silentfix.detection.hypothesis_tester import run_property_tests
    from silentfix.detection.symbolic_executor import symbolic_detection
    from silentfix.detection.outlier_detector import detect_outliers
    from silentfix.tracing.tracer import trace_execution
    from silentfix.localization.ranker import rank_suspicious_locations
    from silentfix.config import get_config

    cfg = get_config()
    source = textwrap.dedent(inspect.getsource(func)) if inspect.getsource(func) else ""
    prop_sources = [
        extract_static_properties(func),
        extract_type_properties(func),
        mine_dynamic_properties(func),
        retrieve_pattern_properties(func.__name__, source),
    ]
    try:
        llm_props = extract_llm_properties(func, _get_module_source(func))
        prop_sources.append(llm_props)
    except Exception:
        pass
    props = fuse_properties(prop_sources)

    failures = FailureSet()
    hyp_failures = run_property_tests(func, props)
    for a, k, d in hyp_failures.failures:
        failures.add_failure(a, k, d)
    for a, k in hyp_failures.passes:
        failures.add_pass(a, k)
    sym_failures = symbolic_detection(func, props)
    for a, k, d in sym_failures.failures:
        failures.add_failure(a, k, d)
    outlier_failures = detect_outliers(func, props)
    for a, k, d in outlier_failures.failures:
        failures.add_failure(a, k, d)

    pass_traces = []
    fail_traces = []
    for args, kwargs in failures.passes[:50]:
        trace = trace_execution(func, args, kwargs, source=source)
        pass_traces.append(trace)
    for args, kwargs, _ in failures.failures[:20]:
        trace = trace_execution(func, args, kwargs, source=source)
        fail_traces.append(trace)

    suspicious = rank_suspicious_locations(func, pass_traces, fail_traces, source)

    result = RepairResult(
        success=False,
        original_source=source,
        properties=props,
        failing_inputs=[(a, k) for a, k, _ in failures.failures],
        suspicious_locations=suspicious,
    )
    if not failures.failures:
        result.error = "No silent bugs detected"
    return result
