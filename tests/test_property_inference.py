from silentfix.property_inference.static_extractor import extract_static_properties
from silentfix.property_inference.type_inferrer import extract_type_properties
from silentfix.property_inference.dynamic_miner import mine_dynamic_properties
from silentfix.property_inference.pattern_retrieval import retrieve_pattern_properties
from silentfix.property_inference.fusion import fuse_properties


def _sample_sort():
    def sort_list(a: list[int]) -> list[int]:
        return sorted(a)
    return sort_list


def _sample_max():
    def max_list(a: list[int]) -> int:
        return max(a)
    return max_list


def _sample_no_doc():
    def foo(x: int, y: int) -> int:
        return x + y
    return foo


def test_static_extraction():
    props = extract_static_properties(_sample_sort())
    assert props is not None
    print(f"  Static: {len(props.preconditions)} pre, {len(props.postconditions)} post")

    props2 = extract_static_properties(_sample_no_doc())
    assert props2 is not None


def test_type_inference():
    props = extract_type_properties(_sample_max())
    assert props is not None
    print(f"  Type: {len(props.postconditions)} post")


def test_dynamic_mining():
    props = mine_dynamic_properties(_sample_max())
    assert props is not None
    print(f"  Dynamic: {len(props.postconditions)} post")


def test_pattern_retrieval():
    props = retrieve_pattern_properties("sort", "def sort_list")
    assert props is not None
    print(f"  Pattern: {len(props.postconditions)} post")


def test_fusion():
    sources = [
        extract_static_properties(_sample_sort()),
        extract_type_properties(_sample_sort()),
        mine_dynamic_properties(_sample_sort()),
        retrieve_pattern_properties("sort", "def sort_list"),
    ]
    fused = fuse_properties(sources)
    assert fused is not None
    assert len(fused.postconditions) > 0
    print(f"  Fused: {len(fused.postconditions)} postconditions")


if __name__ == "__main__":
    print("=== Property Inference Tests ===")
    test_static_extraction()
    test_type_inference()
    test_dynamic_mining()
    test_pattern_retrieval()
    test_fusion()
    print("\nAll property inference tests passed!")
