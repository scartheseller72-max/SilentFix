"""Benchmark runner for SilentFix Pro evaluation."""

from silentfix.core.engine import SilentFixPro
from benchmark.cases.simple_bugs import BENCHMARK_CASES


def run_benchmark():
    engine = SilentFixPro()
    results = []

    for case in BENCHMARK_CASES:
        print(f"\n{'='*60}")
        print(f"Benchmark: {case['name']}")
        print(f"  {case['description']}")

        buggy_source = case["buggy_source"].strip()
        ns = {}
        exec(compile(buggy_source, "<benchmark>", "exec"), ns)
        buggy_func = None
        for v in ns.values():
            if callable(v) and hasattr(v, '__name__'):
                buggy_func = v
                break
        if buggy_func is None:
            print(f"  [ERROR] No callable found")
            continue

        try:
            result = engine.fix(buggy_func, source_override=buggy_source)
            success = result.success
            n_failures = len(result.failing_inputs)
            n_suspicious = len(result.suspicious_locations)
            n_patches = len(result.patches)
            iterations = result.iterations

            results.append({
                "name": case["name"],
                "success": success,
                "failures": n_failures,
                "suspicious": n_suspicious,
                "patches": n_patches,
                "iterations": iterations,
            })

            status = "[PASS]" if success else "[FAIL]"
            print(f"  {status} Failures={n_failures}, Suspicious={n_suspicious}, "
                  f"Patches={n_patches}, Iterations={iterations}")

        except Exception as e:
            print(f"  [ERROR] {e}")
            results.append({"name": case["name"], "error": str(e)})

    print(f"\n{'='*60}")
    print(f"\nBenchmark Summary:")
    passed = sum(1 for r in results if r.get("success"))
    detected = sum(1 for r in results if r.get("failures", 0) > 0 or r.get("success"))
    print(f"  Total cases: {len(results)}")
    print(f"  Repaired: {passed}/{len(results)}")
    print(f"  Detected: {detected}/{len(results)}")

    return results


if __name__ == "__main__":
    run_benchmark()
