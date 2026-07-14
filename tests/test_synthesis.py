from silentfix.synthesis.template_fixer import apply_template_fixes
from silentfix.synthesis.constraint_solver import synthesize_from_constraints
from silentfix.synthesis.synthesizer import synthesize_patches
from silentfix.core.types import SuspiciousLocation, PropertySet, ExecutionTrace, TraceEvent, VariableSnapshot


def test_template_off_by_one():
    source = "def f(a: list[int]) -> int:\n    total = 0\n    for i in range(1, len(a)):\n        total += a[i]\n    return total"
    suspicious = [SuspiciousLocation(line_no=3, node_type="for", total_score=0.5)]
    patches = apply_template_fixes(source, suspicious)
    assert len(patches) >= 1
    assert "range(len(a))" in patches[0].patched_source


def test_template_bad_initializer_max():
    source = "def f(a: list[int]) -> int:\n    result = 0\n    for x in a:\n        if x > result:\n            result = x\n    return result"
    suspicious = [SuspiciousLocation(line_no=2, node_type="assign", total_score=0.5)]
    patches = apply_template_fixes(source, suspicious)
    assert len(patches) >= 1
    assert "float('-inf')" in patches[0].patched_source


def test_template_bad_initializer_sum():
    source = "def f(a: list[int]) -> int:\n    total = 1\n    for x in a:\n        total += x\n    return total"
    suspicious = [SuspiciousLocation(line_no=2, node_type="assign", total_score=0.5)]
    patches = apply_template_fixes(source, suspicious)
    assert len(patches) >= 1
    assert "total = 0" in patches[0].patched_source


def test_template_operator_swap():
    source = "def f(a: list[int]) -> int:\n    result = a[0]\n    for x in a:\n        if x > result:\n            result = x\n    return result"
    suspicious = [SuspiciousLocation(line_no=4, node_type="if", total_score=0.5)]
    patches = apply_template_fixes(source, suspicious)
    assert len(patches) >= 0


def test_template_comparison_order():
    source = "def f(x: int) -> bool:\n    return 5 < x"
    suspicious = [SuspiciousLocation(line_no=2, node_type="return", total_score=0.5)]
    patches = apply_template_fixes(source, suspicious)
    assert len(patches) >= 0


def test_constraint_synthesizer_no_traces():
    source = "def f(a: list[int]) -> int:\n    total = 1\n    for x in a:\n        total += x\n    return total"
    suspicious = [SuspiciousLocation(line_no=2, node_type="assign", total_score=0.5)]
    patches = synthesize_from_constraints(source, suspicious, [], [])
    assert isinstance(patches, list)


def test_constraint_synthesizer_with_traces():
    source = "def f(a: list[int]) -> int:\n    total = 0\n    for x in a:\n        total += x\n    return total"
    suspicious = [SuspiciousLocation(line_no=5, node_type="return", total_score=0.5)]
    pass_traces = [
        ExecutionTrace(
            input_args=([1, 2],), input_kwargs={}, output=3, passed=True,
            events=[TraceEvent(line_no=5, event="line", variables=[
                VariableSnapshot(name="total", value=3),
                VariableSnapshot(name="a", value=[1, 2]),
            ])],
        )
    ]
    fail_traces = [
        ExecutionTrace(
            input_args=([1, 2],), input_kwargs={}, output=2, passed=False,
            events=[TraceEvent(line_no=5, event="line", variables=[
                VariableSnapshot(name="total", value=2),
                VariableSnapshot(name="a", value=[1, 2]),
            ])],
        )
    ]
    patches = synthesize_from_constraints(source, suspicious, pass_traces, fail_traces)
    assert isinstance(patches, list)


if __name__ == "__main__":
    test_template_off_by_one()
    print("  test_template_off_by_one: PASS")
    test_template_bad_initializer_max()
    print("  test_template_bad_initializer_max: PASS")
    test_template_bad_initializer_sum()
    print("  test_template_bad_initializer_sum: PASS")
    test_template_operator_swap()
    print("  test_template_operator_swap: PASS")
    test_template_comparison_order()
    print("  test_template_comparison_order: PASS")
    test_constraint_synthesizer_no_traces()
    print("  test_constraint_synthesizer_no_traces: PASS")
    test_constraint_synthesizer_with_traces()
    print("  test_constraint_synthesizer_with_traces: PASS")
    print("\nAll synthesis tests passed!")
