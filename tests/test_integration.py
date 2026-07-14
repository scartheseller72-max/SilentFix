from silentfix.core.engine import SilentFixPro
from silentfix.core.types import RepairResult


def _buggy_max():
    def max_buggy(a: list[int]) -> int:
        result = 0
        for x in a:
            if x > result:
                result = x
        return result
    return max_buggy


def _buggy_sum():
    def sum_buggy(a: list[int]) -> int:
        total = 0
        for i in range(1, len(a)):
            total += a[i]
        return total
    return sum_buggy


def _buggy_contains():
    def contains_buggy(a: list[int], x: int) -> bool:
        for item in a:
            if item == x:
                return True
            else:
                return False
        return False
    return contains_buggy


def _buggy_average():
    def avg_buggy(a: list[float]) -> float:
        total = 0.0
        for x in a:
            total += x
        return total / len(a) if len(a) > 1 else total
    return avg_buggy


def _buggy_unique():
    def unique_buggy(a: list[int]) -> list[int]:
        result = []
        for x in a:
            if x not in result:
                result.append(x)
        return result
    return unique_buggy


def test_detect_max_bug():
    engine = SilentFixPro()
    result = engine.fix(_buggy_max())
    assert result is not None
    assert len(result.failing_inputs) > 0 or len(result.suspicious_locations) > 0
    print(f"  Failures: {len(result.failing_inputs)}, Suspicious: {len(result.suspicious_locations)}")


def test_detect_sum_bug():
    engine = SilentFixPro()
    result = engine.fix(_buggy_sum())
    assert result is not None
    print(f"  Failures: {len(result.failing_inputs)}, Suspicious: {len(result.suspicious_locations)}")


def test_detect_contains_bug():
    engine = SilentFixPro()
    result = engine.fix(_buggy_contains())
    assert result is not None
    print(f"  Failures: {len(result.failing_inputs)}, Suspicious: {len(result.suspicious_locations)}")


def test_detect_average_bug():
    engine = SilentFixPro()
    result = engine.fix(_buggy_average())
    assert result is not None
    print(f"  Failures: {len(result.failing_inputs)}, Suspicious: {len(result.suspicious_locations)}")


if __name__ == "__main__":
    print("=== Testing SilentFix Pro ===")

    print("\n--- Bug: max() starts at 0 (fails for all-negative inputs) ---")
    test_detect_max_bug()

    print("\n--- Bug: sum() skips first element ---")
    test_detect_sum_bug()

    print("\n--- Bug: contains() returns False prematurely ---")
    test_detect_contains_bug()

    print("\n--- Bug: average() divides by len-1 instead of len ---")
    test_detect_average_bug()

    print("\nDone!")
