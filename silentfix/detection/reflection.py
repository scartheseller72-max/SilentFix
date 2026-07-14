from __future__ import annotations
from silentfix.core.types import PropertySet, FailureSet


def filter_false_positives(
    func: t.Callable, props: PropertySet, failures: FailureSet,
) -> FailureSet:
    return failures
