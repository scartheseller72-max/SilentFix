"""Benchmark cases: simple silent logic bugs in Python."""

BENCHMARK_CASES = [
    # ──────────────────────────────────────────────
    # 1: max() initializes with 0 — fails on all-negative lists
    # ──────────────────────────────────────────────
    {
        "name": "max_all_negative",
        "description": "max() initializes result=0, fails on all-negative lists",
        "buggy_source": """
def max_buggy(a: list[int]) -> int:
    result = 0
    for x in a:
        if x > result:
            result = x
    return result
""",
        "fixed_source": """
def max_buggy(a: list[int]) -> int:
    if not a:
        raise ValueError("empty list")
    result = a[0]
    for x in a[1:]:
        if x > result:
            result = x
    return result
""",
        "example_passing": [([1, 2, 3], 3), ([0, -1, 5], 5)],
        "example_failing": [([-5, -3, -1], -1), ([-10, -20], -10)],
    },

    # ──────────────────────────────────────────────
    # 2: sum() skips first element (range starts at 1)
    # ──────────────────────────────────────────────
    {
        "name": "sum_skip_first",
        "description": "sum() loop starts at index 1, skipping a[0]",
        "buggy_source": """
def sum_buggy(a: list[int]) -> int:
    total = 0
    for i in range(1, len(a)):
        total += a[i]
    return total
""",
        "fixed_source": """
def sum_buggy(a: list[int]) -> int:
    total = 0
    for i in range(len(a)):
        total += a[i]
    return total
""",
        "example_passing": [([], 0), ([5], 0)],
        "example_failing": [([1, 2, 3], 6), ([10, 20], 30)],
    },

    # ──────────────────────────────────────────────
    # 3: sum() initializes total=1 instead of 0
    # ──────────────────────────────────────────────
    {
        "name": "sum_wrong_init",
        "description": "sum() initializes total=1 instead of 0",
        "buggy_source": """
def sum_init_buggy(a: list[int]) -> int:
    total = 1
    for x in a:
        total += x
    return total
""",
        "fixed_source": """
def sum_init_buggy(a: list[int]) -> int:
    total = 0
    for x in a:
        total += x
    return total
""",
        "example_passing": [([], 1), ([0], 1)],
        "example_failing": [([1, 2, 3], 6), ([5], 5)],
    },

    # ──────────────────────────────────────────────
    # 4: Wrong operator — uses > instead of < for min
    # ──────────────────────────────────────────────
    {
        "name": "min_wrong_operator",
        "description": "min() uses > instead of < for comparison",
        "buggy_source": """
def min_buggy(a: list[int]) -> int:
    result = a[0] if a else 0
    for x in a:
        if x > result:
            result = x
    return result
""",
        "fixed_source": """
def min_buggy(a: list[int]) -> int:
    result = a[0] if a else 0
    for x in a:
        if x < result:
            result = x
    return result
""",
        "example_passing": [([], 0), ([5], 5), ([1, 2, 3], 1)],
        "example_failing": [([-5, -3, -1], -5), ([10, -20, 30], -20)],
    },

    # ──────────────────────────────────────────────
    # 5: Wrong variable — accumulates wrong variable
    # ──────────────────────────────────────────────
    {
        "name": "wrong_variable_accumulator",
        "description": "loop accumulates loop var instead of list element",
        "buggy_source": """
def sum_wrong_var(a: list[int]) -> int:
    total = 0
    for x in a:
        total += len(a)
    return total
""",
        "fixed_source": """
def sum_wrong_var(a: list[int]) -> int:
    total = 0
    for x in a:
        total += x
    return total
""",
        "example_passing": [([], 0)],
        "example_failing": [([1, 2], 3), ([5], 5)],
    },

    # ──────────────────────────────────────────────
    # 6: Off-by-one comparison — uses < instead of <=
    # ──────────────────────────────────────────────
    {
        "name": "off_by_one_comparison",
        "description": "uses < instead of <= for boundary check",
        "buggy_source": """
def in_range_buggy(x: int, lo: int, hi: int) -> bool:
    return lo < x < hi
""",
        "fixed_source": """
def in_range_buggy(x: int, lo: int, hi: int) -> bool:
    return lo <= x <= hi
""",
        "example_passing": [(1, 1, 3, True), (2, 1, 3, True), (4, 1, 3, False)],
        "example_failing": [(1, 1, 3, True), (3, 1, 3, True)],
    },

    # ──────────────────────────────────────────────
    # 7: Mutation bug — .sort() returns None in-place
    # ──────────────────────────────────────────────
    {
        "name": "sort_mutation_bug",
        "description": "uses a.sort() which returns None instead of sorted(a)",
        "buggy_source": """
def sort_buggy(a: list[int]) -> list[int]:
    return a.sort()
""",
        "fixed_source": """
def sort_buggy(a: list[int]) -> list[int]:
    return sorted(a)
""",
        "example_passing": [([], [])],
        "example_failing": [([3, 1, 2], [1, 2, 3]), ([5, 4, 3], [3, 4, 5])],
    },

    # ──────────────────────────────────────────────
    # 8: Missing empty check — return a[0] without guard
    # ──────────────────────────────────────────────
    {
        "name": "first_element_no_check",
        "description": "returns a[0] without checking empty list",
        "buggy_source": """
def first_buggy(a: list[int]) -> int | None:
    return a[0]
""",
        "fixed_source": """
def first_buggy(a: list[int]) -> int | None:
    return a[0] if a else None
""",
        "example_passing": [([1, 2, 3], 1)],
        "example_failing": [([], None)],
    },

    # ──────────────────────────────────────────────
    # 9: Count wrong accumulator — uses +=1 instead of += item
    # ──────────────────────────────────────────────
    {
        "name": "count_vs_sum",
        "description": "counts elements instead of summing them",
        "buggy_source": """
def sum_count_buggy(a: list[int]) -> int:
    total = 0
    for x in a:
        total += 1
    return total
""",
        "fixed_source": """
def sum_count_buggy(a: list[int]) -> int:
    total = 0
    for x in a:
        total += x
    return total
""",
        "example_passing": [([], 0)],
        "example_failing": [([5, 10], 15), ([1, 2, 3], 6)],
    },

    # ──────────────────────────────────────────────
    # 10: Boolean logic error — uses and instead of or
    # ──────────────────────────────────────────────
    {
        "name": "boolean_logic_and_or",
        "description": "uses 'and' instead of 'or' for range check",
        "buggy_source": """
def valid_range_buggy(x: int) -> bool:
    return x < 0 and x > 100
""",
        "fixed_source": """
def valid_range_buggy(x: int) -> bool:
    return x < 0 or x > 100
""",
        "example_passing": [(-1, True), (101, True), (50, False)],
        "example_failing": [(-1, True), (101, True)],
    },

    # ──────────────────────────────────────────────
    # 11: Nested loop — wrong inner loop variable
    # ──────────────────────────────────────────────
    {
        "name": "nested_loop_wrong_var",
        "description": "inner loop reuses outer loop variable name",
        "buggy_source": """
def dot_product_buggy(a: list[int], b: list[int]) -> int:
    total = 0
    for i in range(len(a)):
        for i in range(len(b)):
            total += a[i] * b[i]
    return total
""",
        "fixed_source": """
def dot_product_buggy(a: list[int], b: list[int]) -> int:
    total = 0
    for i in range(len(a)):
        for j in range(len(b)):
            total += a[i] * b[j]
    return total
""",
        "example_passing": [([1, 2], [3, 4], 1*3 + 2*4)],
        "example_failing": [([1, 2], [3, 4], 11)],
    },

    # ──────────────────────────────────────────────
    # 12: Wrong return — returns wrong branch
    # ──────────────────────────────────────────────
    {
        "name": "wrong_return_branch",
        "description": "returns True when should return False and vice versa",
        "buggy_source": """
def is_even_buggy(n: int) -> bool:
    if n % 2 == 0:
        return False
    else:
        return True
""",
        "fixed_source": """
def is_even_buggy(n: int) -> bool:
    if n % 2 == 0:
        return True
    else:
        return False
""",
        "example_passing": [(2, True), (4, True)],
        "example_failing": [(2, True), (3, False)],
    },

    # ──────────────────────────────────────────────
    # 13: Division by zero guard — missing zero check in denominator
    # ──────────────────────────────────────────────
    {
        "name": "missing_denominator_check",
        "description": "divides without checking for zero denominator",
        "buggy_source": """
def divide_buggy(a: int, b: int) -> float:
    return a / b
""",
        "fixed_source": """
def divide_buggy(a: int, b: int) -> float:
    if b == 0:
        return float('inf')
    return a / b
""",
        "example_passing": [(10, 2, 5.0), (0, 5, 0.0)],
        "example_failing": [(5, 0, float('inf')), (-3, 0, float('-inf'))],
    },

    # ──────────────────────────────────────────────
    # 14: Swapped min/max in tuple unpacking
    # ──────────────────────────────────────────────
    {
        "name": "swapped_min_max",
        "description": "returns (max, min) instead of (min, max)",
        "buggy_source": """
def min_max_buggy(a: list[int]) -> tuple[int, int]:
    return max(a), min(a)
""",
        "fixed_source": """
def min_max_buggy(a: list[int]) -> tuple[int, int]:
    return min(a), max(a)
""",
        "example_passing": [([1, 2, 3], (1, 3))],
        "example_failing": [([1, 2, 3], (1, 3)), ([-5, 0, 5], (-5, 5))],
    },

    # ──────────────────────────────────────────────
    # 15: String concatenation in loop (O(n²)) — not a bug but wrong var
    # ──────────────────────────────────────────────
    {
        "name": "string_join_wrong_var",
        "description": "uses wrong separator variable",
        "buggy_source": """
def join_buggy(items: list[str], sep: str) -> str:
    result = ""
    for item in items:
        result += item + ","
    return result.rstrip(",")
""",
        "fixed_source": """
def join_buggy(items: list[str], sep: str) -> str:
    result = ""
    for item in items:
        result += item + sep
    return result.rstrip(sep)
""",
        "example_passing": [(["a", "b"], ",", "a,b")],
        "example_failing": [(["a", "b"], ";", "a;b"), (["x"], "|", "x")],
    },
]
