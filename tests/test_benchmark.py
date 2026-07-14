from silentfix.core.engine import SilentFixPro
from benchmark.cases.simple_bugs import BENCHMARK_CASES


def test_benchmark_all_cases():
    engine = SilentFixPro()
    tested = 0
    detected = 0
    repaired = 0

    for case in BENCHMARK_CASES:
        buggy_source = case["buggy_source"].strip()
        ns = {}
        exec(compile(buggy_source, "<test>", "exec"), ns)
        buggy_func = None
        for v in ns.values():
            if callable(v) and hasattr(v, '__name__'):
                buggy_func = v
                break
        if buggy_func is None:
            continue

        tested += 1
        result = engine.fix(buggy_func, source_override=buggy_source)

        if result.failing_inputs:
            detected += 1
        if result.success:
            repaired += 1

    print(f"  Tested: {tested}, Detected: {detected}, Repaired: {repaired}")
    assert tested == len(BENCHMARK_CASES)
    assert detected > 0


def test_benchmark_max_all_negative():
    from benchmark.cases.simple_bugs import BENCHMARK_CASES as BC
    case = BC[0]
    assert case["name"] == "max_all_negative"
    ns = {}
    exec(compile(case["buggy_source"].strip(), "<test>", "exec"), ns)
    buggy_func = next(v for v in ns.values() if callable(v) and hasattr(v, '__name__'))

    engine = SilentFixPro()
    result = engine.fix(buggy_func, source_override=case["buggy_source"].strip())

    assert len(result.failing_inputs) > 0, "Should detect at least one failure"


def test_benchmark_sum_skip_first():
    from benchmark.cases.simple_bugs import BENCHMARK_CASES as BC
    case = BC[1]
    ns = {}
    exec(compile(case["buggy_source"].strip(), "<test>", "exec"), ns)
    buggy_func = next(v for v in ns.values() if callable(v) and hasattr(v, '__name__'))

    engine = SilentFixPro()
    result = engine.fix(buggy_func, source_override=case["buggy_source"].strip())

    assert len(result.failing_inputs) > 0


if __name__ == "__main__":
    test_benchmark_all_cases()
    print("  test_benchmark_all_cases: PASS")
    test_benchmark_max_all_negative()
    print("  test_benchmark_max_all_negative: PASS")
    test_benchmark_sum_skip_first()
    print("  test_benchmark_sum_skip_first: PASS")
    print("\nAll benchmark tests passed!")
