from __future__ import annotations
import typing as t
import textwrap
from silentfix.core.types import (
    SuspiciousLocation, ExecutionTrace, Patch, PropertySet,
)
from silentfix.llm.client import LLMClient
from silentfix.llm.prompts import REPAIR_INSTRUCTION


def llm_agent_repair(
    source: str,
    func_name: str,
    suspicious: list[SuspiciousLocation],
    props: PropertySet,
    pass_traces: list[ExecutionTrace],
    fail_traces: list[ExecutionTrace],
) -> list[Patch]:
    patches: list[Patch] = []

    client = LLMClient()
    prompt = _build_agent_prompt(source, func_name, suspicious, props, pass_traces, fail_traces)

    try:
        response = client.complete(prompt, system=REPAIR_INSTRUCTION, max_tokens=4096)
        patched = _extract_patched_source(response)
        if patched and patched != source:
            patches.append(Patch(
                diff=patched,
                patched_source=patched,
                tier=4,
                score=0.7,
                description="LLM agent repair",
            ))
    except Exception:
        pass

    return patches


def _build_agent_prompt(
    source: str, func_name: str,
    suspicious: list[SuspiciousLocation],
    props: PropertySet,
    pass_traces: list[ExecutionTrace],
    fail_traces: list[ExecutionTrace],
) -> str:
    suspicious_lines = "\n".join(
        f"  Line {loc.line_no}: score={loc.total_score:.3f}"
        for loc in suspicious[:5]
    )

    props_desc = "\n".join(
        f"  - [{p.kind.value}] {p.description} (conf={p.confidence:.2f})"
        for p in props.all()[:10]
    )

    pass_examples = "\n".join(
        f"  f{tuple(e.input_args)} -> {e.output}"
        for e in pass_traces[:3] if e.output is not None
    )
    fail_examples = "\n".join(
        f"  f{tuple(e.input_args)} -> {e.output} (FAIL)"
        for e in fail_traces[:5] if e.output is not None
    )

    return textwrap.dedent(f"""\
    Function to fix: `{func_name}`

    ```python
    {source}
    ```

    Suspicious locations (ranked):
    {suspicious_lines}

    Inferred properties:
    {props_desc}

    Passing examples:
    {pass_examples}

    Failing examples:
    {fail_examples}

    Please provide the corrected version of the function with minimal changes.
    """)


def _extract_patched_source(response: str) -> str | None:
    import re
    m = re.search(r'```python\n(.*?)```', response, re.DOTALL)
    if m:
        return m.group(1).strip()
    lines = response.strip().split("\n")
    start = -1
    for i, line in enumerate(lines):
        if line.startswith("def "):
            start = i
            break
    if start >= 0:
        return "\n".join(lines[start:])
    return None
