from __future__ import annotations
import typing as t
from dataclasses import dataclass, field
from enum import Enum


class PropertyKind(str, Enum):
    PRECONDITION = "pre"
    POSTCONDITION = "post"
    INVARIANT = "invariant"
    METAMORPHIC = "metamorphic"


@dataclass
class Property:
    kind: PropertyKind
    predicate_py: t.Callable | None
    predicate_z3: t.Callable | None
    description: str
    confidence: float
    source: str = "unknown"

    def __call__(self, *args, **kwargs) -> bool:
        if self.predicate_py is not None:
            return self.predicate_py(*args, **kwargs)
        return True


@dataclass
class PropertySet:
    preconditions: list[Property] = field(default_factory=list)
    postconditions: list[Property] = field(default_factory=list)
    invariants: list[Property] = field(default_factory=list)
    metamorphic: list[Property] = field(default_factory=list)
    examples: list[tuple[tuple, dict, t.Any]] = field(default_factory=list)

    def all(self) -> list[Property]:
        return self.preconditions + self.postconditions + self.invariants + self.metamorphic


@dataclass
class VariableSnapshot:
    name: str
    value: t.Any
    summarized: dict | None = None


@dataclass
class TraceEvent:
    line_no: int
    event: str
    variables: list[VariableSnapshot]
    branch_decision: bool | None = None
    loop_iteration: int | None = None
    call_depth: int = 0


@dataclass
class ExecutionTrace:
    input_args: tuple
    input_kwargs: dict
    output: t.Any | None
    events: list[TraceEvent] = field(default_factory=list)
    passed: bool = True
    exception: str | None = None
    duration_ns: int = 0


@dataclass
class SuspiciousLocation:
    line_no: int
    node_type: str
    sbfl_score: float = 0.0
    neural_score: float = 0.0
    divergence_score: float = 0.0
    total_score: float = 0.0
    context: str = ""


@dataclass
class Patch:
    diff: str
    patched_source: str
    tier: int
    score: float = 0.0
    verified: bool = False
    description: str = ""


@dataclass
class RepairResult:
    success: bool
    original_source: str
    patched_source: str | None = None
    patches: list[Patch] = field(default_factory=list)
    properties: PropertySet | None = None
    failing_inputs: list[tuple] = field(default_factory=list)
    suspicious_locations: list[SuspiciousLocation] = field(default_factory=list)
    iterations: int = 0
    error: str | None = None


class FailureSet:
    def __init__(self):
        self.failures: list[tuple[tuple, dict, str]] = []
        self.passes: list[tuple[tuple, dict]] = []

    def add_failure(self, args: tuple, kwargs: dict, violated_property: str):
        self.failures.append((args, kwargs, violated_property))

    def add_pass(self, args: tuple, kwargs: dict):
        self.passes.append((args, kwargs))

    def __len__(self):
        return len(self.failures)


class Config:
    def __init__(self, **kwargs):
        self.llm_backend = kwargs.get("llm_backend", "openai")
        self.llm_model = kwargs.get("llm_model", "gpt-4")
        self.ollama_url = kwargs.get("ollama_url", "http://localhost:11434")
        self.ollama_model = kwargs.get("ollama_model", "codellama")
        self.openai_api_key = kwargs.get("openai_api_key", "")
        self.openai_model = kwargs.get("openai_model", "gpt-4")

        self.property_confidence_threshold = kwargs.get("property_confidence_threshold", 0.5)
        self.min_supporting_sources = kwargs.get("min_supporting_sources", 2)
        self.top_k_suspicious = kwargs.get("top_k_suspicious", 5)
        self.max_iterations = kwargs.get("max_iterations", 5)
        self.patch_budget_tiers = kwargs.get("patch_budget_tiers", [5, 5, 3, 2])

        self.sbfl_weight = kwargs.get("sbfl_weight", 0.4)
        self.neural_weight = kwargs.get("neural_weight", 0.3)
        self.divergence_weight = kwargs.get("divergence_weight", 0.3)

        self.hypothesis_max_examples = kwargs.get("hypothesis_max_examples", 200)
        self.symbolic_timeout_s = kwargs.get("symbolic_timeout_s", 30)
        self.dynamic_miner_samples = kwargs.get("dynamic_miner_samples", 200)
        self.held_out_ratio = kwargs.get("held_out_ratio", 0.2)
        self.verify_simple_only = kwargs.get("verify_simple_only", True)
