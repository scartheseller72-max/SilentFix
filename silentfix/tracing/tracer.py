from __future__ import annotations
import sys
import typing as t
import time
import inspect
import textwrap
from silentfix.core.types import ExecutionTrace, TraceEvent, VariableSnapshot


class TraceCollector:
    def __init__(self, func: t.Callable, source: str = ""):
        self.func = func
        self.events: list[TraceEvent] = []
        self._call_depth = 0
        self._target_name = func.__name__
        self._base_lineno = 0
        self._target_file = ""
        self._source_lines: list[str] = []

        if source:
            self._source_lines = source.split("\n")
            self._base_lineno = 0
            return

        try:
            self._target_file = inspect.getfile(func)
            source_lines, start_line = inspect.getsourcelines(func)
            self._base_lineno = start_line - 1
            self._source_lines = textwrap.dedent("".join(source_lines)).split("\n")
        except (OSError, TypeError, Exception):
            self._source_lines = source.split("\n") if source else ["def stub(): pass"]
            self._base_lineno = 0

        self._last_line = -1
        self._loop_count: dict[int, int] = {}

    def _adjusted_lineno(self, actual_lineno: int) -> int:
        return actual_lineno - self._base_lineno

    def _trace_callback(self, frame, event: str, arg):
        if self._target_file:
            if not frame.f_code.co_filename.endswith(self._target_file):
                return self._trace_callback
        if frame.f_code.co_name != self._target_name:
            return self._trace_callback

        actual_line = frame.f_lineno
        line_no = self._adjusted_lineno(actual_line)

        if line_no < 1 or line_no > len(self._source_lines):
            return self._trace_callback

        if event == "call":
            self._call_depth += 1
        elif event == "return":
            self._call_depth -= 1
        elif event == "line":
            if line_no == self._last_line:
                self._loop_count[line_no] = self._loop_count.get(line_no, 0) + 1
            else:
                self._loop_count[line_no] = 0
            self._last_line = line_no

            vars_list = []
            for name, val in frame.f_locals.items():
                if not name.startswith("_"):
                    snapshot = VariableSnapshot(
                        name=name,
                        value=val,
                        summarized=_summarize_value(val),
                    )
                    vars_list.append(snapshot)

            self.events.append(TraceEvent(
                line_no=line_no,
                event=event,
                variables=vars_list,
                loop_iteration=self._loop_count.get(line_no, 0),
                call_depth=self._call_depth,
            ))

        return self._trace_callback

    def run(self, *args, **kwargs) -> ExecutionTrace:
        trace = ExecutionTrace(
            input_args=args,
            input_kwargs=kwargs,
            output=None,
            passed=True,
        )

        start = time.perf_counter_ns()
        sys.settrace(self._trace_callback)
        try:
            result = self.func(*args, **kwargs)
            trace.output = result
            trace.passed = True
        except Exception as e:
            trace.passed = False
            trace.exception = str(e)
        finally:
            sys.settrace(None)
            trace.duration_ns = time.perf_counter_ns() - start
            trace.events = self.events

        return trace


def _summarize_value(val: t.Any) -> dict | None:
    if isinstance(val, (int, float, bool, str, type(None))):
        return {"type": type(val).__name__, "value": str(val)}
    if isinstance(val, (list, tuple)):
        return {
            "type": type(val).__name__,
            "length": len(val),
            "min": str(min(val)) if val and all(isinstance(v, (int, float)) for v in val) else None,
            "max": str(max(val)) if val and all(isinstance(v, (int, float)) for v in val) else None,
            "sample": [str(v) for v in val[:3]],
        }
    if isinstance(val, dict):
        return {
            "type": "dict",
            "length": len(val),
            "keys_sample": [str(k) for k in list(val.keys())[:3]],
        }
    if isinstance(val, set):
        return {
            "type": "set",
            "length": len(val),
        }
    return {"type": type(val).__name__}


def trace_execution(func: t.Callable, args: tuple, kwargs: dict | None = None, source: str = "") -> ExecutionTrace:
    collector = TraceCollector(func, source)
    return collector.run(*args, **(kwargs or {}))
