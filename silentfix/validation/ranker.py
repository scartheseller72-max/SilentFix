from __future__ import annotations
import typing as t
from silentfix.core.types import Patch
from silentfix.core.utils import compare_asts


def rank_patches(patches: list[Patch], original_source: str) -> list[Patch]:
    scored = []
    for patch in patches:
        simplicity = compare_asts(original_source, patch.patched_source)
        behavioral_score = patch.score

        combined = (
            0.5 * behavioral_score +
            0.3 * simplicity +
            0.2 * (1.0 / (1.0 + patch.tier))
        )

        patch.score = combined
        scored.append(patch)

    scored.sort(key=lambda p: p.score, reverse=True)
    return scored
