from __future__ import annotations
from silentfix.core.types import SuspiciousLocation, ExecutionTrace, Patch, PropertySet
from silentfix.synthesis.template_fixer import apply_template_fixes
from silentfix.synthesis.constraint_solver import synthesize_from_constraints
from silentfix.synthesis.llm_agent import llm_agent_repair
from silentfix.config import get_config


def synthesize_patches(
    source: str,
    func_name: str,
    suspicious: list[SuspiciousLocation],
    props: PropertySet,
    pass_traces: list[ExecutionTrace],
    fail_traces: list[ExecutionTrace],
    fail_examples: list[tuple],
) -> list[Patch]:
    cfg = get_config()
    all_patches: list[Patch] = []

    budget = cfg.patch_budget_tiers

    tier1 = apply_template_fixes(source, suspicious)
    all_patches.extend(tier1[:budget[0]])

    tier2 = synthesize_from_constraints(source, suspicious, pass_traces, fail_traces)
    all_patches.extend(tier2[:budget[1]])

    tier3 = llm_agent_repair(source, func_name, suspicious, props, pass_traces, fail_traces)
    all_patches.extend(tier3[:budget[2]])

    seen = set()
    unique_patches = []
    for p in all_patches:
        key = p.patched_source[:200]
        if key not in seen:
            seen.add(key)
            unique_patches.append(p)

    return unique_patches
