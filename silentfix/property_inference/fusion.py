from __future__ import annotations
import typing as t
from collections import defaultdict
from silentfix.core.types import Property, PropertyKind, PropertySet
from silentfix.config import get_config


def fuse_properties(sources: list[PropertySet]) -> PropertySet:
    cfg = get_config()
    merged = PropertySet()

    all_props: list[Property] = []
    for ps in sources:
        all_props.extend(ps.all())
    merged.examples = _merge_examples(sources)

    groupings = defaultdict(list)
    for prop in all_props:
        key = (prop.kind.value, prop.description[:80])
        groupings[key].append(prop)

    for key, group in groupings.items():
        kind_str = key[0]
        kind = PropertyKind(kind_str)
        avg_conf = sum(p.confidence for p in group) / len(group)
        sources_set = set(p.source for p in group)
        best_prop = max(group, key=lambda p: p.confidence)

        passes_threshold = avg_conf >= cfg.property_confidence_threshold
        passes_sources = len(sources_set) >= cfg.min_supporting_sources
        high_confidence = avg_conf >= 0.7

        if passes_threshold and (passes_sources or high_confidence):
            best_prop.confidence = min(1.0, avg_conf * (1 + 0.1 * len(sources_set)))
            _add_to_propertyset(merged, kind, best_prop)
        elif avg_conf >= cfg.property_confidence_threshold * 1.3:
            best_prop.confidence = avg_conf
            _add_to_propertyset(merged, kind, best_prop)

    merged = _resolve_conflicts(merged)
    return merged


def _add_to_propertyset(props: PropertySet, kind: PropertyKind, prop: Property):
    if kind == PropertyKind.PRECONDITION:
        props.preconditions.append(prop)
    elif kind == PropertyKind.POSTCONDITION:
        props.postconditions.append(prop)
    elif kind == PropertyKind.INVARIANT:
        props.invariants.append(prop)
    elif kind == PropertyKind.METAMORPHIC:
        props.metamorphic.append(prop)


def _merge_examples(sources: list[PropertySet]) -> list[tuple[tuple, dict, t.Any]]:
    seen = set()
    examples = []
    for ps in sources:
        for args, kwargs, expected in ps.examples:
            key = (str(args), str(kwargs))
            if key not in seen:
                seen.add(key)
                examples.append((args, kwargs, expected))
    return examples


def _resolve_conflicts(props: PropertySet) -> PropertySet:
    post = props.postconditions
    resolved = []
    pair_descriptions = [
        ("sorted ascending", "sorted descending"),
        ("non-negative", "non-positive"),
        ("maximum", "minimum"),
    ]

    for i, p1 in enumerate(post):
        conflict = False
        for p2 in post[i+1:]:
            for desc1, desc2 in pair_descriptions:
                if (desc1 in p1.description.lower() and desc2 in p2.description.lower()) or \
                   (desc2 in p1.description.lower() and desc1 in p2.description.lower()):
                    if p1.confidence > p2.confidence:
                        resolved.append(p1)
                    else:
                        resolved.append(p2)
                    conflict = True
                    break
            if conflict:
                break
        if not conflict:
            resolved.append(p1)

    props.postconditions = resolved
    return props
