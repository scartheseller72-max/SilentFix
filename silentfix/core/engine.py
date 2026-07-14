from __future__ import annotations
import typing as t
import inspect
import textwrap
from silentfix.core.types import (
    PropertySet, FailureSet, ExecutionTrace,
    SuspiciousLocation, Patch, RepairResult, Config,
)
from silentfix.property_inference.static_extractor import extract_static_properties
from silentfix.property_inference.llm_extractor import extract_llm_properties
from silentfix.property_inference.type_inferrer import extract_type_properties
from silentfix.property_inference.dynamic_miner import mine_dynamic_properties
from silentfix.property_inference.pattern_retrieval import retrieve_pattern_properties
from silentfix.property_inference.fusion import fuse_properties
from silentfix.detection.hypothesis_tester import run_property_tests
from silentfix.detection.symbolic_executor import symbolic_detection
from silentfix.detection.outlier_detector import detect_outliers
from silentfix.detection.reflection import filter_false_positives
from silentfix.tracing.tracer import trace_execution
from silentfix.localization.ranker import rank_suspicious_locations
from silentfix.synthesis.synthesizer import synthesize_patches
from silentfix.validation.regression import validate_patch
from silentfix.validation.ranker import rank_patches
from silentfix.config import get_config


class SilentFixPro:
    def __init__(self, config: Config | None = None):
        self.config = config or get_config()
        self.iteration = 0

    def fix(self, func: t.Callable, module_code: str = "", source_override: str = "") -> RepairResult:
        source = source_override or self._get_source(func)
        result = RepairResult(
            success=False,
            original_source=source,
        )

        props = self._infer_properties(func, module_code, source)
        result.properties = props

        failures = self._detect_failures(func, props)
        result.failing_inputs = [(a, k) for a, k, _ in failures.failures]

        if not failures.failures:
            result.error = "No silent bugs detected"
            return result

        pass_traces, fail_traces = self._trace_executions(func, failures, source)

        suspicious = rank_suspicious_locations(func, pass_traces, fail_traces, source)
        result.suspicious_locations = suspicious

        best_patch = None
        for iteration in range(self.config.max_iterations):
            self.iteration = iteration + 1

            top_k = self.config.top_k_suspicious + iteration * 2
            expand_suspicious = suspicious[:top_k] if len(suspicious) > top_k else suspicious

            patch = self._try_repair(
                func, source, expand_suspicious, props,
                pass_traces, fail_traces, failures,
            )
            if patch is None:
                result.error = f"No valid patch found after {iteration + 1} iterations"
                continue

            best_patch = patch
            break

        if best_patch:
            result.success = True
            result.patched_source = best_patch.patched_source
            result.patches = [best_patch]

        result.iterations = self.iteration
        return result

    def _infer_properties(self, func: t.Callable, module_code: str, source: str = "") -> PropertySet:
        func_source = source or self._get_source(func)
        sources = [
            extract_static_properties(func, source=func_source),
            extract_type_properties(func),
            mine_dynamic_properties(func),
            retrieve_pattern_properties(func.__name__, func_source),
        ]

        try:
            llm_props = extract_llm_properties(func, module_code)
            sources.append(llm_props)
        except Exception:
            pass

        return fuse_properties(sources)

    def _detect_failures(self, func: t.Callable, props: PropertySet) -> FailureSet:
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

        return filter_false_positives(func, props, failures)

    def _trace_executions(
        self, func: t.Callable, failures: FailureSet, source: str = "",
    ) -> tuple[list[ExecutionTrace], list[ExecutionTrace]]:
        pass_traces = []
        fail_traces = []

        for args, kwargs in failures.passes[:50]:
            trace = trace_execution(func, args, kwargs, source=source)
            pass_traces.append(trace)

        for args, kwargs, _ in failures.failures[:20]:
            trace = trace_execution(func, args, kwargs, source=source)
            fail_traces.append(trace)

        return pass_traces, fail_traces

    def _try_repair(
        self,
        func: t.Callable,
        source: str,
        suspicious: list[SuspiciousLocation],
        props: PropertySet,
        pass_traces: list[ExecutionTrace],
        fail_traces: list[ExecutionTrace],
        failures: FailureSet,
    ) -> Patch | None:
        fail_examples = [
            (a, o) for a, _, _ in failures.failures[:5]
            for o in [self._try_call(func, a)]
            if o is not None
        ]

        candidates = synthesize_patches(
            source, func.__name__, suspicious, props,
            pass_traces, fail_traces, fail_examples,
        )

        valid_results = []
        for candidate in candidates:
            validation = validate_patch(
                func, candidate.patched_source, props,
                [(a, k) for a, k, _ in failures.failures],
                failures.passes,
            )
            if validation["passed"]:
                candidate.verified = validation.get("verified", False)
                candidate.score = validation["score"]
                valid_results.append(candidate)

        if valid_results:
            ranked = rank_patches(valid_results, source)
            return ranked[0]

        return None

    def _get_source(self, func: t.Callable) -> str:
        try:
            return textwrap.dedent(inspect.getsource(func))
        except (OSError, TypeError, Exception):
            return ""

    def _try_call(self, func: t.Callable, args: tuple) -> t.Any:
        try:
            return func(*args)
        except Exception:
            return None
